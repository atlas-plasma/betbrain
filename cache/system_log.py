"""
System log — records every scheduler action, pipeline run, error, and
bet placement attempt so there is always a full audit trail.
"""

import json
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

_DOCKER_DB = Path("/data/betbrain.db")
_LOCAL_DB  = Path(__file__).parent.parent / "betbrain.db"
DB_PATH    = _DOCKER_DB if _DOCKER_DB.exists() else _LOCAL_DB


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS system_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at  TEXT NOT NULL,
            level      TEXT NOT NULL,
            component  TEXT NOT NULL,
            message    TEXT NOT NULL,
            details    TEXT DEFAULT ''
        )
    """)
    conn.commit()


def log(level: str, component: str, message: str, details: str = "") -> None:
    """level: INFO | WARNING | ERROR"""
    now = datetime.now().isoformat(timespec="seconds")
    print(f"[{level}] [{component}] {message}" + (f" — {details[:120]}" if details else ""))
    try:
        with _connect() as conn:
            _ensure_table(conn)
            conn.execute(
                "INSERT INTO system_log (logged_at, level, component, message, details) VALUES (?,?,?,?,?)",
                (now, level, component, message, details)
            )
            conn.commit()
    except Exception as e:
        print(f"[system_log] write error: {e}")


def info(component: str, message: str, details: str = "") -> None:
    log("INFO", component, message, details)


def warning(component: str, message: str, details: str = "") -> None:
    log("WARNING", component, message, details)


def error(component: str, message: str, exc: Optional[Exception] = None) -> None:
    details = traceback.format_exc() if exc else ""
    log("ERROR", component, message, details)


def get_recent(hours: int = 24, limit: int = 200) -> List[Dict]:
    try:
        with _connect() as conn:
            _ensure_table(conn)
            rows = conn.execute("""
                SELECT * FROM system_log
                WHERE logged_at >= datetime('now', ?)
                ORDER BY logged_at DESC
                LIMIT ?
            """, (f"-{hours} hours", limit)).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[system_log] get error: {e}")
        return []


def get_for_date(date: str) -> List[Dict]:
    try:
        with _connect() as conn:
            _ensure_table(conn)
            rows = conn.execute("""
                SELECT * FROM system_log
                WHERE logged_at LIKE ?
                ORDER BY logged_at ASC
            """, (f"{date}%",)).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[system_log] get_for_date error: {e}")
        return []
