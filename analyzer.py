from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from models import Holding, HoldingSnapshot, PriceData, Suggestion

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a portfolio analyst writing a brief daily morning email. This is an automated daily \
job — search the web for news from the LAST 24 HOURS only. Be concise: the reader will \
scan this over coffee in under 2 minutes.

Your output must start with a TITLE line — a short, punchy call-to-action headline derived \
from today's most important finding (e.g. "NVDA earnings Feb 25 — consider adding ahead of \
beat-and-raise" or "AAPL ex-div today — hold through for $0.26 payout"). Format it as a \
top-level markdown heading: # Title Here

Then these sections, using short bullet points (not paragraphs):

- **Action Items** — the 1-3 most important things the reader should consider doing TODAY, \
each as a single bold bullet. Lead with the ticker and the action. This is the most \
important section.
- **Market Snapshot** — 2-3 bullets on indices, macro headlines
- **Your Holdings** — 1 bullet per ticker: what happened, what to watch
- **New Ideas** — 1-2 BUY/SELL ideas for tickers the user does NOT already hold

PRIVACY: NEVER mention share counts, portfolio dollar values, cost basis, or P/L amounts. \
Percentages, price levels, and directional guidance only.

STYLE: No preamble, no sign-off, no "here's your briefing" filler. Jump straight into the \
title. Keep the whole briefing under 400 words. Do NOT use citation markers or footnotes.

After the prose, output a fenced ```json block with a suggestion array. Each object:
  {"ticker", "action": "BUY"|"SELL", "confidence": "HIGH"|"MEDIUM"|"LOW", \
"target_price": number, "reasoning": string, "timeframe_days": int}
Suggestions may include tickers NOT in the user's portfolio. \
Empty array if no suggestions: ```json\n[]\n```
JSON block must be the very last thing — not inside the prose.\
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

    # Extract text blocks, joining fragments intelligently
    text_parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)

    raw = _join_text_blocks(text_parts)
    return _clean_response(raw)


def _join_text_blocks(parts: List[str]) -> str:
    """Join text blocks from web search responses. Fragments that continue a
    sentence (start with lowercase, punctuation, or conjunctions) get joined
    with a space instead of a newline to avoid mid-sentence breaks."""
    if not parts:
        return ""
    result = parts[0]
    for part in parts[1:]:
        stripped = part.lstrip()
        if not stripped:
            continue
        # Fragment continues a sentence: starts with lowercase, punctuation, or conjunction
        if stripped[0].islower() or stripped[0] in ";,.:)":
            result = result.rstrip() + " " + stripped
        else:
            result = result + "\n" + part
    return result


def _clean_response(text: str) -> str:
    # Remove citation markers: [1], [2], etc.
    text = re.sub(r"\[\d+\]", "", text)
    # Remove preamble lines (Claude narrating its search process)
    text = re.sub(
        r"^.*(I'll search|Let me search|I'll look|Let me look|I'll analyze|Let me analyze|"
        r"I'll check|Let me check|I'll research|Let me research|searching for|looking up).*$",
        "", text, flags=re.MULTILINE | re.IGNORECASE,
    )
    # Remove orphaned punctuation on its own line
    text = re.sub(r"^\s*[;.,]\s*$", "", text, flags=re.MULTILINE)
    # Join lines where punctuation got stranded at start of next line
    text = re.sub(r"\n\s*([;,.])\s*", r"\1 ", text)
    # Collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
