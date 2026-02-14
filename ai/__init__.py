"""AI package: signal confidence and trade explanation (OpenAI), voice alerts."""
from .helper import get_signal_confidence, explain_trade
from .voice import speak

__all__ = ["get_signal_confidence", "explain_trade", "speak"]
