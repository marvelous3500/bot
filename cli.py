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
        choices=["pdh_pdl", "liquidity_sweep", "h1_m5_bos", "confluence", "all"],
        default="h1_m5_bos",
        help="Strategy to use ('all' = run every strategy in backtest mode)",
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
        run_backtest_simulation,
        run_liquidity_sweep_backtest,
        run_bos_backtest,
        run_confluence_backtest,
    )
    strategies = (
        ["pdh_pdl", "liquidity_sweep", "h1_m5_bos", "confluence"]
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
                if name == "pdh_pdl":
                    s = run_backtest_simulation(**kwargs)
                elif name == "liquidity_sweep":
                    s = run_liquidity_sweep_backtest(**kwargs)
                elif name == "h1_m5_bos":
                    s = run_bos_backtest(**kwargs)
                else:
                    s = run_confluence_backtest(**kwargs)
                rows.append(s)
            _print_summary_table(period_label, rows)
        return

    for name in strategies:
        print(f"\n{'='*60}\nBacktesting {name} on {args.symbol}\n{'='*60}")
        kwargs = dict(csv_path=args.csv, symbol=args.symbol)
        if name == "pdh_pdl":
            run_backtest_simulation(**kwargs)
        elif name == "liquidity_sweep":
            run_liquidity_sweep_backtest(**kwargs)
        elif name == "h1_m5_bos":
            run_bos_backtest(**kwargs)
        elif name == "confluence":
            run_confluence_backtest(**kwargs)


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
