"""Shared pytest fixtures: every test gets its own empty temporary database."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app          # noqa: E402
from app.db import init_db          # noqa: E402


@pytest.fixture()
def app(tmp_path):
    db_path = str(tmp_path / "test.sqlite")
    init_db(db_path)
    app = create_app({"TESTING": True, "DATABASE": db_path})
    import sqlite3
    con = sqlite3.connect(db_path)
    con.executemany("INSERT INTO technicians (name) VALUES (?)", [("Tech One",), ("Tech Two",)])
    con.commit()
    con.close()
    return app


@pytest.fixture()
def client(app):
    return app.test_client()
