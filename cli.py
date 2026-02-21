"""
CLI: argument parsing and command dispatch for the ICT Trading Bot.
All commands (backtest, replay, paper, live) are handled here.
"""
import argparse
import config


def build_parser():
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        description="ICT Trading Bot — backtest, paper, live, replay"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["backtest", "paper", "live", "replay"],
        default="backtest",
        help="Mode to run the bot in",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        choices=["h1_m5_bos", "kingsely_gold", "marvellous", "nas", "judas", "test", "gold_compare", "marvellous_kingsley_compare", "all"],
        default="h1_m5_bos",
        help="Strategy to use ('all' = run every strategy; 'marvellous_kingsley_compare' = Marvellous vs Kingsley on gold)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        help="Path to CSV file for backtesting/replay",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=config.SYMBOLS[0],
        help="Symbol to trade/backtest/replay",
    )
    parser.add_argument(
        "--period",
        type=str,
        choices=["12d", "60d", "both"],
        default="both",
        help="Backtest period when --strategy all: 12d, 60d, or both (default)",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Bot auto-approves trades (no manual prompt). Use for server/headless runs.",
    )
    return parser


def _run_gold_compare(args):
    """Run kingsely_gold and h1_m5_bos on gold (GC=F), display in same table."""
    import sys
    import io
    from bot.backtest import run_bos_backtest, run_kingsley_backtest

    # Suppress fetch/strategy prints during run
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        s_kingsley = run_kingsley_backtest(symbol="GC=F", period=args.period if args.period != "both" else "60d", return_stats=True)
        s_bos = run_bos_backtest(symbol="GC=F", period=args.period if args.period != "both" else "60d", return_stats=True)
    finally:
        sys.stdout = old_stdout

    period = args.period if args.period != "both" else "60d"
    print()
    print("Backtest Parameters:")
    print("  Asset: GC=F (Gold)")
    print("  Risk per trade: 10%")
    print("  Trade Limit: No trade limit")
    print("  Duration:", period)
    print()
    print("| Strategy          | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
    print("| :---------------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
    for r in sorted([s_kingsley, s_bos], key=lambda x: x["return_pct"], reverse=True):
        wr = f"{r['win_rate']:.2f}%"
        ret_str = f"{'+' if r['return_pct'] >= 0 else ''}{r['return_pct']:,.2f}%"
        print(f"| {r['strategy']:<17} | {r['trades']:>5} | {r['wins']:>4} | {r['losses']:>6} | {wr:>9} | ${r['final_balance']:>11,.2f} | {ret_str:>10} |")


def _hour_to_session(hour_utc):
    """Map UTC hour to session (London 7-10, NY 13-16, Asian 0-4)."""
    import config
    return config.TRADE_SESSION_HOURS.get(hour_utc, "other")


def _format_trade_details(trade_details):
    """From trade_details [(ts, outcome), ...] return days, trades_per_day, sessions."""
    if not trade_details:
        return [], {}, {}
    from collections import Counter
    import pandas as pd
    days = []
    per_day = Counter()
    per_session = Counter()
    for ts, _ in trade_details:
        t = pd.Timestamp(ts) if not hasattr(ts, "hour") else ts
        day = t.strftime("%Y-%m-%d")
        days.append(day)
        per_day[day] += 1
        per_session[_hour_to_session(t.hour)] += 1
    unique_days = sorted(set(days))
    return unique_days, dict(per_day), dict(per_session)


def _run_marvellous_kingsley_compare(args):
    """Run marvellous and kingsely_gold on gold (GC=F), display side by side."""
    import sys
    import io
    from bot.backtest import run_kingsley_backtest, run_marvellous_backtest

    period = args.period if args.period != "both" else "60d"
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        s_marvellous = run_marvellous_backtest(
            symbol="GC=F", period=period, return_stats=True, include_trade_details=True
        )
        s_kingsley = run_kingsley_backtest(
            symbol="GC=F", period=period, return_stats=True, include_trade_details=True
        )
    finally:
        sys.stdout = old_stdout

    print()
    print("Backtest Parameters:")
    print("  Asset: GC=F (Gold)")
    print("  Risk per trade: 10%")
    print("  Trade Limit: No trade limit")
    print("  Duration:", period)
    print()
    print("| Strategy          | Trades | Wins | Losses | Win rate  | Final balance | Return      |")
    print("| :---------------- | :----- | :--- | :----- | :-------- | :------------ | :---------- |")
    for r in sorted([s_marvellous, s_kingsley], key=lambda x: x["return_pct"], reverse=True):
        wr = f"{r['win_rate']:.2f}%"
        ret_str = f"{'+' if r['return_pct'] >= 0 else ''}{r['return_pct']:,.2f}%"
        print(f"| {r['strategy']:<17} | {r['trades']:>5} | {r['wins']:>4} | {r['losses']:>6} | {wr:>9} | ${r['final_balance']:>11,.2f} | {ret_str:>10} |")

    # Days, trades per day, sessions — same table format
    print()
    print("| Strategy          | Days w/ trades | Max/day | Avg/day | London | NY | Asian | Other |")
    print("| :---------------- | :------------- | :------ | :------ | :----- | :- | :---- | :---- |")
    for r in [s_marvellous, s_kingsley]:
        details = r.get("trade_details", [])
        days_list, per_day, per_session = _format_trade_details(details)
        name = r["strategy"]
        n_days = len(days_list)
        if per_day and days_list:
            max_day = max(per_day, key=per_day.get)
            max_val = per_day[max_day]
            avg = r["trades"] / n_days
        else:
            max_val = 0
            avg = 0.0
        london = per_session.get("london", 0)
        ny = per_session.get("ny", 0)
        asian = per_session.get("asian", 0)
        other = per_session.get("other", 0)
        print(f"| {name:<17} | {n_days:>14} | {max_val:>6} | {avg:>6.1f} | {london:>6} | {ny:>2} | {asian:>5} | {other:>5} |")

    # BUY / SELL counts
    print()
    print("| Strategy          | BUY  | SELL |")
    print("| :---------------- | :--- | :--- |")
    for r in [s_marvellous, s_kingsley]:
        buys = r.get("buys", 0)
        sells = r.get("sells", 0)
        print(f"| {r['strategy']:<17} | {buys:>4} | {sells:>5} |")


def _fmt_money(x):
    """Format as currency: $0 for zero, else $1,234.56."""
    if x == 0:
        return "$0"
    return f"${x:,.2f}"


def _print_summary_table(period_label, rows):
    """Print one summary table for a given period (e.g. '12 days') — matches image format."""
    print(period_label)
    print()
    # Header (same column order as image)
    h = ("Strategy", "Trades", "Wins", "Losses", "Win Rate", "Total Profit", "Total Loss", "Final Balance", "Return")
    col_w = (18, 7, 6, 7, 10, 14, 12, 15, 12)
    header = "".join(h[i].ljust(col_w[i]) for i in range(len(h)))
    print(header)
    # Rows sorted by Return descending (best first), like in the image
    sorted_rows = sorted(rows, key=lambda r: r["return_pct"], reverse=True)
    for r in sorted_rows:
        wr = f"{r['win_rate']:.2f}%"
        ret = r["return_pct"]
        ret_str = f"{'+' if ret >= 0 else ''}{ret:,.2f}%"
        row_str = (
            r["strategy"].ljust(col_w[0])
            + str(r["trades"]).rjust(col_w[1])
            + str(r["wins"]).rjust(col_w[2])
            + str(r["losses"]).rjust(col_w[3])
            + wr.rjust(col_w[4])
            + _fmt_money(r["total_profit"]).rjust(col_w[5])
            + _fmt_money(r["total_loss"]).rjust(col_w[6])
            + _fmt_money(r["final_balance"]).rjust(col_w[7])
            + ret_str.rjust(col_w[8])
        )
        print(row_str)
    print()


def run_backtest(args):
    """Run backtest for the selected strategy (or all strategies if --strategy all)."""
    from bot.backtest import (
        run_bos_backtest,
        run_kingsley_backtest,
        run_marvellous_backtest,
        run_nas_backtest,
        run_judas_backtest,
        run_test_backtest,
    )
    if args.strategy == "gold_compare":
        _run_gold_compare(args)
        return
    if args.strategy == "marvellous_kingsley_compare":
        _run_marvellous_kingsley_compare(args)
        return

    strategies = (
        ["h1_m5_bos", "kingsely_gold", "marvellous", "nas", "judas", "test"]
        if args.strategy == "all"
        else [args.strategy]
    )

    if args.strategy == "all":
        # Run all strategies for chosen period(s), then print summary tables (no --csv for all)
        periods = (
            [("12 days", "12d"), ("60 days", "60d")]
            if args.period == "both"
            else [("60 days", "60d")] if args.period == "60d" else [("12 days", "12d")]
        )
        for period_label, period in periods:
            rows = []
            for name in strategies:
                kwargs = dict(symbol=args.symbol, period=period, return_stats=True)
                if name == "h1_m5_bos":
                    s = run_bos_backtest(**kwargs)
                elif name == "kingsely_gold":
                    s = run_kingsley_backtest(symbol="GC=F", period=period, return_stats=True)
                elif name == "marvellous":
                    from bot import marvellous_config as mc
                    s = run_marvellous_backtest(symbol=mc.MARVELLOUS_BACKTEST_SYMBOL, period=period, return_stats=True)
                elif name == "nas":
                    from bot import nas_config as nc
                    s = run_nas_backtest(symbol=nc.BACKTEST_SYMBOL, period=period, return_stats=True)
                elif name == "judas":
                    from bot import judas_config as jc
                    s = run_judas_backtest(symbol=jc.BACKTEST_SYMBOL, period=period, return_stats=True)
                else:
                    s = run_test_backtest(symbol="GC=F", period=period, return_stats=True)
                rows.append(s)
            _print_summary_table(period_label, rows)
        return

    period = args.period if args.period != "both" else "60d"
    for name in strategies:
        print(f"\n{'='*60}\nBacktesting {name} on {args.symbol}\n{'='*60}")
        kwargs = dict(csv_path=args.csv, symbol=args.symbol, period=period)
        if name == "h1_m5_bos":
            run_bos_backtest(**kwargs)
        elif name == "kingsely_gold":
            kwargs["symbol"] = kwargs.get("symbol") or "GC=F"
            run_kingsley_backtest(**kwargs)
        elif name == "marvellous":
            from bot import marvellous_config as mc
            kwargs["symbol"] = kwargs.get("symbol") or mc.MARVELLOUS_BACKTEST_SYMBOL
            run_marvellous_backtest(**kwargs)
        elif name == "nas":
            from bot import nas_config as nc
            kwargs["symbol"] = kwargs.get("symbol") or nc.BACKTEST_SYMBOL
            run_nas_backtest(**kwargs)
        elif name == "judas":
            from bot import judas_config as jc
            kwargs["symbol"] = kwargs.get("symbol") or jc.BACKTEST_SYMBOL
            run_judas_backtest(**kwargs)
        else:
            kwargs["symbol"] = kwargs.get("symbol") or "GC=F"
            run_test_backtest(**kwargs)


def run_replay_cmd(args):
    """Run replay (live flow on historical data)."""
    from bot.replay_engine import run_replay
    run_replay(
        strategy_name=args.strategy,
        symbol=args.symbol,
        csv_path=args.csv,
        auto_approve=True,
    )


def run_paper_or_live(args):
    """Run paper or live trading engine."""
    import sys
    try:
        from bot.live_trading import LiveTradingEngine
    except ImportError as e:
        err = str(e).lower()
        if "metatrader5" in err:
            print("Paper/live requires MetaTrader 5 (Windows only). Run on a Windows machine or Windows VPS with MT5 installed.")
            return
        raise
    if args.auto_approve:
        config.MANUAL_APPROVAL = False
        print("Auto-approve ON: bot will execute trades without confirmation.")
    paper_mode = args.mode == "paper"
    engine = LiveTradingEngine(
        strategy_name=args.strategy,
        paper_mode=paper_mode,
    )
    if not engine.connect():
        print("Failed to connect. Ensure MT5 terminal is installed/running and credentials in .env are correct.")
        return
    try:
        engine.run()
    finally:
        engine.disconnect()
    # Test strategy single-run: force process exit (MT5 may keep threads alive)
    if args.strategy == "test" and getattr(config, "TEST_SINGLE_RUN", False):
        sys.exit(0)


def run(args):
    """
    Dispatch to the correct command based on args.mode.
    Call this after parsing with build_parser().
    """
    if args.strategy == "all" and args.mode != "backtest":
        print("--strategy all is only supported in backtest mode.")
        return
    print(f"Starting ICT Bot in {args.mode} mode with {args.strategy} strategy...")
    if args.mode == "backtest":
        run_backtest(args)
    elif args.mode == "replay":
        run_replay_cmd(args)
    elif args.mode in ("paper", "live"):
        run_paper_or_live(args)
    else:
        raise ValueError(f"Unknown mode: {args.mode}")


def main():
    """Entry point: parse arguments and run the chosen command."""
    parser = build_parser()
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
