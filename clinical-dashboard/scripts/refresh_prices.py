"""Fetch daily prices from Stooq (no API key) and compute performance windows.

Writes data/prices.json:
{
  "as_of": "YYYY-MM-DD",
  "prices": { "MDGL": {"last": 380.1, "ret_1m": 0.04, "ret_3m": .., "ret_ytd": .., "ret_12m": ..,
                        "high_52w": .., "low_52w": .., "history": [[date, close], ...last 400]} }
}
"""
import csv
import io
from datetime import date, timedelta

from lib import http_get, save_json, load_json, today, parse_iso


def all_tickers():
    holdings = load_json("holdings.json")["holdings"]
    tickers = set()
    for lst in holdings.values():
        for h in lst:
            tickers.add(h["ticker"])
    # include any ticker that appears in catalysts too
    for c in load_json("catalysts.json")["catalysts"]:
        tickers.add(c["ticker"])
    return sorted(tickers)


def fetch_stooq(ticker):
    """Return list of (date, close) sorted ascending, or [] on failure."""
    url = "https://stooq.com/q/d/l/?s=%s.us&i=d" % ticker.lower()
    try:
        raw = http_get(url).decode("utf-8", "replace")
    except Exception as e:  # noqa
        print("  ! %s fetch failed: %s" % (ticker, e))
        return []
    rows = []
    reader = csv.DictReader(io.StringIO(raw))
    for r in reader:
        try:
            rows.append((r["Date"], float(r["Close"])))
        except (KeyError, ValueError, TypeError):
            continue
    return rows


def ret(hist, days_back):
    """Total return over a trailing window using nearest available prior close."""
    if not hist:
        return None
    last_d, last_c = hist[-1]
    target = parse_iso(last_d) - timedelta(days=days_back)
    prior = None
    for d, c in hist:
        if parse_iso(d) <= target:
            prior = c
        else:
            break
    if prior is None or prior == 0:
        return None
    return round((last_c / prior) - 1.0, 4)


def ytd_ret(hist):
    if not hist:
        return None
    last_d, last_c = hist[-1]
    year = parse_iso(last_d).year
    base = None
    for d, c in hist:
        if parse_iso(d).year == year:
            base = c
            break
    if base is None or base == 0:
        return None
    return round((last_c / base) - 1.0, 4)


def main():
    out = {"as_of": today(), "prices": {}}
    for t in all_tickers():
        hist = fetch_stooq(t)
        if not hist:
            out["prices"][t] = {"last": None, "error": "no data"}
            continue
        last_d, last_c = hist[-1]
        window = hist[-400:]
        closes_52w = [c for d, c in hist if parse_iso(d) >= date.today() - timedelta(days=365)]
        out["prices"][t] = {
            "last": round(last_c, 2),
            "last_date": last_d,
            "ret_1m": ret(hist, 30),
            "ret_3m": ret(hist, 91),
            "ret_ytd": ytd_ret(hist),
            "ret_12m": ret(hist, 365),
            "high_52w": round(max(closes_52w), 2) if closes_52w else None,
            "low_52w": round(min(closes_52w), 2) if closes_52w else None,
            "history": [[d, round(c, 2)] for d, c in window],
        }
        print("  %s: %s (1m %s, YTD %s)" % (t, last_c, out["prices"][t]["ret_1m"], out["prices"][t]["ret_ytd"]))
    save_json("prices.json", out)
    print("Wrote prices for %d tickers" % len(out["prices"]))


if __name__ == "__main__":
    main()
