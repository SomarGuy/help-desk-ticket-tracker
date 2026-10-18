"""All routes: queue, overview, ticket list/search, create, detail, update, notes."""
from datetime import timedelta

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for)

from .constants import (CATEGORIES, DONE_STATUSES, OPEN_STATUSES, PRIORITIES,
                        STATUSES, sla_delta)
from .db import from_text, get_db, to_text, utcnow
from .stats import dashboard_stats

bp = Blueprint("main", __name__)

# SELECT used by both the list and the detail page.
TICKET_SELECT = (
    "SELECT t.*, te.name AS assignee FROM tickets t "
    "LEFT JOIN technicians te ON te.id = t.assignee_id"
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def technicians():
    return get_db().execute("SELECT id, name FROM technicians ORDER BY name").fetchall()


def add_note(ticket_id: int, author: str, kind: str, body: str) -> None:
    """Append an entry to the ticket's resolution log."""
    get_db().execute(
        "INSERT INTO notes (ticket_id, author, kind, body, created_at) VALUES (?,?,?,?,?)",
        (ticket_id, author, kind, body, to_text(utcnow())),
    )


def get_ticket_or_404(ticket_id: int):
    row = get_db().execute(TICKET_SELECT + " WHERE t.id = ?", (ticket_id,)).fetchone()
    if row is None:
        abort(404)
    return row


def parse_assignee(raw: str | None):
    """Return an int technician id, None for 'unassigned', or raise ValueError."""
    if not raw:
        return None
    tid = int(raw)
    found = get_db().execute("SELECT 1 FROM technicians WHERE id = ?", (tid,)).fetchone()
    if not found:
        raise ValueError("Unknown technician")
    return tid


def sla_state(ticket) -> str:
    """'met' / 'breached' for finished tickets, 'overdue' / 'ok' for open ones."""
    if ticket["resolved_at"]:
        return "met" if ticket["resolved_at"] <= ticket["due_at"] else "breached"
    return "overdue" if ticket["due_at"] < to_text(utcnow()) else "ok"


def time_left(ticket) -> str:
    """Human-readable time until/after the SLA due time for an open ticket."""
    delta = from_text(ticket["due_at"]) - utcnow()
    mins = int(abs(delta.total_seconds()) // 60)
    text = f"{mins // 60}h {mins % 60:02d}m" if mins < 60 * 48 else f"{mins // 1440}d"
    return f"{text} overdue" if delta < timedelta(0) else f"{text} left"


def fragment() -> str:
    """'' for a normal page; '1' or 'list' when the page's JavaScript asks for just a piece of it."""
    return request.values.get("fragment", "")


def frag_args() -> dict:
    """Carry the fragment flag through a redirect so the JavaScript gets a fragment back."""
    return {"fragment": fragment()} if fragment() else {}


def render_workspace(panel=None, **ctx):
    """Render the queue with an optional ticket panel beside it, or just the requested fragment."""
    return render_template("workspace.html", panel=panel, **ctx)


# --------------------------------------------------------------------------
# overview (the numbers)
# --------------------------------------------------------------------------
@bp.route("/overview")
def dashboard():
    return render_template("dashboard.html", s=dashboard_stats())


# --------------------------------------------------------------------------
# the queue: list + search/filter
# --------------------------------------------------------------------------
def queue_context(default_status: str = "") -> dict:
    """Run the search/filter from the query string and return what the queue templates need."""
    q = request.args.get("q", "").strip()
    status = request.args.get("status", default_status)
    category = request.args.get("category", "")
    priority = request.args.get("priority", "")
    assignee = request.args.get("assignee", "")
    overdue = request.args.get("overdue") == "1"

    where, params = [], []
    if q:
        # Search title, description, requester and ticket number.
        like = f"%{q}%"
        where.append("(t.title LIKE ? OR t.description LIKE ? OR t.requester LIKE ? "
                     "OR CAST(t.id AS TEXT) = ?)")
        params += [like, like, like, q.lstrip("#")]
    if status == "active":                       # pseudo-status: everything not done
        where.append(f"t.status IN ({','.join('?' * len(OPEN_STATUSES))})")
        params += OPEN_STATUSES
    elif status in STATUSES:
        where.append("t.status = ?")
        params.append(status)
    if category in CATEGORIES:
        where.append("t.category = ?")
        params.append(category)
    if priority in PRIORITIES:
        where.append("t.priority = ?")
        params.append(priority)
    if assignee == "none":
        where.append("t.assignee_id IS NULL")
    elif assignee.isdigit():
        where.append("t.assignee_id = ?")
        params.append(int(assignee))
    if overdue:
        where.append(f"t.status IN ({','.join('?' * len(OPEN_STATUSES))}) AND t.due_at < ?")
        params += OPEN_STATUSES + [to_text(utcnow())]

    sql = TICKET_SELECT + (" WHERE " + " AND ".join(where) if where else "")
    # Open tickets first, most urgent SLA first; finished tickets after, newest first.
    sql += (" ORDER BY CASE WHEN t.status IN ('Resolved','Closed') THEN 1 ELSE 0 END, "
            "CASE WHEN t.status IN ('Resolved','Closed') THEN '' ELSE t.due_at END, "
            "t.created_at DESC")
    rows = get_db().execute(sql, params).fetchall()
    tickets = [dict(r, sla=sla_state(r), left=None if r["resolved_at"] else time_left(r))
               for r in rows]
    f = dict(q=q, status=status, category=category, priority=priority,
             assignee=assignee, overdue=overdue)
    narrowed = sum(bool(v) for k, v in f.items() if k not in ("q", "status")) + (
        1 if status not in ("", "active") else 0)
    return dict(tickets=tickets, technicians=technicians(), f=f, narrowed=narrowed,
                past_due=sum(t["sla"] == "overdue" for t in tickets),
                queue_url=request.path if request.path in ("/", "/tickets") else url_for("main.queue"))


def show_queue(default_status: str):
    ctx = queue_context(default_status)
    if fragment() == "list":
        return render_template("_queue.html", selected_id=None, **ctx)
    return render_workspace(selected_id=None, **ctx)


@bp.route("/")
def queue():
    """Home page: the queue of tickets that are not finished yet."""
    return show_queue("active")


@bp.route("/tickets")
def ticket_list():
    """The same queue, with every status unless the URL says otherwise."""
    return show_queue("")


# --------------------------------------------------------------------------
# create
# --------------------------------------------------------------------------
@bp.route("/tickets/new", methods=["GET", "POST"])
def ticket_new():
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        title = form.get("title", "").strip()
        requester = form.get("requester", "").strip()
        category, priority = form.get("category"), form.get("priority")
        errors = []
        if not title:
            errors.append("Title is required.")
        if not requester:
            errors.append("Requester name is required.")
        if category not in CATEGORIES:
            errors.append("Choose a valid category.")
        if priority not in PRIORITIES:
            errors.append("Choose a valid priority.")
        try:
            assignee_id = parse_assignee(form.get("assignee_id"))
        except ValueError:
            errors.append("Choose a valid technician.")
            assignee_id = None
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            now = utcnow()
            db = get_db()
            cur = db.execute(
                "INSERT INTO tickets (title, description, requester, category, priority, "
                "status, assignee_id, created_at, updated_at, due_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (title, form.get("description", "").strip(), requester, category, priority,
                 "Open", assignee_id, to_text(now), to_text(now),
                 to_text(now + sla_delta(priority))))
            add_note(cur.lastrowid, "System", "change",
                     f"Ticket created ({priority} priority, SLA due in "
                     f"{int(sla_delta(priority).total_seconds() // 3600)}h).")
            db.commit()
            flash(f"Ticket #{cur.lastrowid} created.", "ok")
            return redirect(url_for("main.ticket_detail", ticket_id=cur.lastrowid, **frag_args()))
    if fragment():
        return render_template("_new.html", form=form, technicians=technicians(),
                               queue_url=url_for("main.queue"))
    return render_workspace(panel="new", form=form, selected_id=None,
                            **queue_context("active"))


# --------------------------------------------------------------------------
# detail + update + notes
# --------------------------------------------------------------------------
@bp.route("/tickets/<int:ticket_id>")
def ticket_detail(ticket_id: int):
    t = get_ticket_or_404(ticket_id)
    notes = get_db().execute(
        "SELECT * FROM notes WHERE ticket_id = ? ORDER BY created_at, id", (ticket_id,)
    ).fetchall()
    detail = dict(t=t, notes=notes, sla=sla_state(t),
                  left=None if t["resolved_at"] else time_left(t),
                  technicians=technicians(), queue_url=url_for("main.queue"))
    if fragment():
        return render_template("_detail.html", **detail)
    ctx = {**queue_context("active"), **detail, "selected_id": ticket_id}
    return render_workspace(panel="detail", **ctx)


@bp.route("/tickets/<int:ticket_id>/update", methods=["POST"])
def ticket_update(ticket_id: int):
    """Change status / priority / assignee. Resolving requires a resolution note."""
    t = get_ticket_or_404(ticket_id)
    db = get_db()
    form = request.form
    author = form.get("author", "").strip() or "Technician"
    status, priority = form.get("status", t["status"]), form.get("priority", t["priority"])
    resolution = form.get("resolution", "").strip()

    if status not in STATUSES or priority not in PRIORITIES:
        abort(400)
    try:
        assignee_id = parse_assignee(form.get("assignee_id"))
    except ValueError:
        abort(400)

    now = utcnow()
    changes, sets, params = [], [], []
    redirect_to = redirect(url_for("main.ticket_detail", ticket_id=ticket_id, **frag_args()))

    if status in DONE_STATUSES and not (resolution or t["resolution"]):
        flash("Add a resolution summary before resolving or closing a ticket.", "error")
        return redirect_to

    if priority != t["priority"]:
        # Re-calculate the SLA due time from the ticket's creation time.
        new_due = from_text(t["created_at"]) + sla_delta(priority)
        sets += ["priority = ?", "due_at = ?"]
        params += [priority, to_text(new_due)]
        changes.append(f"Priority {t['priority']} -> {priority} "
                       f"(SLA due now {to_text(new_due).replace('T', ' ')} UTC)")

    if assignee_id != t["assignee_id"]:
        name = db.execute("SELECT name FROM technicians WHERE id = ?", (assignee_id,)).fetchone()
        sets.append("assignee_id = ?")
        params.append(assignee_id)
        changes.append(f"Assigned to {name['name'] if name else 'nobody (unassigned)'}")

    if status != t["status"]:
        sets.append("status = ?")
        params.append(status)
        changes.append(f"Status {t['status']} -> {status}")
        if status in DONE_STATUSES and t["resolved_at"] is None:
            sets.append("resolved_at = ?")
            params.append(to_text(now))
        elif status not in DONE_STATUSES and t["resolved_at"] is not None:
            sets.append("resolved_at = NULL")            # ticket reopened
            changes.append("Ticket reopened")

    if status in DONE_STATUSES and resolution and resolution != (t["resolution"] or ""):
        sets.append("resolution = ?")
        params.append(resolution)
        add_note(ticket_id, author, "resolution", resolution)

    if sets:
        sets.append("updated_at = ?")
        params += [to_text(now), ticket_id]
        db.execute(f"UPDATE tickets SET {', '.join(sets)} WHERE id = ?", params)
        for c in changes:
            add_note(ticket_id, author, "change", c)
        db.commit()
        flash("Ticket updated.", "ok")
    else:
        flash("No changes to save.", "ok")
    return redirect_to


@bp.route("/tickets/<int:ticket_id>/notes", methods=["POST"])
def note_add(ticket_id: int):
    get_ticket_or_404(ticket_id)
    body = request.form.get("body", "").strip()
    author = request.form.get("author", "").strip() or "Technician"
    if not body:
        flash("A note can't be empty.", "error")
    else:
        add_note(ticket_id, author, "note", body)
        get_db().execute("UPDATE tickets SET updated_at = ? WHERE id = ?",
                         (to_text(utcnow()), ticket_id))
        get_db().commit()
        flash("Note added.", "ok")
    return redirect(url_for("main.ticket_detail", ticket_id=ticket_id, **frag_args()))
