"""Tests for ticket creation, workflow rules, filtering, SLA times and dashboard maths."""
import sqlite3
from datetime import timedelta

from app.db import from_text, to_text, utcnow


def create(client, **over):
    data = dict(title="Printer offline", requester="Test User", category="Hardware",
                priority="Medium", description="Shows offline", assignee_id="")
    data.update(over)
    return client.post("/tickets/new", data=data, follow_redirects=False)


def rows(app, sql, params=()):
    con = sqlite3.connect(app.config["DATABASE"])
    con.row_factory = sqlite3.Row
    out = con.execute(sql, params).fetchall()
    con.close()
    return out


def insert_ticket(app, category, priority, created_hours_ago, resolve_after_hours=None):
    """Insert a ticket directly with exact timestamps (for deterministic stats tests)."""
    created = utcnow() - timedelta(hours=created_hours_ago)
    resolved = created + timedelta(hours=resolve_after_hours) if resolve_after_hours else None
    due = created + timedelta(hours={"Critical": 4, "High": 8, "Medium": 24, "Low": 72}[priority])
    con = sqlite3.connect(app.config["DATABASE"])
    con.execute(
        "INSERT INTO tickets (title, requester, category, priority, status, created_at, "
        "updated_at, due_at, resolved_at, resolution) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("t", "r", category, priority, "Resolved" if resolved else "Open", to_text(created),
         to_text(created), to_text(due), to_text(resolved) if resolved else None,
         "fixed" if resolved else None))
    con.commit()
    con.close()


# ---- creating tickets ------------------------------------------------------
def test_create_ticket_sets_sla_due_from_priority(app, client):
    resp = create(client, priority="Critical")
    assert resp.status_code == 302
    t = rows(app, "SELECT * FROM tickets")[0]
    assert t["status"] == "Open"
    assert from_text(t["due_at"]) - from_text(t["created_at"]) == timedelta(hours=4)
    # the creation is recorded in the resolution log
    assert rows(app, "SELECT COUNT(*) n FROM notes WHERE ticket_id=?", (t["id"],))[0]["n"] == 1


def test_create_rejects_invalid_input(app, client):
    create(client, title="  ")
    create(client, category="Plumbing")
    create(client, priority="Urgent!!")
    assert rows(app, "SELECT COUNT(*) n FROM tickets")[0]["n"] == 0


def test_html_in_title_is_escaped(app, client):
    create(client, title="<script>alert(1)</script>")
    page = client.get("/tickets").data.decode()
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


# ---- workflow ----------------------------------------------------------------
def test_assign_and_change_priority_logs_and_recalculates_sla(app, client):
    create(client, priority="Low")
    tid = rows(app, "SELECT id FROM tickets")[0]["id"]
    client.post(f"/tickets/{tid}/update", data=dict(
        status="In Progress", priority="High", assignee_id="1", author="Tech One"))
    t = rows(app, "SELECT * FROM tickets WHERE id=?", (tid,))[0]
    assert (t["status"], t["priority"], t["assignee_id"]) == ("In Progress", "High", 1)
    assert from_text(t["due_at"]) - from_text(t["created_at"]) == timedelta(hours=8)
    log = " ".join(r["body"] for r in rows(app, "SELECT body FROM notes WHERE kind='change'"))
    assert "Priority Low -> High" in log and "Assigned to Tech One" in log


def test_cannot_resolve_without_resolution(app, client):
    create(client)
    client.post("/tickets/1/update", data=dict(status="Resolved", priority="Medium", assignee_id=""))
    t = rows(app, "SELECT * FROM tickets")[0]
    assert t["status"] == "Open" and t["resolved_at"] is None


def test_resolve_close_and_reopen(app, client):
    create(client)
    client.post("/tickets/1/update", data=dict(
        status="Resolved", priority="Medium", assignee_id="", resolution="Replaced toner."))
    t = rows(app, "SELECT * FROM tickets")[0]
    assert t["status"] == "Resolved" and t["resolved_at"] and t["resolution"] == "Replaced toner."
    assert rows(app, "SELECT COUNT(*) n FROM notes WHERE kind='resolution'")[0]["n"] == 1
    client.post("/tickets/1/update", data=dict(
        status="Closed", priority="Medium", assignee_id="", resolution="Replaced toner."))
    assert rows(app, "SELECT status FROM tickets")[0]["status"] == "Closed"
    client.post("/tickets/1/update", data=dict(status="Open", priority="Medium", assignee_id=""))
    t = rows(app, "SELECT * FROM tickets")[0]
    assert t["status"] == "Open" and t["resolved_at"] is None


def test_add_note_and_empty_note_rejected(app, client):
    create(client)
    client.post("/tickets/1/notes", data=dict(author="Tech One", body="Called the user."))
    client.post("/tickets/1/notes", data=dict(author="Tech One", body="   "))
    notes = rows(app, "SELECT * FROM notes WHERE kind='note'")
    assert len(notes) == 1 and notes[0]["body"] == "Called the user."
    assert "Called the user." in client.get("/tickets/1").data.decode()


def test_missing_ticket_is_404(client):
    assert client.get("/tickets/12345").status_code == 404


# ---- search / filter -----------------------------------------------------------
def test_search_and_filters(app, client):
    create(client, title="Wi-Fi keeps dropping", category="Network", priority="High")
    create(client, title="Reset my password", category="Account Access", priority="Low")
    create(client, title="Monitor flicker", category="Hardware", priority="Low")

    def titles(qs):
        page = client.get("/tickets?" + qs).data.decode()
        return [t for t in ("Wi-Fi keeps dropping", "Reset my password", "Monitor flicker") if t in page]

    assert titles("q=wi-fi") == ["Wi-Fi keeps dropping"]
    assert titles("category=Account+Access") == ["Reset my password"]
    assert titles("priority=Low") == ["Reset my password", "Monitor flicker"]
    assert titles("q=%232") == ["Reset my password"]                 # search by ticket number
    assert titles("status=Closed") == []
    assert len(titles("")) == 3


def test_overdue_filter(app, client):
    insert_ticket(app, "Network", "Critical", created_hours_ago=10)      # due 4h after -> overdue
    insert_ticket(app, "Network", "Low", created_hours_ago=1)            # not overdue
    page = client.get("/tickets?overdue=1").data.decode()
    import re
    assert len(re.findall(r'href="/tickets/\d+"', page)) == 1


# ---- dashboard ---------------------------------------------------------------------
def test_dashboard_numbers(app, client):
    insert_ticket(app, "Network", "Medium", 5)                  # open
    insert_ticket(app, "Network", "Critical", 10)               # open + overdue
    insert_ticket(app, "Hardware", "Medium", 50, resolve_after_hours=2)    # within SLA
    insert_ticket(app, "Hardware", "High", 50, resolve_after_hours=10)     # missed 8h SLA
    insert_ticket(app, "Software", "Low", 100, resolve_after_hours=6)
    from app.stats import dashboard_stats
    with app.app_context():
        s = dashboard_stats()
    assert s["by_category"] == {"Hardware": 0, "Software": 0, "Network": 2, "Account Access": 0}
    assert s["total_open"] == 2 and s["overdue"] == 1 and s["unassigned"] == 2
    assert s["resolved_count"] == 3
    assert abs(s["avg_hours_all"] - (2 + 10 + 6) / 3) < 0.01
    assert abs(s["avg_hours_by_category"]["Hardware"] - 6.0) < 0.01
    assert s["avg_hours_by_category"]["Network"] is None
    assert abs(s["sla_met_pct"] - 200 / 3) < 0.01               # 2 of 3 met SLA
    assert client.get("/").status_code == 200


def test_dashboard_with_no_data(client):
    resp = client.get("/")
    assert resp.status_code == 200 and b"n/a" in resp.data


# ---- tag links on the detail page ----------------------------------------------------
def test_detail_page_tags_link_to_matching_filters(app, client):
    import re
    from urllib.parse import parse_qs, unquote_plus, urlparse
    create(client, title="Wi-Fi keeps dropping", category="Network", priority="High")
    create(client, title="Reset my password", category="Account Access", priority="Low")
    for tid, cat, pri in ((1, "Network", "High"), (2, "Account Access", "Low")):
        page = client.get(f"/tickets/{tid}").data.decode()
        links = re.findall(r'<a class="tag[^"]*" href="([^"]+)"', page)
        qs = [parse_qs(urlparse(unquote_plus(h).replace("&amp;", "&")).query) for h in links]
        assert {"status": ["Open"]} in qs and {"priority": [pri]} in qs and {"category": [cat]} in qs
        listing = client.get([h for h in links if "category" in h][0]).data.decode()
        assert f"/tickets/{tid}" in listing and (f"/tickets/{3 - tid}" not in listing)
