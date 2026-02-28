"""
TrendVesterStrategy: follow current trend (H1 BOS only) + vester 1M entry.
Simpler than vester: no H1 zone confirmation, no H1 liquidity sweep, no 5M sweep required.
Use when vester has not taken a trade in days — more signals to test entry/execution.
"""
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple, List

import config
from .strategy_vester import VesterStrategy, _atr, _price_in_zone, _get_fvg_zones
from .. import vester_config as vc


class TrendVesterStrategy(VesterStrategy):
    """
    Trend + vester 1M entry. Bias = H1 BOS only (current trend). Setup = 5M BOS + zone (OB/FVG/ATR).
    No H1 zone confirmation, no H1 liquidity sweep, no 5M sweep required — more trades.
    """

    def _get_trend_bias(self, df_h1_slice: pd.DataFrame) -> Optional[str]:
        """Current trend from most recent H1 BOS in lookback. No zone confirmation, no liquidity sweep."""
        if df_h1_slice is None or df_h1_slice.empty or len(df_h1_slice) < 3:
            return None
        end = len(df_h1_slice)
        lookback = min(50, end)
        for i in range(end - 1, max(0, end - lookback) - 1, -1):
            if i < 0:
                break
            row = df_h1_slice.iloc[i]
            if row.get("bos_bull"):
                return "BULLISH"
            if row.get("bos_bear"):
                return "BEARISH"
        return None

    def run_backtest(self, only_last_n_bars: Optional[int] = None) -> pd.DataFrame:
        """
        Same data flow as vester but: bias = H1 BOS only; 5M sweep not required; no 4H/breaker/P&D.
        Reuses vester's 5M zone + 1M entry logic.
        """
        if self.df_h1.empty or self.df_m5.empty or self.df_m1.empty:
            return pd.DataFrame()

        self._live_setup_status = None
        signals = []
        entry_df = self.df_m1
        atr_series = _atr(entry_df, 14)
        atr_m5 = _atr(self.df_m5, 14) if not self.df_m5.empty else None
        ob_lookback = vc.OB_LOOKBACK
        liq_lookback = vc.LIQUIDITY_LOOKBACK
        min_rr = vc.MIN_RR
        trades_per_session: Dict[str, int] = {}
        trades_per_day: Dict[str, int] = {}
        daily_loss: Dict[str, float] = {}
        max_per_setup = getattr(config, "TREND_VESTER_MAX_TRADES_PER_SETUP", 3)
        trades_per_5m_setup: Dict = {}
        trades_per_sl_key: Dict[str, int] = {}
        max_per_sl = getattr(config, "VESTER_MAX_TRADES_PER_SL_LEVEL", 1)
        apply_limits = getattr(config, "BACKTEST_APPLY_TRADE_LIMITS", False)
        m5_window = getattr(vc, "M5_WINDOW_HOURS", 12)

        start_i = 100
        if only_last_n_bars is not None and only_last_n_bars > 0:
            start_i = max(100, len(entry_df) - only_last_n_bars)

        for i in range(start_i, len(entry_df)):
            idx = entry_df.index[i]
            current_time = idx if hasattr(idx, "hour") else pd.Timestamp(idx)

            if getattr(config, "BACKTEST_EXCLUDE_WEEKENDS", False) and current_time.weekday() >= 5:
                continue

            session_key = config.TRADE_SESSION_HOURS.get(current_time.hour, "other")
            day_key = current_time.strftime("%Y-%m-%d") if hasattr(current_time, "strftime") else str(current_time.date())

            if apply_limits:
                max_per_day = getattr(config, "BACKTEST_MAX_TRADES_PER_DAY", config.MAX_TRADES_PER_DAY)
                max_per_session = getattr(config, "BACKTEST_MAX_TRADES_PER_SESSION", config.MAX_TRADES_PER_SESSION)
                if trades_per_day.get(day_key, 0) >= max_per_day:
                    continue
                if max_per_session is not None and session_key != "other":
                    if trades_per_session.get(session_key, 0) >= max_per_session:
                        continue
            else:
                if trades_per_session.get(session_key, 0) >= getattr(config, "TREND_VESTER_MAX_TRADES_PER_SESSION", vc.MAX_TRADES_PER_SESSION):
                    continue
            if daily_loss.get(day_key, 0) >= config.INITIAL_BALANCE * (vc.DAILY_LOSS_LIMIT_PCT / 100.0):
                continue

            df_h1_slice = self.df_h1[self.df_h1.index <= idx].tail(vc.HTF_LOOKBACK_HOURS)
            if df_h1_slice.empty or len(df_h1_slice) < 5:
                continue

            bias = self._get_trend_bias(df_h1_slice)
            if bias is None:
                continue

            df_m5_slice = self.df_m5[(self.df_m5.index <= idx) & (self.df_m5.index >= idx - pd.Timedelta(hours=m5_window))]
            if df_m5_slice.empty:
                continue

            swept, liq_level, _ = self.detectLiquiditySweep(df_m5_slice, "BUY" if bias == "BULLISH" else "SELL", liq_lookback)
            if not swept:
                liq_level = None

            struct_shift, bos_idx = self.detectStructureShift(df_m5_slice)
            if struct_shift != bias:
                continue
            bos_row = df_m5_slice.iloc[bos_idx] if bos_idx is not None and bos_idx < len(df_m5_slice) else None
            broken_level = None
            if bos_row is not None:
                broken_level = bos_row.get("bos_bull_broken_level") if struct_shift == "BULLISH" else bos_row.get("bos_bear_broken_level")
                if broken_level is not None and pd.isna(broken_level):
                    broken_level = None

            entry_zone_top, entry_zone_bottom = None, None
            current_ob = None
            if bos_idx is not None:
                current_ob = self.detectOrderBlock(df_m5_slice, bos_idx)
            if current_ob is not None:
                entry_zone_top, entry_zone_bottom = current_ob["high"], current_ob["low"]
            if entry_zone_top is None:
                zones = _get_fvg_zones(df_m5_slice, 0, len(df_m5_slice))
                for zt, zb, zd in reversed(zones):
                    if zd == bias:
                        entry_zone_top, entry_zone_bottom = zt, zb
                        break
            if entry_zone_top is None and liq_level is not None:
                bar_row = entry_df.iloc[i]
                atr_val = atr_series.iloc[i] if i < len(atr_series) and atr_series is not None else np.nan
                atr_val = float(atr_val) if not pd.isna(atr_val) and atr_val > 0 else (bar_row["high"] - bar_row["low"]) * 2
                half = atr_val * getattr(vc, "LIQ_ZONE_ATR_MULT", 0.5)
                if bias == "BULLISH":
                    entry_zone_bottom = float(liq_level) - half
                    entry_zone_top = float(liq_level) + half
                else:
                    entry_zone_top = float(liq_level) + half
                    entry_zone_bottom = float(liq_level) - half
            if entry_zone_top is None:
                bar_row = entry_df.iloc[i]
                atr_val = atr_series.iloc[i] if i < len(atr_series) and atr_series is not None else np.nan
                atr_val = float(atr_val) if not pd.isna(atr_val) and atr_val > 0 else (bar_row["high"] - bar_row["low"]) * 2
                mid = (bar_row["high"] + bar_row["low"]) / 2
                half = atr_val * getattr(vc, "LIQ_ZONE_ATR_MULT", 0.5)
                entry_zone_bottom = mid - half
                entry_zone_top = mid + half
            if entry_zone_top is None:
                continue

            if only_last_n_bars is not None:
                direction = "SELL" if bias == "BEARISH" else "BUY"
                wait_1m = "price in zone + bearish candle | or 1M BOS down in zone | or sweep high + bearish displacement" if direction == "SELL" else "price in zone + bullish candle | or 1M BOS up in zone | or sweep low + bullish displacement"
                self._live_setup_status = {"direction": direction, "zone_top": entry_zone_top, "zone_bottom": entry_zone_bottom, "waiting_1m": wait_1m}

            df_m1_slice = entry_df.iloc[: i + 1]
            if len(df_m1_slice) < 20:
                continue

            row = entry_df.iloc[i]
            in_zone = _price_in_zone(row["low"], row["high"], entry_zone_top, entry_zone_bottom)
            if not in_zone:
                continue

            triggered, entry_price, trigger_reason = self.checkEntryTrigger(
                df_m1_slice, "BUY" if bias == "BULLISH" else "SELL",
                entry_zone_top, entry_zone_bottom, i,
            )
            if not triggered or entry_price is None:
                continue
            if only_last_n_bars is not None:
                self._live_setup_status = None

            if getattr(config, "VESTER_USE_CONFIRMED_BOS_ONLY", False) and broken_level is not None and not pd.isna(broken_level):
                from ..indicators_bos import is_bos_still_valid_on_entry_df
                bos_time = df_m5_slice.index[bos_idx] if bos_idx is not None and bos_idx < len(df_m5_slice) else None
                if bos_time is not None:
                    df_m1_up_to = self.df_m1[self.df_m1.index <= idx]
                    if not is_bos_still_valid_on_entry_df(df_m1_up_to, bos_time, idx, float(broken_level), struct_shift):
                        continue

            m5_bar_ts = idx.floor("5min") if hasattr(idx, "floor") else pd.Timestamp(idx).floor("5min")
            if max_per_setup is not None and trades_per_5m_setup.get(m5_bar_ts, 0) >= max_per_setup:
                continue

            if getattr(config, "USE_ZONE_DIRECTION_FILTER", False):
                from ..indicators import price_in_buyside_liquidity, price_in_sellside_liquidity
                from ..indicators import get_equilibrium
                lookback = getattr(config, "ZONE_DIRECTION_FVG_LOOKBACK", 30)
                buffer_pct = getattr(config, "ZONE_DIRECTION_BUFFER_PCT", 0.001)
                use_eq = getattr(config, "ZONE_DIRECTION_USE_EQUILIBRIUM", True)
                equilibrium_zd = None
                if use_eq:
                    eq_lookback = getattr(vc, "EQUILIBRIUM_LOOKBACK", 24)
                    df_eq_slice = self.df_h1[self.df_h1.index <= idx].tail(eq_lookback)
                    if df_eq_slice is not None and not df_eq_slice.empty:
                        equilibrium_zd = get_equilibrium(df_eq_slice, eq_lookback)
                if bias == "BULLISH":
                    if price_in_buyside_liquidity(entry_price, df_m5_slice, lookback, equilibrium=equilibrium_zd, buffer_pct=buffer_pct, use_equilibrium=use_eq):
                        continue
                else:
                    if price_in_sellside_liquidity(entry_price, df_m5_slice, lookback, equilibrium=equilibrium_zd, buffer_pct=buffer_pct, use_equilibrium=use_eq):
                        continue

            if current_ob is None:
                current_ob = {"high": entry_zone_top, "low": entry_zone_bottom, "midpoint": (entry_zone_top + entry_zone_bottom) / 2}

            sl_method = getattr(vc, "SL_METHOD", "OB")
            sl_atr_mult = getattr(vc, "SL_ATR_MULT", 0.5)
            sl_micro_tf = getattr(vc, "SL_MICRO_TF", "1m")
            pip = 0.01 if "XAU" in str(self.symbol or "") or "GC" in str(self.symbol or "") else 0.0001

            if sl_method == "HYBRID":
                micro_df = df_m1_slice if sl_micro_tf == "1m" else df_m5_slice
                micro_atr = atr_series if sl_micro_tf == "1m" else atr_m5
                base_swing = None
                if bias == "BULLISH":
                    swing_lows = micro_df[micro_df["swing_low"] == True]
                    if not swing_lows.empty:
                        base_swing = float(swing_lows.iloc[-1]["swing_low_price"])
                else:
                    swing_highs = micro_df[micro_df["swing_high"] == True]
                    if not swing_highs.empty:
                        base_swing = float(swing_highs.iloc[-1]["swing_high_price"])
                if base_swing is not None and micro_atr is not None:
                    if sl_micro_tf == "5m":
                        m5_up_to = self.df_m5[self.df_m5.index <= idx]
                        atr_val = atr_m5.loc[m5_up_to.index[-1]] if not m5_up_to.empty and m5_up_to.index[-1] in atr_m5.index else np.nan
                    else:
                        atr_val = atr_series.iloc[i] if i < len(atr_series) else np.nan
                    atr_val = float(atr_val) if not pd.isna(atr_val) and atr_val > 0 else (row["high"] - row["low"]) * 2
                    buf = atr_val * sl_atr_mult
                    if bias == "BULLISH":
                        sl = base_swing - buf
                        if sl >= entry_price:
                            sl = entry_price - pip
                    else:
                        sl = base_swing + buf
                        if sl <= entry_price:
                            sl = entry_price + pip
                else:
                    sl_method = "OB"
            if sl_method != "HYBRID":
                sl_buffer = config.get_symbol_config(self.symbol, "VESTER_SL_BUFFER") or vc.SL_BUFFER
                buf = sl_buffer * pip
                if bias == "BULLISH":
                    sl = current_ob["low"] - buf
                    if sl >= entry_price:
                        sl = entry_price - pip
                else:
                    sl = current_ob["high"] + buf
                    if sl <= entry_price:
                        sl = entry_price + pip

            min_sl_pips = config.get_symbol_config(self.symbol, "VESTER_MIN_SL_PIPS") or getattr(config, "VESTER_MIN_SL_PIPS", 5.0)
            min_sl_dist = min_sl_pips * pip
            if bias == "BULLISH":
                if (entry_price - sl) < min_sl_dist:
                    sl = entry_price - min_sl_dist
            else:
                if (sl - entry_price) < min_sl_dist:
                    sl = entry_price + min_sl_dist

            if bias == "BULLISH":
                future_highs = self.df_m5[(self.df_m5.index > idx) & (self.df_m5["swing_high"] == True)].head(3)
                tp = future_highs.iloc[0]["swing_high_price"] if not future_highs.empty else None
                sl_dist = entry_price - sl
                min_tp = entry_price + sl_dist * min_rr
                if tp is None or tp < min_tp:
                    tp = min_tp
            else:
                future_lows = self.df_m5[(self.df_m5.index > idx) & (self.df_m5["swing_low"] == True)].head(3)
                tp = future_lows.iloc[0]["swing_low_price"] if not future_lows.empty else None
                sl_dist = sl - entry_price
                min_tp = entry_price - sl_dist * min_rr
                if tp is None or tp > min_tp:
                    tp = min_tp

            spread_pips = config.get_symbol_config(self.symbol, "BACKTEST_SPREAD_PIPS") or getattr(config, "BACKTEST_SPREAD_PIPS", 2.0)
            max_spread = config.get_symbol_config(self.symbol, "VESTER_MAX_SPREAD_POINTS") or vc.MAX_SPREAD_POINTS
            pip_size = 0.01 if "XAU" in str(self.symbol or "") or "GC" in str(self.symbol or "") else 0.0001
            spread_points = spread_pips * (pip_size * 10 if pip_size == 0.0001 else 1)
            if spread_points > max_spread:
                continue

            atr_val = atr_series.iloc[i] if i < len(atr_series) and atr_series is not None else np.nan
            if not pd.isna(atr_val) and atr_val > 0:
                bar_range = row["high"] - row["low"]
                if bar_range > atr_val * vc.MAX_CANDLE_VOLATILITY_ATR_MULT:
                    continue

            if vc.USE_NEWS_FILTER:
                from ..news_filter import is_news_safe
                if not is_news_safe(
                    current_time,
                    vc.NEWS_BUFFER_MINUTES,
                    vc.NEWS_BUFFER_MINUTES,
                    True,
                    ["United States", "Euro Zone"],
                    "investpy",
                    getattr(config, "FCSAPI_KEY", None),
                ):
                    continue

            sl_key = f"{round(float(sl), 2)}" if ("XAU" in str(self.symbol or "") or "GC" in str(self.symbol or "")) else f"{round(float(sl), 5)}"
            if max_per_sl is not None and trades_per_sl_key.get(sl_key, 0) >= max_per_sl:
                continue

            reason = f"TrendVester: H1 trend {bias} + 5M zone + {trigger_reason}"
            sig = self.placeTrade("BUY" if bias == "BULLISH" else "SELL", entry_price, sl, tp, idx, reason)
            sig["setup_5m"] = m5_bar_ts
            signals.append(sig)
            trades_per_sl_key[sl_key] = trades_per_sl_key.get(sl_key, 0) + 1
            trades_per_5m_setup[m5_bar_ts] = trades_per_5m_setup.get(m5_bar_ts, 0) + 1
            trades_per_session[session_key] = trades_per_session.get(session_key, 0) + 1
            trades_per_day[day_key] = trades_per_day.get(day_key, 0) + 1

        return pd.DataFrame(signals)
