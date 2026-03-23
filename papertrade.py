"""
Paper Trading module for BetBrain
Stores all bets in betbrain.db (SQLite) so they survive Docker rebuilds.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Resolve DB path: prefer /data/betbrain.db (Docker volume) if it exists,
# otherwise fall back to the project root (local dev).
_DOCKER_DB = Path("/data/betbrain.db")
_LOCAL_DB  = Path(__file__).parent / "betbrain.db"
DB_PATH    = _DOCKER_DB if _DOCKER_DB.exists() else _LOCAL_DB

INITIAL_BANKROLL = 1000.0


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_bets (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT    NOT NULL,
            match         TEXT    NOT NULL,
            market        TEXT    NOT NULL,
            pick          TEXT    DEFAULT '',
            opening_odds  REAL    NOT NULL,
            odds          REAL    NOT NULL,
            stake         REAL    NOT NULL,
            prediction    REAL    DEFAULT 0,
            reasoning     TEXT    DEFAULT '',
            status        TEXT    DEFAULT 'pending',
            profit        REAL    DEFAULT 0,
            closing_odds  REAL,
            clv           REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_bankroll (
            id       INTEGER PRIMARY KEY CHECK (id = 1),
            bankroll REAL NOT NULL
        )
    """)
    # Seed bankroll row if first run
    conn.execute("""
        INSERT OR IGNORE INTO paper_bankroll (id, bankroll) VALUES (1, ?)
    """, (INITIAL_BANKROLL,))
    conn.commit()


class PaperTrader:
    """Simulate betting without real money. Persists to SQLite."""

    def __init__(self, initial_bankroll: float = INITIAL_BANKROLL):
        self.initial_bankroll = initial_bankroll
        with _connect() as conn:
            _ensure_tables(conn)

    def _get_bankroll(self) -> float:
        with _connect() as conn:
            row = conn.execute("SELECT bankroll FROM paper_bankroll WHERE id=1").fetchone()
            return row["bankroll"] if row else self.initial_bankroll

    def _set_bankroll(self, conn: sqlite3.Connection, amount: float) -> None:
        conn.execute("UPDATE paper_bankroll SET bankroll=? WHERE id=1", (amount,))

    @property
    def bankroll(self) -> float:
        return self._get_bankroll()

    def place_bet(self, match: str, market: str, odds: float, stake: float,
                  prediction: float, reasoning: str = "", pick: str = "",
                  **kwargs) -> Dict:
        """Place a paper bet."""
        # pick may come as kwarg for backwards compat
        if not pick:
            pick = kwargs.get("pick", "")

        with _connect() as conn:
            _ensure_tables(conn)
            current = conn.execute("SELECT bankroll FROM paper_bankroll WHERE id=1").fetchone()["bankroll"]

            if stake > current:
                return {"error": "Insufficient bankroll"}

            new_bankroll = current - stake
            self._set_bankroll(conn, new_bankroll)

            cur = conn.execute("""
                INSERT INTO paper_bets
                    (timestamp, match, market, pick, opening_odds, odds, stake,
                     prediction, reasoning, status, profit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0)
            """, (datetime.now().isoformat(), match, market, pick,
                  odds, odds, stake, prediction, reasoning))
            conn.commit()

            return self._row_to_dict(conn.execute(
                "SELECT * FROM paper_bets WHERE id=?", (cur.lastrowid,)
            ).fetchone())

    def settle_bet(self, bet_id: int, won: bool, closing_odds: float = None) -> Dict:
        """Settle a bet after game result."""
        with _connect() as conn:
            _ensure_tables(conn)
            row = conn.execute(
                "SELECT * FROM paper_bets WHERE id=? AND status='pending'", (bet_id,)
            ).fetchone()

            if not row:
                return {"error": "Bet not found"}

            if won:
                profit = row["stake"] * (row["odds"] - 1)
            else:
                profit = -row["stake"]

            status = "won" if won else "lost"
            clv = None
            if closing_odds and closing_odds > 1:
                clv = round(row["opening_odds"] / closing_odds, 4)

            current = conn.execute("SELECT bankroll FROM paper_bankroll WHERE id=1").fetchone()["bankroll"]
            if won:
                self._set_bankroll(conn, current + row["stake"] + profit)

            conn.execute("""
                UPDATE paper_bets
                SET status=?, profit=?, closing_odds=?, clv=?
                WHERE id=?
            """, (status, profit, closing_odds, clv, bet_id))
            conn.commit()

            return self._row_to_dict(conn.execute(
                "SELECT * FROM paper_bets WHERE id=?", (bet_id,)
            ).fetchone())

    def get_status(self) -> Dict:
        """Get current paper trading status."""
        with _connect() as conn:
            _ensure_tables(conn)
            bankroll = conn.execute("SELECT bankroll FROM paper_bankroll WHERE id=1").fetchone()["bankroll"]
            rows = conn.execute("SELECT * FROM paper_bets").fetchall()
            bets = [self._row_to_dict(r) for r in rows]

        settled = [b for b in bets if b["status"] != "pending"]
        won  = sum(1 for b in settled if b["status"] == "won")
        lost = len(settled) - won
        total_profit = sum(b.get("profit", 0) for b in bets)

        clv_values = [b["clv"] for b in bets if b.get("clv") is not None]
        avg_clv = round(sum(clv_values) / len(clv_values), 4) if clv_values else None

        return {
            "bankroll":         round(bankroll, 2),
            "initial_bankroll": self.initial_bankroll,
            "total_profit":     round(total_profit, 2),
            "profit_pct":       round((total_profit / self.initial_bankroll) * 100, 2),
            "total_bets":       len(bets),
            "pending_bets":     sum(1 for b in bets if b["status"] == "pending"),
            "won":              won,
            "lost":             lost,
            "win_rate":         won / len(settled) if settled else 0,
            "avg_clv":          avg_clv,
            "clv_sample_size":  len(clv_values),
        }

    def get_pending_bets(self) -> List[Dict]:
        """Get all pending bets."""
        with _connect() as conn:
            _ensure_tables(conn)
            rows = conn.execute(
                "SELECT * FROM paper_bets WHERE status='pending' ORDER BY timestamp DESC"
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get_history(self, limit: int = 50) -> List[Dict]:
        """Get bet history, most recent first."""
        with _connect() as conn:
            _ensure_tables(conn)
            rows = conn.execute(
                "SELECT * FROM paper_bets ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def reset(self) -> None:
        """Reset paper trading — wipes all bets and restores bankroll."""
        with _connect() as conn:
            _ensure_tables(conn)
            conn.execute("DELETE FROM paper_bets")
            conn.execute("UPDATE paper_bankroll SET bankroll=? WHERE id=1", (self.initial_bankroll,))
            conn.commit()

    @staticmethod
    def _row_to_dict(row) -> Dict:
        if row is None:
            return {}
        d = dict(row)
        # Normalise field names to match old JSON format
        d.setdefault("opening_odds", d.get("odds"))
        return d


def get_paper_trader() -> PaperTrader:
    """Get a paper trader instance (backed by SQLite)."""
    return PaperTrader()
