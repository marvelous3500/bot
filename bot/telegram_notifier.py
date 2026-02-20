"""
Telegram notifier: send trade setup to a bot before execution.
Used when TELEGRAM_ENABLED=true (live/paper only).
"""
import requests
from datetime import datetime, timezone


def _current_session():
    """Return current session name (London, NY, Asian) from UTC hour."""
    try:
        import config
    except ImportError:
        return "N/A"
    session_hours = getattr(config, 'TRADE_SESSION_HOURS', {})
    hour = datetime.now(timezone.utc).hour
    name = session_hours.get(hour, "Other")
    return name.capitalize()


def send_setup_notification(signal, strategy_name):
    """
    Send the trade setup to Telegram when 1H confirmation is seen, before execution.
    Fails silently (log but don't block) if token/chat_id missing or request fails.
    Returns True if sent successfully, False otherwise.
    """
    try:
        import config
    except ImportError:
        return False
    if not getattr(config, 'TELEGRAM_ENABLED', False):
        return False
    token = getattr(config, 'TELEGRAM_BOT_TOKEN', None)
    chat_id = getattr(config, 'TELEGRAM_CHAT_ID', None)
    if not token or not chat_id:
        if getattr(config, 'MT5_VERBOSE', False):
            print("[TELEGRAM] Skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False
    entry = signal.get('price')
    sl = signal.get('sl')
    tp = signal.get('tp')
    entry_str = f"{float(entry):.1f}" if entry is not None else "N/A"
    sl_str = f"{float(sl):.1f}" if sl is not None else "N/A"
    tp_str = f"{float(tp):.1f}" if tp is not None else "N/A"
    symbol = signal.get('symbol', 'N/A')
    pair = symbol.rstrip('m') if isinstance(symbol, str) else symbol
    bias = "Bullish" if signal.get('type') == 'BUY' else "Bearish"
    strategy_title = strategy_name.replace('_', ' ').title()
    session = _current_session()
    text = f"""📊 {strategy_title} Strategy Setup Detected

Pair: {pair}
Bias: {bias}
Entry Zone: {entry_str}
SL: {sl_str}
TP1: {tp_str}
Session: {session}
"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
        if r.ok:
            return True
        if getattr(config, 'MT5_VERBOSE', False):
            print(f"[TELEGRAM] Failed: {r.status_code} {r.text[:200]}")
        return False
    except Exception as e:
        if getattr(config, 'MT5_VERBOSE', False):
            print(f"[TELEGRAM] Error: {e}")
        return False


def test_telegram(strategy_name="marvellous"):
    """
    Send a test setup notification to Telegram. Use to verify bot token and chat ID.
    Returns True if sent successfully, False otherwise.
    """
    try:
        import config
    except ImportError:
        print("[TELEGRAM] Error: config not found")
        return False
    token = getattr(config, 'TELEGRAM_BOT_TOKEN', None)
    chat_id = getattr(config, 'TELEGRAM_CHAT_ID', None)
    if not token or not chat_id:
        print("[TELEGRAM] Error: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in .env")
        return False
    orig = getattr(config, 'TELEGRAM_ENABLED', False)
    config.TELEGRAM_ENABLED = True
    signal = {
        'type': 'SELL',
        'symbol': 'XAUUSDm',
        'price': 2034.2,
        'sl': 2037.5,
        'tp': 2028,
        'reason': 'Test notification',
    }
    try:
        ok = send_setup_notification(signal, strategy_name)
        if ok:
            print("Telegram test: setup notification sent. Check your bot.")
        else:
            print("Telegram test: failed to send (check token, chat_id, network).")
        return ok
    finally:
        config.TELEGRAM_ENABLED = orig
