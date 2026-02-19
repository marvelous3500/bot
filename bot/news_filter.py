"""
News filter for Marvellous Strategy.
Fetches economic calendar events via investpy (primary) or FCS API (fallback).
"""
from datetime import datetime, timedelta
from typing import Optional

_CACHE: dict = {}
_CACHE_TTL_SEC = 3600  # 1 hour


def _cache_key(from_date: str, to_date: str) -> str:
    return f"{from_date}_{to_date}"


def _is_cache_valid(key: str) -> bool:
    if key not in _CACHE:
        return False
    entry = _CACHE[key]
    return (datetime.utcnow() - entry["fetched_at"]).total_seconds() < _CACHE_TTL_SEC


def _fetch_investpy(from_date: str, to_date: str, countries: list) -> Optional[list]:
    """Fetch events via investpy. Returns list of (datetime_utc, importance) or None on error."""
    try:
        try:
            import investpy
        except ImportError:
            return None
        # investpy uses dd/mm/yyyy
        df = investpy.economic_calendar(
            countries=countries,
            from_date=from_date,
            to_date=to_date,
        )
        if df is None or df.empty:
            return []
        events = []
        date_col = next((c for c in df.columns if "date" in str(c).lower()), "date")
        time_col = next((c for c in df.columns if "time" in str(c).lower()), "time")
        imp_col = next((c for c in df.columns if "import" in str(c).lower()), "importance")
        for _, row in df.iterrows():
            try:
                date_str = str(row.get(date_col, row.get("date", "")))
                time_str = str(row.get(time_col, row.get("time", "00:00")))
                imp = str(row.get(imp_col, row.get("importance", ""))).lower()
                if imp not in ("high", "medium"):
                    continue
                # Parse date (dd/mm/yyyy or yyyy-mm-dd)
                date_str = date_str.strip()
                if "/" in date_str:
                    parts = date_str.split("/")
                    if len(parts) == 3:
                        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                    else:
                        continue
                elif "-" in date_str:
                    parts = date_str.split("-")
                    if len(parts) == 3:
                        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    else:
                        continue
                else:
                    continue
                # Parse time
                t_parts = time_str.replace(":", " ").split()
                h, min_ = 0, 0
                if len(t_parts) >= 2:
                    h, min_ = int(t_parts[0]), int(t_parts[1])
                elif len(t_parts) == 1 and t_parts[0].isdigit():
                    h = int(t_parts[0])
                dt = datetime(y, m, d, h, min_, 0)
                events.append((dt, imp))
            except (ValueError, TypeError, IndexError):
                continue
        return events
    except Exception:
        return None


def _fetch_fcsapi(from_date: str, to_date: str, api_key: str) -> Optional[list]:
    """Fetch events via FCS API. Returns list of (datetime_utc, importance) or None on error."""
    if not api_key:
        return None
    try:
        import urllib.request
        from urllib.parse import urlencode
        # FCS uses YYYY-MM-DD
        params = {"from": from_date, "to": to_date, "access_key": api_key}
        url = f"https://fcsapi.com/api-v3/forex/economy_cal?{urlencode(params)}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read().decode()
        import json
        j = json.loads(data)
        if not j.get("status", False):
            return []
        events = []
        for item in j.get("response", []) or []:
            imp = str(item.get("importance", "")).lower()
            if imp not in ("high", "medium"):
                continue
            dt_str = item.get("date") or item.get("datetime") or ""
            if not dt_str:
                continue
            try:
                # Try common formats
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                    try:
                        dt = datetime.strptime(dt_str[:19], fmt)
                        events.append((dt, imp))
                        break
                    except ValueError:
                        continue
            except (ValueError, TypeError):
                continue
        return events
    except Exception:
        return None


def fetch_news_events(
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    countries: Optional[list] = None,
    api: str = "investpy",
    api_key: Optional[str] = None,
) -> list:
    """
    Fetch economic calendar events for the given date range.
    Returns list of (datetime_utc, importance) where importance is 'high' or 'medium'.
    """
    now = datetime.utcnow()
    from_dt = from_date or (now - timedelta(days=1))
    to_dt = to_date or (now + timedelta(days=1))
    countries = countries or ["United States", "Euro Zone"]
    from_str = from_dt.strftime("%d/%m/%Y")
    to_str = to_dt.strftime("%d/%m/%Y")
    cache_key = _cache_key(from_str, to_str)
    if _is_cache_valid(cache_key):
        return _CACHE[cache_key]["events"]
    events = None
    if api == "fcsapi" and api_key:
        from_fcs = from_dt.strftime("%Y-%m-%d")
        to_fcs = to_dt.strftime("%Y-%m-%d")
        events = _fetch_fcsapi(from_fcs, to_fcs, api_key)
    if events is None:
        events = _fetch_investpy(from_str, to_str, countries)
    if events is None and api == "investpy" and api_key:
        from_fcs = from_dt.strftime("%Y-%m-%d")
        to_fcs = to_dt.strftime("%Y-%m-%d")
        events = _fetch_fcsapi(from_fcs, to_fcs, api_key)
    if events is None:
        events = []
    _CACHE[cache_key] = {"events": events, "fetched_at": datetime.utcnow()}
    return events


def is_news_safe(
    current_time: datetime,
    buffer_before_minutes: int = 15,
    buffer_after_minutes: int = 15,
    avoid_news: bool = True,
    countries: Optional[list] = None,
    api: str = "investpy",
    api_key: Optional[str] = None,
) -> bool:
    """
    Return True if it is safe to trade (no high/medium impact news within buffer).
    When avoid_news=False, always returns True.
    """
    if not avoid_news:
        return True
    from_dt = current_time - timedelta(days=1)
    to_dt = current_time + timedelta(days=1)
    events = fetch_news_events(
        from_date=from_dt,
        to_date=to_dt,
        countries=countries,
        api=api,
        api_key=api_key,
    )
    delta_before = timedelta(minutes=buffer_before_minutes)
    delta_after = timedelta(minutes=buffer_after_minutes)
    for event_time, _ in events:
        if event_time - delta_before <= current_time <= event_time + delta_after:
            return False
    return True
