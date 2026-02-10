from __future__ import annotations

import logging
from datetime import datetime

from models import Briefing, HoldingSnapshot

logger = logging.getLogger(__name__)


def run_daily() -> None:
    from analyzer import analyze_portfolio
    from db import (
        get_holdings,
        get_previous_day_value,
        init_db,
        save_briefing,
        save_snapshots,
        save_suggestion,
    )
    from notifier import send_briefing
    from prices import fetch_prices
    from suggestions import resolve_open_suggestions

    init_db()

    # 1. Load holdings
    holdings = get_holdings()
    if not holdings:
        print("No holdings in portfolio. Use 'add' command first.")
        return

    tickers = [h.ticker for h in holdings]
    print(f"Portfolio: {', '.join(tickers)}")

    # 2. Fetch prices
    prices = fetch_prices(tickers)
    if not prices:
        print("Failed to fetch any prices. Aborting.")
        return

    print(f"Prices fetched for {len(prices)}/{len(tickers)} tickers")

    # 3. Build snapshots, compute portfolio value
    snapshots = []
    portfolio_value = 0.0
    for h in holdings:
        p = prices.get(h.ticker)
        if not p:
            continue
        value = h.shares * p.current_price
        portfolio_value += value
        snapshots.append(
            HoldingSnapshot(
                ticker=h.ticker,
                shares=h.shares,
                price=p.current_price,
                value=round(value, 2),
                day_change_pct=p.day_change_pct,
            )
        )

    print(f"Portfolio value: ${portfolio_value:,.2f}")

    # 4. Compute daily change
    prev_value = get_previous_day_value()
    daily_change_pct = None
    if prev_value and prev_value > 0:
        daily_change_pct = round(((portfolio_value - prev_value) / prev_value) * 100, 2)
        print(f"Daily change: {daily_change_pct:+.2f}%")

    # 5. Resolve open suggestions
    resolve_open_suggestions(prices)

    # 6. Call Claude for analysis
    print("Analyzing portfolio with Claude...")
    briefing_text, suggestions = analyze_portfolio(
        holdings, snapshots, prices, portfolio_value, daily_change_pct
    )
    print(f"Analysis complete — {len(suggestions)} suggestion(s)")

    # 7. Save new suggestions
    for s in suggestions:
        save_suggestion(s)

    # 8. Save briefing
    now = datetime.now()
    briefing = Briefing(
        date=now.strftime("%Y-%m-%d"),
        content=briefing_text,
        portfolio_value=round(portfolio_value, 2),
        daily_change_pct=daily_change_pct,
        suggestion_count=len(suggestions),
        created_at=now.isoformat(),
    )
    briefing_id = save_briefing(briefing)
    briefing.id = briefing_id

    # Save snapshots linked to this briefing
    save_snapshots(snapshots, briefing_id)

    # 9. Send email
    sent = send_briefing(briefing)
    if sent:
        print("Briefing email sent!")
    else:
        print("Email not sent (check SMTP config or logs)")

    # 10. Print summary
    print("\n" + "=" * 60)
    print(briefing_text[:500] + ("..." if len(briefing_text) > 500 else ""))
    print("=" * 60)
