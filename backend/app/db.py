from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from sqlmodel import SQLModel, Session, create_engine


DEFAULT_DB_PATH = Path(os.getenv("FIGMAQA_DB_PATH", "./data/figmaqa.db")).resolve()
DEFAULT_DB_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DEFAULT_DB_PATH}"

_is_sqlite = DEFAULT_DB_URL.startswith("sqlite")
engine = create_engine(
    DEFAULT_DB_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    echo=False,
)


def init_db() -> None:
    if _is_sqlite:
        DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
