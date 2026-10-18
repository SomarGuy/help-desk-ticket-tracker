"""Help Desk Ticket Tracker - Flask application factory."""
import os
from datetime import datetime

from flask import Flask

from . import db
from .constants import CATEGORIES, DONE_STATUSES, PRIORITIES, STATUSES


def create_app(test_config: dict | None = None) -> Flask:
    """Build the Flask app. Tests pass `test_config` to use a temporary database."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.path.join(app.instance_path, "tickets.sqlite"),
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)

    app.teardown_appcontext(db.close_db)

    from .views import bp
    app.register_blueprint(bp)

    # ---- template helpers ---------------------------------------------
    @app.template_filter("dt")
    def fmt_dt(value: str | None) -> str:
        """'2026-03-02T14:05:00' -> 'Mar 2, 14:05'. Times are UTC."""
        if not value:
            return "-"
        d = datetime.strptime(value, db.TIME_FORMAT)
        return f"{d.strftime('%b')} {d.day}, {d:%H:%M}"

    @app.template_filter("hours")
    def fmt_hours(value: float | None) -> str:
        if value is None:
            return "n/a"
        return f"{value:.1f} h"

    @app.context_processor
    def inject_constants():
        return dict(CATEGORIES=CATEGORIES, PRIORITIES=PRIORITIES, STATUSES=STATUSES,
                    DONE_STATUSES=DONE_STATUSES, now_text=db.to_text(db.utcnow()))

    return app
