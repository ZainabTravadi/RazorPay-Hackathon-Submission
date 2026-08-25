from __future__ import annotations

from sqlalchemy import inspect, text

from database.base import Base
from database.session import engine
from database.models import *  # noqa: F401,F403


def _migrate_sqlite_recovery_schema() -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "recovery_executions" in table_names:
            recovery_columns = {column["name"] for column in inspector.get_columns("recovery_executions")}
            for column_name, ddl in {
                "status": "VARCHAR(32) NOT NULL DEFAULT 'pending'",
            }.items():
                if column_name not in recovery_columns:
                    connection.execute(text(f"ALTER TABLE recovery_executions ADD COLUMN {column_name} {ddl}"))


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_recovery_schema()


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
