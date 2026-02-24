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
        choices=["marvellous", "vester", "follow", "test-sl", "all"],
        default="marvellous",
        help="Strategy to use ('all' = run marvellous+vester; 'follow' = test strategy; 'test-sl' = one trade then stop)",
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
    parser.add_argument(
        "--trade-details",
        action="store_true",
        help="Print per-trade log (entry, SL, TP, outcome, bar hit) for backtest.",
    )
    parser.add_argument(
        "--compare-breaker-block",
        action="store_true",
        help="Run backtest with and without breaker block; show side-by-side comparison for each strategy.",
    )
    parser.add_argument(
        "--compare-premium-discount",
        action="store_true",
        help="Run backtest with and without premium/discount filter; show side-by-side comparison for each strategy.",
    )
    return parser


def _hour_to_session(hour_utc):
    """Map UTC hour to session (London 7-10, NY 13-16, Asian 0-4)."""
    import config
    return config.TRADE_SESSION_HOURS.get(hour_utc, "other")


def _format_trade_details(trade_details):
    """From trade_details [(ts, outcome), ...] or [(ts, outcome, ...), ...] return days, trades_per_day, sessions."""
    if not trade_details:
        return [], {}, {}
    from collections import Counter
    import pandas as pd
    days = []
    per_day = Counter()
    per_session = Counter()
    for item in trade_details:
        ts = item[0]
        ts_conv = pd.Timestamp(ts) if not hasattr(ts, "hour") else ts
        day = ts_conv.strftime("%Y-%m-%d")
        days.append(day)
        per_day[day] += 1
        per_session[_hour_to_session(ts_conv.hour)] += 1
    unique_days = sorted(set(days))
    return unique_days, dict(per_day), dict(per_session)


def _fmt_money(x):
    """Format as currency: $0 for zero, else $1,234.56."""
    if x == 0:
        return "$0"
    return f"${x:,.2f}"


def _print_summary_table(period_label, rows):
    """Print one summary table for a given period (e.g. '12 days') — matches image format."""
    print(period_label)
    print()
    h = ("Strategy", "Trades", "Wins", "Losses", "Win Rate", "Total Profit", "Total Loss", "Final Balance", "Return")
    col_w = (18, 7, 6, 7, 10, 14, 12, 15, 12)
    header = "".join(h[i].ljust(col_w[i]) for i in range(len(h)))
    print(header)
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


def _print_breaker_block_comparison(strategy_name, without_bb, with_bb):
    """Print side-by-side comparison: without vs with breaker block."""
    print()
    print(f"  {strategy_name.upper()} — Breaker Block Comparison")
    print("  " + "-" * 70)
    print("  | {:20} | {:24} | {:24} |".format("Metric", "Without Breaker Block", "With Breaker Block"))
    print("  |" + "-" * 22 + "|" + "-" * 26 + "|" + "-" * 26 + "|")
    for key, label in [
        ("trades", "Trades"),
        ("wins", "Wins"),
        ("losses", "Losses"),
        ("win_rate", "Win rate"),
        ("final_balance", "Final balance"),
        ("return_pct", "Return"),
    ]:
        v0 = without_bb.get(key, 0)
        v1 = with_bb.get(key, 0)
        if key == "win_rate":
            v0_str = f"{v0:.2f}%"
            v1_str = f"{v1:.2f}%"
        elif key == "return_pct":
            v0_str = f"{'+' if v0 >= 0 else ''}{v0:,.2f}%"
            v1_str = f"{'+' if v1 >= 0 else ''}{v1:,.2f}%"
        elif key == "final_balance":
            v0_str = _fmt_money(v0)
            v1_str = _fmt_money(v1)
        else:
            v0_str = str(v0)
            v1_str = str(v1)
        print("  | {:20} | {:>24} | {:>24} |".format(label, v0_str, v1_str))
    print("  " + "-" * 70)
    print()


def _print_premium_discount_comparison(strategy_name, without_pd, with_pd):
    """Print side-by-side comparison: without vs with premium/discount filter."""
    print()
    print(f"  {strategy_name.upper()} — Premium/Discount Comparison")
    print("  " + "-" * 70)
    print("  | {:20} | {:24} | {:24} |".format("Metric", "Without P/D Filter", "With P/D Filter"))
    print("  |" + "-" * 22 + "|" + "-" * 26 + "|" + "-" * 26 + "|")
    for key, label in [
        ("trades", "Trades"),
        ("wins", "Wins"),
        ("losses", "Losses"),
        ("win_rate", "Win rate"),
        ("final_balance", "Final balance"),
        ("return_pct", "Return"),
    ]:
        v0 = without_pd.get(key, 0)
        v1 = with_pd.get(key, 0)
        if key == "win_rate":
            v0_str = f"{v0:.2f}%"
            v1_str = f"{v1:.2f}%"
        elif key == "return_pct":
            v0_str = f"{'+' if v0 >= 0 else ''}{v0:,.2f}%"
            v1_str = f"{'+' if v1 >= 0 else ''}{v1:,.2f}%"
        elif key == "final_balance":
            v0_str = _fmt_money(v0)
            v1_str = _fmt_money(v1)
        else:
            v0_str = str(v0)
            v1_str = str(v1)
        print("  | {:20} | {:>24} | {:>24} |".format(label, v0_str, v1_str))
    print("  " + "-" * 70)
    print()


def run_backtest(args):
    """Run backtest for the selected strategy (or all strategies if --strategy all)."""
    from bot.backtest import run_marvellous_backtest, run_vester_backtest, run_follow_backtest

    if args.strategy == "test-sl":
        print("test-sl has no backtest. Use --mode live (or paper) for lot-size testing.")
        return

    strategies = (
        ["marvellous", "vester"]
        if args.strategy == "all"
        else [args.strategy]
    )

    # Premium/Discount comparison: run each strategy with and without P/D filter
    if getattr(args, "compare_premium_discount", False):
        period = args.period if args.period != "both" else "60d"
        for name in strategies:
            print(f"\n{'='*60}\nBacktesting {name} on {args.symbol} (premium/discount comparison)\n{'='*60}")
            kwargs = dict(csv_path=args.csv, symbol=args.symbol, period=period, return_stats=True)
            if name == "marvellous":
                from bot import marvellous_config as mc
                kwargs["symbol"] = kwargs.get("symbol") or mc.MARVELLOUS_BACKTEST_SYMBOL
                orig = getattr(mc, "USE_PREMIUM_DISCOUNT", False)
                mc.USE_PREMIUM_DISCOUNT = False
                without_pd = run_marvellous_backtest(**kwargs)
                mc.USE_PREMIUM_DISCOUNT = True
                with_pd = run_marvellous_backtest(**kwargs)
                mc.USE_PREMIUM_DISCOUNT = orig
            else:
                from bot import vester_config as vc
                kwargs["symbol"] = kwargs.get("symbol") or vc.VESTER_BACKTEST_SYMBOL
                orig = getattr(vc, "USE_PREMIUM_DISCOUNT", False)
                vc.USE_PREMIUM_DISCOUNT = False
                without_pd = run_vester_backtest(**kwargs)
                vc.USE_PREMIUM_DISCOUNT = True
                with_pd = run_vester_backtest(**kwargs)
                vc.USE_PREMIUM_DISCOUNT = orig
            _print_premium_discount_comparison(name, without_pd, with_pd)
        return

    # Breaker block comparison: run each strategy with and without breaker block
    if getattr(args, "compare_breaker_block", False):
        period = args.period if args.period != "both" else "60d"
        for name in strategies:
            print(f"\n{'='*60}\nBacktesting {name} on {args.symbol} (breaker block comparison)\n{'='*60}")
            kwargs = dict(csv_path=args.csv, symbol=args.symbol, period=period, return_stats=True)
            if name == "marvellous":
                from bot import marvellous_config as mc
                kwargs["symbol"] = kwargs.get("symbol") or mc.MARVELLOUS_BACKTEST_SYMBOL
                orig = getattr(mc, "REQUIRE_BREAKER_BLOCK", False)
                mc.REQUIRE_BREAKER_BLOCK = False
                without_bb = run_marvellous_backtest(**kwargs)
                mc.REQUIRE_BREAKER_BLOCK = True
                with_bb = run_marvellous_backtest(**kwargs)
                mc.REQUIRE_BREAKER_BLOCK = orig
            else:
                from bot import vester_config as vc
                kwargs["symbol"] = kwargs.get("symbol") or vc.VESTER_BACKTEST_SYMBOL
                orig_req = getattr(vc, "REQUIRE_BREAKER_BLOCK", False)
                orig_4h = getattr(vc, "BREAKER_BLOCK_4H", False)
                vc.REQUIRE_BREAKER_BLOCK = False
                vc.BREAKER_BLOCK_4H = False
                without_bb = run_vester_backtest(**kwargs)
                vc.REQUIRE_BREAKER_BLOCK = True
                vc.BREAKER_BLOCK_4H = getattr(config, "VESTER_BREAKER_BLOCK_4H", False)
                with_bb = run_vester_backtest(**kwargs)
                vc.REQUIRE_BREAKER_BLOCK = orig_req
                vc.BREAKER_BLOCK_4H = orig_4h
            _print_breaker_block_comparison(name, without_bb, with_bb)
        return

    if args.strategy == "all":
        periods = (
            [("12 days", "12d"), ("60 days", "60d")]
            if args.period == "both"
            else [("60 days", "60d")] if args.period == "60d" else [("12 days", "12d")]
        )
        for period_label, period in periods:
            rows = []
            for name in strategies:
                kwargs = dict(symbol=args.symbol, period=period, return_stats=True)
                if name == "marvellous":
                    from bot import marvellous_config as mc
                    kwargs["symbol"] = mc.MARVELLOUS_BACKTEST_SYMBOL
                    s = run_marvellous_backtest(**kwargs)
                elif name == "vester":
                    from bot import vester_config as vc
                    kwargs["symbol"] = kwargs.get("symbol") or vc.VESTER_BACKTEST_SYMBOL
                    s = run_vester_backtest(**kwargs)
                rows.append(s)
            _print_summary_table(period_label, rows)
        return

    period = args.period if args.period != "both" else "60d"
    for name in strategies:
        print(f"\n{'='*60}\nBacktesting {name} on {args.symbol}\n{'='*60}")
        kwargs = dict(csv_path=args.csv, symbol=args.symbol, period=period)
        if getattr(args, "trade_details", False):
            kwargs["include_trade_details"] = True
        if name == "marvellous":
            from bot import marvellous_config as mc
            kwargs["symbol"] = kwargs.get("symbol") or mc.MARVELLOUS_BACKTEST_SYMBOL
            run_marvellous_backtest(**kwargs)
        elif name == "vester":
            from bot import vester_config as vc
            kwargs["symbol"] = kwargs.get("symbol") or vc.VESTER_BACKTEST_SYMBOL
            run_vester_backtest(**kwargs)
        elif name == "follow":
            kwargs["symbol"] = kwargs.get("symbol") or getattr(config, "VESTER_BACKTEST_SYMBOL", "GC=F")
            run_follow_backtest(**kwargs)


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
        symbol=args.symbol,
    )
    if not engine.connect():
        print("Failed to connect. Ensure MT5 terminal is installed/running and credentials in .env are correct.")
        return
    try:
        engine.run()
    finally:
        engine.disconnect()


def run(args):
    """Dispatch to the correct command based on args.mode."""
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
