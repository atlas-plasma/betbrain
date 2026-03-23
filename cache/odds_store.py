"""
Live odds storage.

Every time the pipeline fetches real Betway/bookmaker odds, we save them
to the historical_odds table so they can be used in future backtests.

Schema matches the existing SBRO data:
  date, home, away, home_ml, away_ml, ou_line, home_score, away_score, total, source
home_score / away_score / total are NULL until the game is settled.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List

DB_PATH = Path(__file__).parent.parent / "betbrain.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historical_odds (
            date        TEXT NOT NULL,
            home        TEXT NOT NULL,
            away        TEXT NOT NULL,
            home_ml     REAL,
            away_ml     REAL,
            ou_line     REAL,
            home_score  INTEGER,
            away_score  INTEGER,
            total       INTEGER,
            source      TEXT,
            PRIMARY KEY (date, home, away)
        )
    """)
    conn.commit()


def save_odds(date: str, home: str, away: str,
              home_ml: float, away_ml: float,
              ou_line: float, source: str = "betway_live") -> None:
    """
    Save live odds for a game. Skips if we already have an entry for this game
    (so the opening odds are preserved, not overwritten on every pipeline run).
    """
    try:
        with _connect() as conn:
            _ensure_table(conn)
            conn.execute("""
                INSERT INTO historical_odds (date, home, away, home_ml, away_ml, ou_line, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, home, away) DO UPDATE SET
                    home_ml  = COALESCE(excluded.home_ml,  historical_odds.home_ml),
                    away_ml  = COALESCE(excluded.away_ml,  historical_odds.away_ml),
                    ou_line  = COALESCE(excluded.ou_line,  historical_odds.ou_line),
                    source   = excluded.source
            """, (date, home, away, home_ml, away_ml, ou_line, source))
            conn.commit()
    except Exception as e:
        print(f"[odds_store] save error: {e}")


def settle_game(date: str, home: str, away: str,
                home_score: int, away_score: int) -> None:
    """
    Fill in the final score for a game once it's settled.
    Called by the auto-settler so future backtests have outcomes too.
    """
    total = home_score + away_score
    try:
        with _connect() as conn:
            _ensure_table(conn)
            conn.execute("""
                UPDATE historical_odds
                SET home_score=?, away_score=?, total=?
                WHERE date=? AND home=? AND away=?
            """, (home_score, away_score, total, date, home, away))
            conn.commit()
    except Exception as e:
        print(f"[odds_store] settle error: {e}")


def get_odds(date: str, home: str, away: str) -> Dict:
    """Retrieve stored odds for a specific game."""
    try:
        with _connect() as conn:
            _ensure_table(conn)
            row = conn.execute(
                "SELECT * FROM historical_odds WHERE date=? AND home=? AND away=?",
                (date, home, away)
            ).fetchone()
            if row:
                return dict(row)
    except Exception as e:
        print(f"[odds_store] get error: {e}")
    return {}


def count_stored() -> int:
    """Return total number of games with stored odds."""
    try:
        with _connect() as conn:
            _ensure_table(conn)
            return conn.execute("SELECT COUNT(*) FROM historical_odds WHERE source LIKE '%live%'").fetchone()[0]
    except Exception:
        return 0
