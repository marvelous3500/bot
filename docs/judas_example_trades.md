# NAS Judas Strategy — Example Trades

This document describes example trades that illustrate the full 10-step confirmation chain of the NAS Judas Strategy.

---

## Trade 1: Bullish Judas (BUY)

**Symbol:** ^NDX (NAS100)  
**Direction:** BUY  
**Timestamp:** 2025-01-15 10:45 UTC (NY kill zone)

### Step-by-Step Confirmation

| Step | Condition | Result |
|------|-----------|--------|
| 1 | Session | NY kill zone 09:30–11:30 UTC |
| 2 | Judas move | Sweep of lows detected (fake move below swing low) |
| 3 | Sweep | Wick beyond swing low 19950, close back inside |
| 4 | Sweep size | 42 points ≥ 35 min |
| 5 | Displacement | Bull candle body 2.1× avg (≥ 1.8) |
| 6 | Structure shift | Close breaks above recent swing low |
| 7 | FVG | Bull FVG formed, size 22 points |
| 8 | Retrace | Price returns into FVG zone |
| 9 | Entry candle | Bullish close, body in FVG |
| 10 | Execute | BUY @ 20085, SL 19942, TP 20128 |

**Outcome:** WIN (price reached TP before SL)

---

## Trade 2: Bearish Judas (SELL)

**Symbol:** ^NDX (NAS100)  
**Direction:** SELL  
**Timestamp:** 2025-01-16 04:15 UTC (London kill zone)

### Step-by-Step Confirmation

| Step | Condition | Result |
|------|-----------|--------|
| 1 | Session | London kill zone 03:00–05:00 UTC |
| 2 | Judas move | Sweep of highs detected |
| 3 | Sweep | Wick beyond swing high 20220, close back inside |
| 4 | Sweep size | 38 points ≥ 35 min |
| 5 | Displacement | Bear candle body 1.9× avg |
| 6 | Structure shift | Close breaks below recent swing high |
| 7 | FVG | Bear FVG formed, size 20 points |
| 8 | Retrace | Price returns into FVG zone |
| 9 | Entry candle | Bearish close, body in FVG |
| 10 | Execute | SELL @ 20150, SL 20208, TP 20092 |

**Outcome:** LOSS (price hit SL before TP)

---

## Trade 3: Rejected — Sweep Too Small

**Symbol:** ^NDX (NAS100)  
**Direction:** BUY (attempted)  
**Timestamp:** 2025-01-17 10:00 UTC

### Rejection Reason

| Step | Condition | Result |
|------|-----------|--------|
| 1 | Session | Pass |
| 2 | Judas move | Sweep detected |
| 3 | Sweep | Wick beyond swing |
| 4 | Sweep size | **28 points < 35 min** → **REJECT** |

**Outcome:** No trade. Confirmation chain incomplete at step 4.

---

## Summary

- **Trade 1:** Full chain → BUY → WIN  
- **Trade 2:** Full chain → SELL → LOSS  
- **Trade 3:** Chain broken at sweep size → no trade  

The strategy never trades sweeps directly. It waits for liquidity trap + displacement + structure shift + FVG retrace + entry candle before executing.
