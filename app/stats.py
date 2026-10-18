"""Dashboard numbers. Everything is computed from the tickets table with SQL."""
from .constants import CATEGORIES, OPEN_STATUSES, PRIORITIES
from .db import get_db, to_text, utcnow

_OPEN = ",".join("?" * len(OPEN_STATUSES))


def dashboard_stats() -> dict:
    db = get_db()
    now = to_text(utcnow())

    by_cat = {c: 0 for c in CATEGORIES}
    for r in db.execute(
        f"SELECT category, COUNT(*) n FROM tickets WHERE status IN ({_OPEN}) GROUP BY category",
        OPEN_STATUSES,
    ):
        by_cat[r["category"]] = r["n"]

    by_pri = {p: 0 for p in PRIORITIES}
    for r in db.execute(
        f"SELECT priority, COUNT(*) n FROM tickets WHERE status IN ({_OPEN}) GROUP BY priority",
        OPEN_STATUSES,
    ):
        by_pri[r["priority"]] = r["n"]

    # Average time to resolve, in hours, over tickets that have a resolved_at.
    # julianday() returns days, so multiply by 24.
    avg_all = db.execute(
        "SELECT AVG((julianday(resolved_at) - julianday(created_at)) * 24) h, COUNT(*) n "
        "FROM tickets WHERE resolved_at IS NOT NULL"
    ).fetchone()
    avg_by_cat = {c: None for c in CATEGORIES}
    for r in db.execute(
        "SELECT category, AVG((julianday(resolved_at) - julianday(created_at)) * 24) h "
        "FROM tickets WHERE resolved_at IS NOT NULL GROUP BY category"
    ):
        avg_by_cat[r["category"]] = r["h"]

    overdue = db.execute(
        f"SELECT COUNT(*) FROM tickets WHERE status IN ({_OPEN}) AND due_at < ?",
        [*OPEN_STATUSES, now],
    ).fetchone()[0]

    # SLA met = resolved on or before its due time.
    sla = db.execute(
        "SELECT SUM(resolved_at <= due_at) met, COUNT(*) n FROM tickets "
        "WHERE resolved_at IS NOT NULL"
    ).fetchone()

    total_open = sum(by_cat.values())
    return {
        "total_open": total_open,
        "total": db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0],
        "resolved_count": avg_all["n"],
        "overdue": overdue,
        "unassigned": db.execute(
            f"SELECT COUNT(*) FROM tickets WHERE assignee_id IS NULL AND status IN ({_OPEN})",
            OPEN_STATUSES,
        ).fetchone()[0],
        "by_category": by_cat,
        "by_priority": by_pri,
        "avg_hours_all": avg_all["h"],
        "avg_hours_by_category": avg_by_cat,
        "sla_met_pct": (100.0 * sla["met"] / sla["n"]) if sla["n"] else None,
    }
