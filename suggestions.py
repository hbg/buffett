from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from models import PriceData, Suggestion

logger = logging.getLogger(__name__)


def resolve_open_suggestions(prices: Dict[str, PriceData]) -> None:
    from db import expire_suggestion, get_open_suggestions, resolve_suggestion

    open_sug = get_open_suggestions()
    now = datetime.now()

    for s in open_sug:
        price_data = prices.get(s.ticker)
        if not price_data:
            continue

        current = price_data.current_price
        created = datetime.fromisoformat(s.created_at)
        deadline = created + timedelta(days=s.timeframe_days)

        # Check if target hit (directional)
        hit = False
        if s.action == "BUY" and current >= s.target_price:
            hit = True
        elif s.action == "SELL" and current <= s.target_price:
            hit = True

        if hit:
            resolve_suggestion(s.id, "HIT", current)
            logger.info("Suggestion %d (%s %s) HIT at %.2f", s.id, s.action, s.ticker, current)
        elif now >= deadline:
            expire_suggestion(s.id, current)
            logger.info("Suggestion %d (%s %s) EXPIRED at %.2f", s.id, s.action, s.ticker, current)


def compute_pnl(s: Suggestion) -> Optional[float]:
    if s.resolved_price is None:
        return None
    if s.action == "BUY":
        return s.resolved_price - s.entry_price
    else:  # SELL
        return s.entry_price - s.resolved_price


def scorecard(suggestions: List[Suggestion]) -> Dict:
    resolved = [s for s in suggestions if s.status in ("HIT", "EXPIRED")]
    if not resolved:
        return {
            "total": len(suggestions),
            "open": len([s for s in suggestions if s.status == "OPEN"]),
            "resolved": 0,
            "hit_rate": 0.0,
            "avg_pnl": 0.0,
            "best": None,
            "worst": None,
            "by_confidence": {},
        }

    pnls = []
    for s in resolved:
        pnl = compute_pnl(s)
        if pnl is not None:
            pnls.append((s, pnl))

    pnls.sort(key=lambda x: x[1], reverse=True)
    hits = [s for s in resolved if s.status == "HIT"]

    # Breakdown by confidence
    by_confidence: Dict[str, Dict] = {}
    for conf in ("HIGH", "MEDIUM", "LOW"):
        conf_resolved = [s for s in resolved if s.confidence == conf]
        conf_hits = [s for s in conf_resolved if s.status == "HIT"]
        conf_pnls = [compute_pnl(s) for s in conf_resolved if compute_pnl(s) is not None]
        if conf_resolved:
            by_confidence[conf] = {
                "count": len(conf_resolved),
                "hit_rate": len(conf_hits) / len(conf_resolved) * 100,
                "avg_pnl": sum(conf_pnls) / len(conf_pnls) if conf_pnls else 0.0,
            }

    avg_pnl = sum(p for _, p in pnls) / len(pnls) if pnls else 0.0

    return {
        "total": len(suggestions),
        "open": len([s for s in suggestions if s.status == "OPEN"]),
        "resolved": len(resolved),
        "hit_rate": len(hits) / len(resolved) * 100 if resolved else 0.0,
        "avg_pnl": round(avg_pnl, 2),
        "best": _format_call(pnls[0]) if pnls else None,
        "worst": _format_call(pnls[-1]) if pnls else None,
        "by_confidence": by_confidence,
    }


def _format_call(entry: tuple) -> Dict:
    s, pnl = entry
    return {
        "ticker": s.ticker,
        "action": s.action,
        "pnl": round(pnl, 2),
        "status": s.status,
    }
