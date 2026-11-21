import sqlite3
from collections.abc import Generator
from pathlib import Path

from app.config import SCHEMA_PATH, SEED_MANAGERS, get_db_path


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str | None = None) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection(db_path)
    try:
        conn.executescript(schema_sql)
        count = conn.execute("SELECT COUNT(*) FROM managers").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO managers (name) VALUES (?)",
                [(name,) for name in SEED_MANAGERS],
            )
            conn.commit()
    finally:
        conn.close()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
