from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from models import Holding, HoldingSnapshot, PriceData, Suggestion

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a professional portfolio analyst producing a daily email briefing. This runs as \
an automated daily job, so your analysis must be grounded in TODAY's news and market data. \
Search the web for the most recent information — prioritise news from the last 24 hours.

The user will provide their current holdings with price and performance data. Your job:

1. **Search the web** for today's news on each holding ticker and the broader market.
2. Produce a briefing with these sections:
   - **Market Overview** — brief macro summary based on today's market activity
   - **Holdings Analysis** — for each holding, summarise the latest news, price action, and near-term outlook
   - **Trade Suggestions** — actionable BUY/SELL ideas based on your analysis

PRIVACY RULE — this email could be intercepted. NEVER mention specific share counts, \
portfolio dollar values, cost basis, or P/L dollar amounts in your prose. You may discuss \
percentage changes, price targets, and general directional guidance. The user already knows \
their position sizes — focus on the analysis, not the numbers they gave you.

After your prose briefing, output a fenced JSON code block labelled ```json containing an \
array of suggestion objects. Each object must have exactly these fields:
  - "ticker": string (uppercase)
  - "action": "BUY" or "SELL"
  - "confidence": "HIGH", "MEDIUM", or "LOW"
  - "target_price": number
  - "reasoning": string (one sentence)
  - "timeframe_days": integer (default 7)

If you have no suggestions, output an empty array: ```json\n[]\n```

Do NOT include the JSON block inside the prose sections — keep it as a separate fenced block at the very end.\
"""


def analyze_portfolio(
    holdings: List[Holding],
    snapshots: List[HoldingSnapshot],
    prices: Dict[str, PriceData],
    portfolio_value: float,
    daily_change_pct: Optional[float],
) -> Tuple[str, List[Suggestion]]:
    user_msg = _build_user_message(holdings, snapshots, prices, portfolio_value, daily_change_pct)
    raw_response = _call_claude(user_msg)
    briefing_text, suggestions = _parse_response(raw_response, prices)
    return briefing_text, suggestions


def _build_user_message(
    holdings: List[Holding],
    snapshots: List[HoldingSnapshot],
    prices: Dict[str, PriceData],
    portfolio_value: float,
    daily_change_pct: Optional[float],
) -> str:
    lines = [
        f"Date: {datetime.now().strftime('%Y-%m-%d')}",
        f"Portfolio Value: ${portfolio_value:,.2f}",
    ]
    if daily_change_pct is not None:
        lines.append(f"Daily Change: {daily_change_pct:+.2f}%")

    lines.append("\nHoldings:")
    for h in holdings:
        p = prices.get(h.ticker)
        if not p:
            continue
        market_value = h.shares * p.current_price
        cost_total = h.shares * h.cost_basis
        pnl = market_value - cost_total
        pnl_pct = (pnl / cost_total) * 100 if cost_total else 0
        lines.append(
            f"  {h.ticker}: {h.shares} shares @ ${p.current_price:.2f} "
            f"(day: {p.day_change_pct:+.2f}%, P/L: ${pnl:+,.2f} / {pnl_pct:+.1f}%, "
            f"cost basis: ${h.cost_basis:.2f})"
        )

    return "\n".join(lines)


def _call_claude(user_message: str) -> str:
    from anthropic import Anthropic
    from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
        messages=[{"role": "user", "content": user_message}],
    )

    # Extract text blocks from the response (skip tool_use / web_search result blocks)
    text_parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)

    return "\n".join(text_parts)


def _parse_response(raw: str, prices: Dict[str, PriceData]) -> Tuple[str, List[Suggestion]]:
    suggestions = _parse_suggestions(raw, prices)
    # Strip the JSON block from the briefing text
    briefing = re.sub(r"```json\s*\[.*?\]\s*```", "", raw, flags=re.DOTALL).strip()
    return briefing, suggestions


def _parse_suggestions(raw: str, prices: Dict[str, PriceData]) -> List[Suggestion]:
    match = re.search(r"```json\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if not match:
        logger.info("No JSON suggestion block found in Claude response")
        return []

    try:
        items = json.loads(match.group(1))
    except json.JSONDecodeError:
        logger.warning("Failed to parse suggestion JSON from Claude response")
        return []

    now = datetime.now().isoformat()
    suggestions: List[Suggestion] = []
    for item in items:
        ticker = item.get("ticker", "").upper()
        price_data = prices.get(ticker)
        entry_price = price_data.current_price if price_data else 0.0
        suggestions.append(
            Suggestion(
                ticker=ticker,
                action=item.get("action", "BUY").upper(),
                confidence=item.get("confidence", "MEDIUM").upper(),
                target_price=float(item.get("target_price", 0)),
                reasoning=item.get("reasoning", ""),
                created_at=now,
                status="OPEN",
                entry_price=entry_price,
                timeframe_days=int(item.get("timeframe_days", 7)),
            )
        )
    return suggestions
