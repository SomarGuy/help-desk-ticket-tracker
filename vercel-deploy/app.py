"""Vercel entrypoint (Flask zero-config looks for `app` in app.py).

Vercel's filesystem is read-only except /tmp, so the SQLite database lives in
/tmp/tickets.sqlite and is auto-seeded with SYNTHETIC sample tickets on cold
start. It is an ephemeral demo: state resets whenever the instance restarts.
"""
import os

from helpdesk import create_app
import seed

DB_PATH = "/tmp/tickets.sqlite"

if not os.path.exists(DB_PATH):
    seed.build(DB_PATH, 60, 42)   # same synthetic data as `python seed.py`

app = create_app({"DATABASE": DB_PATH})
