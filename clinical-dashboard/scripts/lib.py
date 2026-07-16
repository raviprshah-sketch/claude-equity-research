"""Shared helpers for the clinical-trial dashboard pipeline. Standard library only."""
import json
import os
import time
import urllib.request
import urllib.error
from datetime import date, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
OUTPUT = os.path.join(BASE, "output")

# A descriptive User-Agent is required by SEC EDGAR. Override via env for your own contact.
USER_AGENT = os.environ.get(
    "DASHBOARD_UA", "claude-equity-research clinical-dashboard (contact: set DASHBOARD_UA)"
)


def load_json(name):
    with open(os.path.join(DATA, name), "r") as f:
        return json.load(f)


def save_json(name, obj):
    path = os.path.join(DATA, name)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
    return path


def http_get(url, headers=None, retries=4, timeout=30):
    """GET with exponential backoff. Returns bytes or raises the last error."""
    hdrs = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    if headers:
        hdrs.update(headers)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                return raw
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    raise last


def today():
    return date.today().isoformat()


def parse_iso(s):
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def days_until(iso_str, ref=None):
    d = parse_iso(iso_str)
    if not d:
        return None
    ref = ref or date.today()
    return (d - ref).days
