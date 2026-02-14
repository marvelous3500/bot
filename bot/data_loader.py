import time
import yfinance as yf
import pandas as pd
import os

# Retry config for Yahoo Finance (handles transient None/timeouts)
YF_MAX_RETRIES = 3
YF_RETRY_DELAY_SEC = 3


def fetch_data_yfinance(symbol, period='5d', interval='5m'):
    """Fetches historical data from Yahoo Finance with retries on transient failures."""
    print(f"Fetching {period} of data for {symbol} at {interval} interval...")
    last_error = None
    for attempt in range(1, YF_MAX_RETRIES + 1):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            if df is not None and not df.empty:
                break
            last_error = RuntimeError(f"No data returned for {symbol} ({interval}).")
        except (TypeError, KeyError) as e:
            # yfinance often raises TypeError when API returns None/invalid JSON
            last_error = e
        except Exception as e:
            last_error = e
        if attempt < YF_MAX_RETRIES:
            print(f"  Retry {attempt}/{YF_MAX_RETRIES} in {YF_RETRY_DELAY_SEC}s...")
            time.sleep(YF_RETRY_DELAY_SEC)
    else:
        raise RuntimeError(
            f"Failed to fetch {symbol} ({interval}) after {YF_MAX_RETRIES} attempts: {last_error}"
        ) from last_error
    if df is None or df.empty:
        raise RuntimeError(f"No data returned for {symbol} ({interval}). Check symbol and period.")
    df = df.rename(columns={
        'Open': 'open',
        'High': 'high',
        'Low': 'low',
        'Close': 'close',
        'Volume': 'volume'
    })
    df = df[['open', 'high', 'low', 'close', 'volume']].dropna()
    return df

def fetch_daily_data_yfinance(symbol, period='1mo'):
    """Fetches daily data for PDH/PDL calculation."""
    return fetch_data_yfinance(symbol, period=period, interval='1d')

def load_data_csv(filepath):
    """Loads data from a CSV file."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CSV file not found: {filepath}")
    df = pd.read_csv(filepath)
    df.columns = [c.lower() for c in df.columns]
    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)
    elif 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
    return df
