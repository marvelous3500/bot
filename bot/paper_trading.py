import pandas as pd
from datetime import datetime
import json
import os

try:
    import config
except ImportError:
    config = None

class PaperTrading:
    """Simulates live trading without risking real money."""

    def __init__(self, initial_balance=10000, log_file='paper_trades.json'):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.positions = []
        self.trades_history = []
        self.log_file = log_file
        self.next_ticket = 1
        if os.path.exists(log_file):
            self.load_session()

    def place_order(self, symbol, order_type, volume, price, sl=None, tp=None, comment=""):
        ticket = self.next_ticket
        self.next_ticket += 1
        position = {
            'ticket': ticket,
            'symbol': symbol,
            'type': order_type,
            'volume': volume,
            'price_open': price,
            'sl': sl,
            'tp': tp,
            'comment': comment,
            'time_open': datetime.now(),
            'profit': 0
        }
        self.positions.append(position)
        print(f"[PAPER] Order executed: {order_type} {volume} {symbol} @ {price}, Ticket: {ticket}")
        return {
            'ticket': ticket,
            'symbol': symbol,
            'type': order_type,
            'volume': volume,
            'price': price,
            'sl': sl,
            'tp': tp,
            'time': datetime.now()
        }

    def update_positions(self, mt5_connector):
        closed_positions = []
        tp1_enabled = config and getattr(config, 'TP1_SL_TO_ENTRY_ENABLED', False)
        tp1_ratio = getattr(config, 'TP1_RATIO', 0.5) if config else 0.5
        for position in self.positions[:]:
            symbol = position['symbol']
            tick = mt5_connector.get_live_price(symbol)
            if tick is None:
                continue
            if position['type'] == 'BUY':
                current_price = tick['bid']
                price_diff = current_price - position['price_open']
                if tp1_enabled and position.get('tp'):
                    price_open = position['price_open']
                    tp = position['tp']
                    tp1 = price_open + (tp - price_open) * tp1_ratio
                    sl = position.get('sl')
                    pip_size = mt5_connector.get_pip_size(symbol) if mt5_connector else None
                    tolerance = (pip_size or 0.0001) * 2
                    sl_at_entry = sl is not None and abs(float(sl) - float(price_open)) <= tolerance
                    if current_price >= tp1 and not sl_at_entry:
                        position['sl'] = price_open
                        print(f"[PAPER] Position {position['ticket']} SL moved to entry (TP1 hit)")
                if position['tp'] and current_price >= position['tp']:
                    self.close_position(position['ticket'], position['tp'], 'TP Hit')
                    closed_positions.append(position['ticket'])
                    continue
                if position['sl'] and current_price <= position['sl']:
                    self.close_position(position['ticket'], position['sl'], 'SL Hit')
                    closed_positions.append(position['ticket'])
                    continue
            else:
                current_price = tick['ask']
                price_diff = position['price_open'] - current_price
                if tp1_enabled and position.get('tp'):
                    price_open = position['price_open']
                    tp = position['tp']
                    tp1 = price_open - (price_open - tp) * tp1_ratio
                    sl = position.get('sl')
                    pip_size = mt5_connector.get_pip_size(symbol) if mt5_connector else None
                    tolerance = (pip_size or 0.0001) * 2
                    sl_at_entry = sl is not None and abs(float(sl) - float(price_open)) <= tolerance
                    if current_price <= tp1 and not sl_at_entry:
                        position['sl'] = price_open
                        print(f"[PAPER] Position {position['ticket']} SL moved to entry (TP1 hit)")
                if position['tp'] and current_price <= position['tp']:
                    self.close_position(position['ticket'], position['tp'], 'TP Hit')
                    closed_positions.append(position['ticket'])
                    continue
                if position['sl'] and current_price >= position['sl']:
                    self.close_position(position['ticket'], position['sl'], 'SL Hit')
                    closed_positions.append(position['ticket'])
                    continue
            position['profit'] = price_diff * position['volume'] * 100
        return closed_positions

    def close_position(self, ticket, close_price, reason="Manual Close"):
        for i, position in enumerate(self.positions):
            if position['ticket'] == ticket:
                if position['type'] == 'BUY':
                    price_diff = close_price - position['price_open']
                else:
                    price_diff = position['price_open'] - close_price
                profit = price_diff * position['volume'] * 100
                self.balance += profit
                trade = {
                    **position,
                    'price_close': close_price,
                    'time_close': datetime.now().isoformat(),
                    'profit': profit,
                    'reason': reason
                }
                self.trades_history.append(trade)
                self.positions.pop(i)
                print(f"[PAPER] Position {ticket} closed @ {close_price}, Profit: ${profit:.2f}, Reason: {reason}")
                self.save_session()
                return True
        return False

    def get_positions(self):
        return self.positions

    def get_account_info(self):
        total_profit = sum(p['profit'] for p in self.positions)
        return {
            'balance': self.balance,
            'equity': self.balance + total_profit,
            'profit': total_profit,
            'margin': 0,
            'free_margin': self.balance + total_profit,
            'currency': 'USD'
        }

    def get_stats(self):
        if not self.trades_history:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'total_profit': 0,
                'return_pct': 0
            }
        wins = len([t for t in self.trades_history if t['profit'] > 0])
        losses = len([t for t in self.trades_history if t['profit'] <= 0])
        total_profit = sum(t['profit'] for t in self.trades_history)
        return {
            'total_trades': len(self.trades_history),
            'wins': wins,
            'losses': losses,
            'win_rate': wins / len(self.trades_history) * 100 if self.trades_history else 0,
            'total_profit': total_profit,
            'return_pct': (self.balance - self.initial_balance) / self.initial_balance * 100
        }

    def save_session(self):
        data = {
            'balance': self.balance,
            'initial_balance': self.initial_balance,
            'positions': [{**p, 'time_open': p['time_open'].isoformat()} for p in self.positions],
            'trades_history': self.trades_history,
            'next_ticket': self.next_ticket
        }
        with open(self.log_file, 'w') as f:
            json.dump(data, f, indent=2)

    def load_session(self):
        try:
            with open(self.log_file, 'r') as f:
                data = json.load(f)
            self.balance = data.get('balance', self.balance)
            self.initial_balance = data.get('initial_balance', self.initial_balance)
            self.trades_history = data.get('trades_history', [])
            self.next_ticket = data.get('next_ticket', 1)
            positions = data.get('positions', [])
            for p in positions:
                p['time_open'] = datetime.fromisoformat(p['time_open'])
            self.positions = positions
            print(f"[PAPER] Loaded previous session: Balance ${self.balance:.2f}")
        except Exception as e:
            print(f"[PAPER] Could not load session: {e}")
