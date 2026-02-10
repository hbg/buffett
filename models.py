from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Holding:
    ticker: str
    shares: float
    cost_basis: float
    added_at: str = ""


@dataclass
class PriceData:
    ticker: str
    current_price: float
    previous_close: float
    day_change_pct: float


@dataclass
class Suggestion:
    id: Optional[int] = None
    ticker: str = ""
    action: str = ""          # BUY or SELL
    confidence: str = ""      # HIGH, MEDIUM, LOW
    target_price: float = 0.0
    reasoning: str = ""
    created_at: str = ""
    status: str = "OPEN"      # OPEN, HIT, EXPIRED
    entry_price: float = 0.0
    resolved_price: Optional[float] = None
    resolved_at: Optional[str] = None
    timeframe_days: int = 7


@dataclass
class Briefing:
    id: Optional[int] = None
    date: str = ""
    content: str = ""
    portfolio_value: float = 0.0
    daily_change_pct: Optional[float] = None
    suggestion_count: int = 0
    created_at: str = ""


@dataclass
class HoldingSnapshot:
    ticker: str
    shares: float
    price: float
    value: float
    day_change_pct: float
    briefing_id: Optional[int] = None
