"""
Backtest result cache backed by SQLite.

Cache key: (strategy, start_date, end_date)
On hit  : returns persisted results instantly — no recompute.
On miss : caller runs the backtest, then calls save() to persist.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

DB_PATH = Path(__file__).parent.parent / "betbrain.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy    TEXT    NOT NULL,
            start_date  TEXT    NOT NULL,
            end_date    TEXT    NOT NULL,
            run_at      TEXT    NOT NULL,
            results     TEXT    NOT NULL,   -- JSON blob
            UNIQUE(strategy, start_date, end_date)
        )
    """)
    conn.commit()


def load(strategy: str, start_date: str, end_date: str) -> Optional[Dict]:
    """Return cached results or None if not found."""
    try:
        with _connect() as conn:
            _ensure_table(conn)
            row = conn.execute(
                "SELECT results, run_at FROM backtest_runs "
                "WHERE strategy=? AND start_date=? AND end_date=?",
                (strategy, start_date, end_date),
            ).fetchone()
            if row:
                data = json.loads(row["results"])
                data["_cached"] = True
                data["_cached_at"] = row["run_at"]
                return data
    except Exception as e:
        print(f"[cache] load error: {e}")
    return None


def save(strategy: str, start_date: str, end_date: str, data: Dict) -> None:
    """Persist backtest results, replacing any prior run for the same key."""
    try:
        # Don't store cache-metadata fields in the DB
        clean = {k: v for k, v in data.items() if not k.startswith("_cached")}
        with _connect() as conn:
            _ensure_table(conn)
            conn.execute(
                """
                INSERT INTO backtest_runs (strategy, start_date, end_date, run_at, results)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(strategy, start_date, end_date)
                DO UPDATE SET run_at=excluded.run_at, results=excluded.results
                """,
                (strategy, start_date, end_date,
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 json.dumps(clean)),
            )
            conn.commit()
    except Exception as e:
        print(f"[cache] save error: {e}")


def list_runs() -> list:
    """Return summary of all cached runs (for display in the UI)."""
    try:
        with _connect() as conn:
            _ensure_table(conn)
            rows = conn.execute(
                "SELECT strategy, start_date, end_date, run_at "
                "FROM backtest_runs ORDER BY run_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        print(f"[cache] list error: {e}")
    return []


def delete(strategy: str, start_date: str, end_date: str) -> None:
    """Remove a specific cached run."""
    try:
        with _connect() as conn:
            _ensure_table(conn)
            conn.execute(
                "DELETE FROM backtest_runs WHERE strategy=? AND start_date=? AND end_date=?",
                (strategy, start_date, end_date),
            )
            conn.commit()
    except Exception as e:
        print(f"[cache] delete error: {e}")
