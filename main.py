from __future__ import annotations

import argparse
import sys


def cmd_run(args: argparse.Namespace) -> None:
    from pipeline import run_daily

    run_daily()


def cmd_add(args: argparse.Namespace) -> None:
    from db import add_holding, init_db

    init_db()
    ticker = args.ticker.upper()

    cost_basis = args.cost_basis
    if cost_basis is None:
        from prices import get_current_price

        cost_basis = get_current_price(ticker)
        if cost_basis is None:
            print(f"Could not fetch price for {ticker}. Specify cost basis manually.")
            sys.exit(1)
        print(f"Using current price ${cost_basis:.2f} as cost basis")

    add_holding(ticker, args.shares, cost_basis)
    print(f"Added {args.shares} shares of {ticker} @ ${cost_basis:.2f}")


def cmd_remove(args: argparse.Namespace) -> None:
    from db import init_db, remove_holding

    init_db()
    ticker = args.ticker.upper()
    if remove_holding(ticker):
        print(f"Removed {ticker} from portfolio")
    else:
        print(f"{ticker} not found in portfolio")


def cmd_portfolio(args: argparse.Namespace) -> None:
    from db import get_holdings, init_db
    from prices import fetch_prices

    init_db()
    holdings = get_holdings()
    if not holdings:
        print("Portfolio is empty. Use 'add' to add holdings.")
        return

    tickers = [h.ticker for h in holdings]
    prices = fetch_prices(tickers)

    print(f"\n{'Ticker':<8} {'Shares':>8} {'Price':>10} {'Value':>12} {'Cost':>10} {'P/L':>12} {'P/L %':>8} {'Day':>8}")
    print("-" * 78)

    total_value = 0.0
    total_cost = 0.0
    for h in holdings:
        p = prices.get(h.ticker)
        if not p:
            print(f"{h.ticker:<8} {h.shares:>8.1f} {'N/A':>10}")
            continue
        value = h.shares * p.current_price
        cost = h.shares * h.cost_basis
        pnl = value - cost
        pnl_pct = (pnl / cost) * 100 if cost else 0
        total_value += value
        total_cost += cost
        print(
            f"{h.ticker:<8} {h.shares:>8.1f} {p.current_price:>10.2f} "
            f"${value:>10,.2f} {h.cost_basis:>10.2f} "
            f"{'${:>+10,.2f}'.format(pnl)} {pnl_pct:>+7.1f}% {p.day_change_pct:>+7.2f}%"
        )

    print("-" * 78)
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost) * 100 if total_cost else 0
    print(
        f"{'TOTAL':<8} {'':>8} {'':>10} "
        f"${total_value:>10,.2f} {'':>10} "
        f"{'${:>+10,.2f}'.format(total_pnl)} {total_pnl_pct:>+7.1f}%"
    )
    print()


def cmd_suggestions(args: argparse.Namespace) -> None:
    from db import get_open_suggestions, init_db

    init_db()
    open_sug = get_open_suggestions()
    if not open_sug:
        print("No open suggestions.")
        return

    print(f"\n{'ID':>4} {'Ticker':<8} {'Action':<6} {'Conf':<8} {'Entry':>10} {'Target':>10} {'Days':>5}  Reasoning")
    print("-" * 90)
    for s in open_sug:
        print(
            f"{s.id:>4} {s.ticker:<8} {s.action:<6} {s.confidence:<8} "
            f"${s.entry_price:>9.2f} ${s.target_price:>9.2f} {s.timeframe_days:>5}  "
            f"{s.reasoning[:40]}"
        )
    print()


def cmd_scorecard(args: argparse.Namespace) -> None:
    from db import get_all_suggestions, init_db
    from suggestions import scorecard

    init_db()
    all_sug = get_all_suggestions()
    if not all_sug:
        print("No suggestions recorded yet.")
        return

    sc = scorecard(all_sug)
    print(f"\n{'Suggestion Scorecard':=^50}")
    print(f"  Total suggestions:  {sc['total']}")
    print(f"  Open:               {sc['open']}")
    print(f"  Resolved:           {sc['resolved']}")
    print(f"  Hit rate:           {sc['hit_rate']:.1f}%")
    print(f"  Avg P/L per trade:  ${sc['avg_pnl']:+.2f}")

    if sc["best"]:
        b = sc["best"]
        print(f"  Best call:          {b['action']} {b['ticker']} (${b['pnl']:+.2f}, {b['status']})")
    if sc["worst"]:
        w = sc["worst"]
        print(f"  Worst call:         {w['action']} {w['ticker']} (${w['pnl']:+.2f}, {w['status']})")

    if sc["by_confidence"]:
        print(f"\n  {'Confidence':<12} {'Count':>6} {'Hit Rate':>10} {'Avg P/L':>10}")
        print("  " + "-" * 40)
        for conf, data in sc["by_confidence"].items():
            print(f"  {conf:<12} {data['count']:>6} {data['hit_rate']:>9.1f}% ${data['avg_pnl']:>+9.2f}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Portfolio Advisor")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="Run daily analysis pipeline")

    add_p = sub.add_parser("add", help="Add a holding")
    add_p.add_argument("ticker", help="Stock ticker symbol")
    add_p.add_argument("shares", type=float, help="Number of shares")
    add_p.add_argument("cost_basis", type=float, nargs="?", default=None, help="Cost basis per share (default: current price)")

    rm_p = sub.add_parser("remove", help="Remove a holding")
    rm_p.add_argument("ticker", help="Stock ticker symbol")

    sub.add_parser("portfolio", help="Show current portfolio")
    sub.add_parser("suggestions", help="Show open suggestions")
    sub.add_parser("scorecard", help="Show suggestion scorecard")

    args = parser.parse_args()

    commands = {
        "run": cmd_run,
        "add": cmd_add,
        "remove": cmd_remove,
        "portfolio": cmd_portfolio,
        "suggestions": cmd_suggestions,
        "scorecard": cmd_scorecard,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
