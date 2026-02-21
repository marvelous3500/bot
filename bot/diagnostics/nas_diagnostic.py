"""
NAS Strategy Diagnostic Module — professional quant-level debugging.
Automatically tracks and reports why every trade was rejected.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class RejectionEvent:
    """Single rejection event with full context."""
    step: str
    reason: str
    timestamp: Optional[pd.Timestamp] = None
    h1_idx: Optional[pd.Timestamp] = None
    bias: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


class NASDiagnosticCollector:
    """
    Collects all NAS strategy rejection events for post-run analysis.
    Use with NasStrategy(diagnostic=collector) and run_backtest().
    """

    def __init__(self, max_events_per_reason: int = 5):
        self.events: List[RejectionEvent] = []
        self.reasons: Counter = Counter()
        self.step_counts: Counter = Counter()
        self.max_events_per_reason = max_events_per_reason
        self._reason_samples: Dict[str, List[RejectionEvent]] = defaultdict(list)
        self.h1_bars_with_bos = 0
        self.h1_bars_examined = 0
        self.m15_bars_evaluated = 0
        self.filter_rejections: Counter = Counter()

    def reject(
        self,
        step: str,
        reason: str,
        timestamp: Optional[pd.Timestamp] = None,
        h1_idx: Optional[pd.Timestamp] = None,
        bias: Optional[str] = None,
        **context,
    ):
        """Record a rejection event."""
        event = RejectionEvent(
            step=step,
            reason=reason,
            timestamp=timestamp,
            h1_idx=h1_idx,
            bias=bias,
            context=context,
        )
        self.events.append(event)
        self.reasons[reason] += 1
        self.step_counts[step] += 1

        if len(self._reason_samples[reason]) < self.max_events_per_reason:
            self._reason_samples[reason].append(event)

    def record_h1_bos(self):
        """Record that an H1 bar had BOS (bull or bear)."""
        self.h1_bars_with_bos += 1

    def record_h1_examined(self):
        """Record that an H1 bar was examined (had BOS)."""
        self.h1_bars_examined += 1

    def record_filter_reject(self, reason: str):
        """Record a filter rejection (session, news, ATR, spread)."""
        self.filter_rejections[reason] += 1
        self.m15_bars_evaluated += 1

    def record_m15_evaluated(self):
        """Record that an M15 bar was evaluated in the entry window."""
        self.m15_bars_evaluated += 1

    def total_rejections(self) -> int:
        return len(self.events)

    def get_summary(self) -> Dict[str, Any]:
        """Return structured summary for programmatic use."""
        total = self.total_rejections()
        return {
            "total_rejections": total,
            "reasons": dict(self.reasons),
            "step_counts": dict(self.step_counts),
            "filter_rejections": dict(self.filter_rejections),
            "h1_bars_with_bos": self.h1_bars_with_bos,
            "h1_bars_examined": self.h1_bars_examined,
            "m15_bars_evaluated": self.m15_bars_evaluated,
        }


def print_nas_diagnostic_report(collector: NASDiagnosticCollector, symbol: str = ""):
    """
    Print a professional quant-level diagnostic report.
    """
    total = collector.total_rejections()
    total_filter = sum(collector.filter_rejections.values())

    print()
    print("=" * 70)
    print("NAS STRATEGY — DIAGNOSTIC REPORT (Trade Rejection Analysis)")
    print("=" * 70)
    if symbol:
        print(f"  Symbol: {symbol}")
    print(f"  Total rejection events: {total}")
    print(f"  Filter rejections (session/news/ATR/spread): {total_filter}")
    print(f"  H1 bars with BOS examined: {collector.h1_bars_with_bos}")
    print(f"  M15 bars evaluated in entry windows: {collector.m15_bars_evaluated}")
    print()

    if total == 0 and total_filter == 0:
        print("  No rejections recorded. Strategy may have taken trades or no setups occurred.")
        print()
        return

    # Rejection reasons summary (sorted by count desc)
    print("-" * 70)
    print("REJECTION REASONS (by frequency)")
    print("-" * 70)
    if collector.reasons:
        max_len = max(len(r) for r in collector.reasons) if collector.reasons else 20
        for reason, count in collector.reasons.most_common():
            pct = 100.0 * count / total if total else 0
            print(f"  {reason:<{max_len}}  {count:>6}  ({pct:>5.1f}%)")
    print()

    # Filter breakdown
    if collector.filter_rejections:
        print("-" * 70)
        print("FILTER REJECTIONS (session / news / ATR / spread)")
        print("-" * 70)
        for reason, count in collector.filter_rejections.most_common():
            pct = 100.0 * count / total_filter if total_filter else 0
            print(f"  {reason:<30}  {count:>6}  ({pct:>5.1f}%)")
        print()

    # Step breakdown
    if collector.step_counts:
        print("-" * 70)
        print("REJECTIONS BY STEP (8-step entry chain)")
        print("-" * 70)
        steps_order = [
            "h1_bias",
            "4h_conflict",
            "filter",
            "sweep_size",
            "displacement_fvg",
            "return_to_fvg",
            "entry_candle",
            "invalid_sl",
        ]
        for step in steps_order:
            if step in collector.step_counts:
                print(f"  {step:<25}  {collector.step_counts[step]:>6}")
        for step, count in collector.step_counts.items():
            if step not in steps_order:
                print(f"  {step:<25}  {count:>6}")
        print()

    # Sample rejections (first few per reason)
    print("-" * 70)
    print("SAMPLE REJECTIONS (with context)")
    print("-" * 70)
    for reason in list(collector.reasons.keys())[:10]:
        samples = collector._reason_samples.get(reason, [])
        if samples:
            print(f"\n  [{reason}]")
            for i, ev in enumerate(samples[:3], 1):
                ts = ev.timestamp.strftime("%Y-%m-%d %H:%M") if ev.timestamp is not None else "N/A"
                ctx = " | ".join(f"{k}={v}" for k, v in list(ev.context.items())[:4])
                print(f"    {i}. {ts}  bias={ev.bias or 'N/A'}  {ctx}")
    print()
    print("=" * 70)
    print()
