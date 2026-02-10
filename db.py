from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import List, Optional

from models import Briefing, Holding, HoldingSnapshot, Suggestion


def _connect() -> sqlite3.Connection:
    from config import DB_PATH

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS holdings (
            ticker TEXT PRIMARY KEY,
            shares REAL NOT NULL,
            cost_basis REAL NOT NULL,
            added_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            action TEXT NOT NULL,
            confidence TEXT NOT NULL,
            target_price REAL NOT NULL,
            reasoning TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            entry_price REAL NOT NULL,
            resolved_price REAL,
            resolved_at TEXT,
            timeframe_days INTEGER NOT NULL DEFAULT 7
        );

        CREATE TABLE IF NOT EXISTS briefings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            content TEXT NOT NULL,
            portfolio_value REAL NOT NULL,
            daily_change_pct REAL,
            suggestion_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS holding_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            briefing_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            price REAL NOT NULL,
            value REAL NOT NULL,
            day_change_pct REAL NOT NULL,
            FOREIGN KEY (briefing_id) REFERENCES briefings(id)
        );
        """
    )
    conn.commit()
    conn.close()


# ── Holdings ──────────────────────────────────────────────────────────

def add_holding(ticker: str, shares: float, cost_basis: float) -> None:
    conn = _connect()
    now = datetime.now().isoformat()
    # Weighted average cost basis on conflict
    conn.execute(
        """
        INSERT INTO holdings (ticker, shares, cost_basis, added_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            cost_basis = (holdings.cost_basis * holdings.shares + excluded.cost_basis * excluded.shares)
                         / (holdings.shares + excluded.shares),
            shares = holdings.shares + excluded.shares
        """,
        (ticker.upper(), shares, cost_basis, now),
    )
    conn.commit()
    conn.close()


def get_holdings() -> List[Holding]:
    conn = _connect()
    rows = conn.execute("SELECT ticker, shares, cost_basis, added_at FROM holdings ORDER BY ticker").fetchall()
    conn.close()
    return [Holding(ticker=r["ticker"], shares=r["shares"], cost_basis=r["cost_basis"], added_at=r["added_at"]) for r in rows]


def remove_holding(ticker: str) -> bool:
    conn = _connect()
    cur = conn.execute("DELETE FROM holdings WHERE ticker = ?", (ticker.upper(),))
    conn.commit()
    removed = cur.rowcount > 0
    conn.close()
    return removed


# ── Snapshots ─────────────────────────────────────────────────────────

def save_snapshots(snapshots: List[HoldingSnapshot], briefing_id: int) -> None:
    conn = _connect()
    conn.executemany(
        """
        INSERT INTO holding_snapshots (briefing_id, ticker, shares, price, value, day_change_pct)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [(briefing_id, s.ticker, s.shares, s.price, s.value, s.day_change_pct) for s in snapshots],
    )
    conn.commit()
    conn.close()


# ── Suggestions ───────────────────────────────────────────────────────

def save_suggestion(s: Suggestion) -> int:
    conn = _connect()
    cur = conn.execute(
        """
        INSERT INTO suggestions (ticker, action, confidence, target_price, reasoning,
                                 created_at, status, entry_price, timeframe_days)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (s.ticker, s.action, s.confidence, s.target_price, s.reasoning,
         s.created_at, s.status, s.entry_price, s.timeframe_days),
    )
    conn.commit()
    suggestion_id = cur.lastrowid
    conn.close()
    return suggestion_id  # type: ignore[return-value]


def get_open_suggestions() -> List[Suggestion]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM suggestions WHERE status = 'OPEN' ORDER BY created_at DESC").fetchall()
    conn.close()
    return [_row_to_suggestion(r) for r in rows]


def get_all_suggestions() -> List[Suggestion]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM suggestions ORDER BY created_at DESC").fetchall()
    conn.close()
    return [_row_to_suggestion(r) for r in rows]


def resolve_suggestion(suggestion_id: int, status: str, resolved_price: float) -> None:
    conn = _connect()
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE suggestions SET status = ?, resolved_price = ?, resolved_at = ? WHERE id = ?",
        (status, resolved_price, now, suggestion_id),
    )
    conn.commit()
    conn.close()


def expire_suggestion(suggestion_id: int, current_price: float) -> None:
    resolve_suggestion(suggestion_id, "EXPIRED", current_price)


# ── Briefings ─────────────────────────────────────────────────────────

def save_briefing(b: Briefing) -> int:
    conn = _connect()
    cur = conn.execute(
        """
        INSERT INTO briefings (date, content, portfolio_value, daily_change_pct, suggestion_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (b.date, b.content, b.portfolio_value, b.daily_change_pct, b.suggestion_count, b.created_at),
    )
    conn.commit()
    briefing_id = cur.lastrowid
    conn.close()
    return briefing_id  # type: ignore[return-value]


def get_previous_day_value() -> Optional[float]:
    conn = _connect()
    row = conn.execute(
        "SELECT portfolio_value FROM briefings ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        return row["portfolio_value"]
    return None


# ── Helpers ───────────────────────────────────────────────────────────

def _row_to_suggestion(r: sqlite3.Row) -> Suggestion:
    return Suggestion(
        id=r["id"],
        ticker=r["ticker"],
        action=r["action"],
        confidence=r["confidence"],
        target_price=r["target_price"],
        reasoning=r["reasoning"],
        created_at=r["created_at"],
        status=r["status"],
        entry_price=r["entry_price"],
        resolved_price=r["resolved_price"],
        resolved_at=r["resolved_at"],
        timeframe_days=r["timeframe_days"],
    )
