"""SQLite connection lifecycle for the Rockwall database."""
from pathlib import Path
import sqlite3

DATABASE_PATH = Path(__file__).resolve().parents[1] / "schema/rockwall.db"


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def get_capacity() -> tuple[int, int]:
    row = get_connection().execute("SELECT v FROM settings WHERE k='capacity'").fetchone()
    return tuple(map(int, row["v"].split("/")))


def set_capacity(active: int, maxv: int) -> None:
    c = get_connection()
    c.execute("UPDATE settings SET v=? WHERE k='capacity'", (f"{active}/{maxv}",))
    c.commit()
    c.close()
