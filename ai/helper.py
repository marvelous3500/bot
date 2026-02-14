"""
AI helper: signal confidence (1-5) and trade explanation via OpenAI.
If OPENAI_API_KEY is missing or AI is disabled, returns None / empty string.
"""
import os
import re

def _get_client():
    """Return OpenAI client or None if no key."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key.strip())
    except Exception:
        return None


def get_signal_confidence(signal):
    """
    Score trading setup confidence 1 (low) to 5 (high).
    Returns float in [1, 5] or None if disabled/error.
    """
    try:
        import config
        if not getattr(config, 'AI_ENABLED', False):
            return None
    except Exception:
        return None
    client = _get_client()
    if not client:
        return None
    summary = (
        f"Strategy reason: {signal.get('reason', 'N/A')}. "
        f"Symbol: {signal.get('symbol', 'N/A')}. "
        f"Direction: {signal.get('type', 'N/A')}. "
        f"Entry: {signal.get('price')}, SL: {signal.get('sl')}, TP: {signal.get('tp')}."
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You score trading setups from 1 (low confidence) to 5 (high confidence). Reply with only a single integer 1, 2, 3, 4, or 5."},
                {"role": "user", "content": summary}
            ],
            max_tokens=10,
        )
        text = (r.choices[0].message.content or "").strip()
        match = re.search(r"[1-5]", text)
        if match:
            return float(match.group())
    except Exception:
        pass
    return None


def explain_trade(trade_summary):
    """
    Return a short plain-English explanation of the trade.
    Returns str or "" if disabled/error.
    """
    try:
        import config
        if not getattr(config, 'AI_EXPLAIN_TRADES', False):
            return ""
    except Exception:
        return ""
    client = _get_client()
    if not client:
        return ""
    summary = (
        f"Strategy: {trade_summary.get('reason', 'N/A')}. "
        f"Symbol: {trade_summary.get('symbol', 'N/A')}. "
        f"Direction: {trade_summary.get('type', 'N/A')}. "
        f"Entry: {trade_summary.get('price')}, SL: {trade_summary.get('sl')}, TP: {trade_summary.get('tp')}. "
        f"Outcome: {trade_summary.get('outcome', 'N/A')}."
    )
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Explain this trade in 2 short sentences for a trader. Be concise."},
                {"role": "user", "content": summary}
            ],
            max_tokens=150,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception:
        return ""
