import sys
import threading
from datetime import datetime

class TradeApprover:
    """Handles manual approval for trades before execution."""

    def __init__(self, timeout=60):
        self.timeout = timeout

    def request_approval(self, signal, account_info=None):
        print("\n" + "=" * 50)
        print("TRADE APPROVAL REQUIRED")
        print("=" * 50)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Strategy: {signal.get('reason', 'Unknown')}")
        print(f"Symbol: {signal['symbol']}")
        print(f"Direction: {signal['type']}")
        print(f"Entry Price: {signal['price']:.5f}")
        print(f"Stop Loss: {signal['sl']:.5f}")
        print(f"Take Profit: {signal['tp']:.5f}")
        if signal['type'] == 'BUY':
            risk = signal['price'] - signal['sl']
            reward = signal['tp'] - signal['price']
        else:
            risk = signal['sl'] - signal['price']
            reward = signal['price'] - signal['tp']
        rr_ratio = reward / risk if risk > 0 else 0
        print(f"Risk:Reward: 1:{rr_ratio:.2f}")
        volume = signal.get('volume', 0.01)
        print(f"\nPosition Size: {volume} lots")
        risk_amount = risk * volume * 100
        print(f"Estimated Risk: ${risk_amount:.2f}")
        if account_info:
            print(f"\nAccount Balance: ${account_info['balance']:.2f}")
            print(f"Account Equity: ${account_info['equity']:.2f}")
        print("\n" + "=" * 50)
        result = [None]
        def read_response():
            try:
                if sys.stdin.isatty():
                    response = input(f"Approve this trade? (y/n, {self.timeout}s timeout): ").strip().lower()
                else:
                    response = sys.stdin.readline().strip().lower()
                result[0] = response
            except (KeyboardInterrupt, Exception):
                result[0] = ""
        try:
            reader = threading.Thread(target=read_response, daemon=True)
            reader.start()
            reader.join(timeout=self.timeout if self.timeout > 0 else None)
            if result[0] is None:
                print(f"\nNo response within {self.timeout}s - trade REJECTED (timeout)")
                return False
            if result[0] == 'y' or result[0] == 'yes':
                print("✓ Trade APPROVED")
                return True
            else:
                print("✗ Trade REJECTED")
                return False
        except KeyboardInterrupt:
            print("\n✗ Trade REJECTED (interrupted)")
            return False
        except Exception as e:
            print(f"\n✗ Trade REJECTED (error: {e})")
            return False

    def show_daily_summary(self, trades_today):
        if not trades_today:
            return
        wins = sum(1 for t in trades_today if t.get('profit', 0) > 0)
        losses = sum(1 for t in trades_today if t.get('profit', 0) <= 0)
        total_profit = sum(t.get('profit', 0) for t in trades_today)
        print("\n" + "=" * 50)
        print("TODAY'S TRADING SUMMARY")
        print("=" * 50)
        print(f"Total Trades: {len(trades_today)}")
        print(f"Wins: {wins}")
        print(f"Losses: {losses}")
        if trades_today:
            print(f"Win Rate: {wins/len(trades_today)*100:.1f}%")
        print(f"Total P&L: ${total_profit:.2f}")
        print("=" * 50)
