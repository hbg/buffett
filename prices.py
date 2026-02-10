from __future__ import annotations

import logging
from typing import Dict, Optional

from models import PriceData

logger = logging.getLogger(__name__)


def fetch_prices(tickers: list) -> Dict[str, PriceData]:
    import yfinance as yf

    results: Dict[str, PriceData] = {}
    batch = yf.Tickers(" ".join(tickers))

    for ticker in tickers:
        try:
            info = batch.tickers[ticker].fast_info
            current = info.last_price
            prev_close = info.previous_close
            if current is None or prev_close is None:
                logger.warning("Missing price data for %s, skipping", ticker)
                continue
            change_pct = ((current - prev_close) / prev_close) * 100 if prev_close else 0.0
            results[ticker] = PriceData(
                ticker=ticker,
                current_price=round(current, 2),
                previous_close=round(prev_close, 2),
                day_change_pct=round(change_pct, 2),
            )
        except Exception:
            logger.warning("Failed to fetch price for %s, skipping", ticker, exc_info=True)

    return results


def get_current_price(ticker: str) -> Optional[float]:
    prices = fetch_prices([ticker])
    if ticker in prices:
        return prices[ticker].current_price
    return None
