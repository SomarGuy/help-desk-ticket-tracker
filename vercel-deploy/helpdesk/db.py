"""Tiny SQLite helper layer: connection per request, schema creation, time helpers."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

SCHEMA = Path(__file__).with_name("schema.sql")
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (seconds precision)."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def to_text(dt: datetime) -> str:
    return dt.strftime(TIME_FORMAT)


def from_text(text: str) -> datetime:
    return datetime.strptime(text, TIME_FORMAT)


def get_db() -> sqlite3.Connection:
    """Open (once per request) the SQLite connection. Rows behave like dicts."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(path: str) -> None:
    """Create (or reset!) all tables in the database file at `path`."""
    con = sqlite3.connect(path)
    con.executescript(SCHEMA.read_text())
    con.commit()
    con.close()
