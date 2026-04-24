from pathlib import Path

from flask import Flask
from sqlalchemy import event, text

from app.config import DefaultConfig
from app.extensions import db
from app.routes.api import api_bp
from app.routes.pages import pages_bp
from app.services.sync_queue import ensure_default_sync_settings


_REGISTERED_SQLITE_ENGINES: set[int] = set()


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.from_object(DefaultConfig())
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{Path(app.instance_path) / 'app.db'}"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {
            "timeout": 30,
        }
    }

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    with app.app_context():
        register_sqlite_pragmas()
        db.create_all()
        ensure_sqlite_schema_updates()
        ensure_default_sync_settings()

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)

    return app


def register_sqlite_pragmas() -> None:
    engine = db.engine

    if engine.url.drivername != "sqlite":
        return

    engine_id = id(engine)
    if engine_id in _REGISTERED_SQLITE_ENGINES:
        return

    event.listen(engine, "connect", apply_sqlite_pragmas)
    _REGISTERED_SQLITE_ENGINES.add(engine_id)


def apply_sqlite_pragmas(dbapi_connection, connection_record):  # pragma: no cover - SQLAlchemy hook
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def ensure_sqlite_schema_updates() -> None:
    engine = db.engine
    if engine.url.drivername != "sqlite":
        return

    existing_columns = {
        row[1]
        for row in db.session.execute(text("PRAGMA table_info(sync_jobs)")).all()
    }
    column_definitions = {
        "timeout_applies": "ALTER TABLE sync_jobs ADD COLUMN timeout_applies BOOLEAN NOT NULL DEFAULT 1",
        "total_items": "ALTER TABLE sync_jobs ADD COLUMN total_items INTEGER NOT NULL DEFAULT 0",
        "remaining_items": "ALTER TABLE sync_jobs ADD COLUMN remaining_items INTEGER NOT NULL DEFAULT 0",
    }

    for column_name, statement in column_definitions.items():
        if column_name not in existing_columns:
            db.session.execute(text(statement))

    db.session.commit()
