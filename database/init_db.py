from __future__ import annotations

from database.base import Base
from database.session import engine
from database.models import *  # noqa: F401,F403


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
