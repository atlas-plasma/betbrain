"""
Inference log — stores every game the pipeline analyses so you can see
what the model decided even when no bet was placed.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set

_DOCKER_DB = Path("/data/betbrain.db")
_LOCAL_DB  = Path(__file__).parent.parent / "betbrain.db"
DB_PATH    = _DOCKER_DB if _DOCKER_DB.exists() else _LOCAL_DB


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inference_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at    TEXT NOT NULL,
            game_date    TEXT NOT NULL,
            match        TEXT NOT NULL,
            start_time   TEXT DEFAULT '',
            market       TEXT NOT NULL,
            pick         TEXT DEFAULT '',
            odds         REAL DEFAULT 0,
            model_prob   REAL DEFAULT 0,
            implied_prob REAL DEFAULT 0,
            edge         REAL DEFAULT 0,
            should_bet   INTEGER DEFAULT 0,
            bet_placed   INTEGER DEFAULT 0,
            odds_source  TEXT DEFAULT '',
            details      TEXT DEFAULT '{}'
        )
    """)
    # Add details column if upgrading from old schema
    try:
        conn.execute("ALTER TABLE inference_log ADD COLUMN details TEXT DEFAULT '{}'")
    except Exception:
        pass
    conn.commit()


def log_inference(opportunities: List[Dict], placed_keys: Set[tuple]) -> None:
    """
    Log all analysed opportunities.
    placed_keys = set of (match, market) tuples where a bet was actually placed.
    One row per market per match. Stores full agent votes + reasoning in details JSON.
    """
    if not opportunities:
        return

    # Build per-match details once (agent votes, reasoning, score pred, etc.)
    match_details: Dict[str, dict] = {}
    for o in opportunities:
        m = o.get("match", "")
        if m not in match_details:
            match_details[m] = {
                "score_pred":    o.get("score_pred", ""),
                "pred_total":    o.get("pred_total", 0),
                "ou_line":       o.get("ou_line", 6.5),
                "confidence":    o.get("confidence", ""),
                "home_pdo":      o.get("home_pdo", 100),
                "away_pdo":      o.get("away_pdo", 100),
                "home_b2b":      o.get("home_b2b", False),
                "away_b2b":      o.get("away_b2b", False),
                "home_goalie":   o.get("home_goalie", ""),
                "away_goalie":   o.get("away_goalie", ""),
                "home_goalie_sv": o.get("home_goalie_sv", 0),
                "away_goalie_sv": o.get("away_goalie_sv", 0),
                "agent_votes":   o.get("agent_votes", []),
                "reasoning":     o.get("reasoning", ""),
                "vote_summary":  o.get("vote_summary", ""),
            }

    now = datetime.now().isoformat()
    rows = []
    seen: Set[tuple] = set()
    for o in opportunities:
        key = (o.get("match", ""), o.get("market", ""))
        if key in seen:
            continue
        seen.add(key)
        details_json = json.dumps(match_details.get(o.get("match", ""), {}))
        rows.append((
            now,
            o.get("date", ""),
            o.get("match", ""),
            o.get("start_time", ""),
            o.get("market", ""),
            o.get("win_pick", ""),
            o.get("odds", 0),
            o.get("model_prob", 0),
            o.get("implied_prob", 0),
            o.get("edge", 0),
            1 if o.get("should_bet") else 0,
            1 if key in placed_keys else 0,
            o.get("odds_source", ""),
            details_json,
        ))
    try:
        with _connect() as conn:
            _ensure_table(conn)
            conn.executemany("""
                INSERT INTO inference_log
                    (logged_at, game_date, match, start_time, market, pick,
                     odds, model_prob, implied_prob, edge, should_bet, bet_placed,
                     odds_source, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            conn.commit()
    except Exception as e:
        print(f"[inference_log] error: {e}")


def get_for_date(date: str) -> List[Dict]:
    """Return all inference entries for a specific game_date (YYYY-MM-DD)."""
    try:
        with _connect() as conn:
            _ensure_table(conn)
            rows = conn.execute("""
                SELECT * FROM inference_log
                WHERE game_date = ?
                ORDER BY match, market
            """, (date,)).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["details"] = json.loads(d.get("details") or "{}")
                except Exception:
                    d["details"] = {}
                result.append(d)
            return result
    except Exception as e:
        print(f"[inference_log] get_for_date error: {e}")
        return []


def get_recent(hours: int = 24, limit: int = 100) -> List[Dict]:
    """Return recent inference entries, most recent first."""
    try:
        with _connect() as conn:
            _ensure_table(conn)
            rows = conn.execute("""
                SELECT * FROM inference_log
                WHERE logged_at >= datetime('now', ?)
                ORDER BY logged_at DESC, match, market
                LIMIT ?
            """, (f"-{hours} hours", limit)).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["details"] = json.loads(d.get("details") or "{}")
                except Exception:
                    d["details"] = {}
                result.append(d)
            return result
    except Exception as e:
        print(f"[inference_log] get error: {e}")
        return []
