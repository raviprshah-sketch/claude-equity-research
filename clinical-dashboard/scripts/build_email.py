"""Build the monthly summary email (inline-styled HTML + plaintext).

Email clients ignore <style>/CSS variables, so everything here is inline-styled,
light-theme, table-based. Content:
  - Portfolio performance snapshot (top positions, 1M / YTD)
  - Catalysts in the next ~90 days (the month's watch-list)
  - Readouts reported in the last ~35 days (what just happened)
  - Recurring commercial trajectories to check on earnings

Writes output/monthly_email.html and output/monthly_email.txt.
"""
import os
from datetime import date

from lib import load_json, days_until, OUTPUT

INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e6e5df"
GOOD = "#0a7a0a"
NEG = "#c0392b"
BLUE = "#1f6fd0"
CARD = "#ffffff"
PAGE = "#f4f4f1"


def esc(s):
    import html
    return html.escape(str(s if s is not None else ""))


def pct(x):
    if x is None:
        return "—"
    return ("+%.1f%%" % (x * 100)) if x >= 0 else ("%.1f%%" % (x * 100))


def color_for(x):
    if x is None:
        return MUTED
    return GOOD if x >= 0 else NEG


def build():
    holdings = load_json("holdings.json")
    catalysts = load_json("catalysts.json")
    funds = load_json("funds.json")
    try:
        prices = load_json("prices.json")
    except Exception:
        prices = {"prices": {}}
    px = prices.get("prices", {})

    month = date.today().strftime("%B %Y")

    # unique positions with fund tags
    ticker_funds, ticker_name = {}, {}
    for fid, lst in holdings["holdings"].items():
        for h in lst:
            ticker_funds.setdefault(h["ticker"], set()).add(fid.upper())
            ticker_name[h["ticker"]] = h["name"]

    cats = catalysts["catalysts"]
    soon = sorted([c for c in cats if c.get("status") == "upcoming"
                   and 0 <= (days_until(c["sort_date"]) or 9999) <= 100],
                  key=lambda c: c["sort_date"])
    recent = sorted([c for c in cats if c.get("status") == "reported"
                     and -40 <= (days_until(c["sort_date"]) or -9999) <= 0],
                    key=lambda c: c["sort_date"], reverse=True)
    recurring = [c for c in cats if c.get("status") == "recurring"]

    # ---- performance rows (sorted by YTD desc where available) ----
    perf = []
    for t in ticker_name:
        p = px.get(t, {})
        perf.append((t, p))
    perf.sort(key=lambda tp: (tp[1].get("ret_ytd") is None, -(tp[1].get("ret_ytd") or 0)))

    def perf_table():
        if not any(p.get("last") for _, p in perf):
            return ("<tr><td style='padding:10px;color:%s;font-style:italic'>Price data populates after the "
                    "first automated refresh.</td></tr>" % MUTED)
        rows = ""
        for t, p in perf:
            if not p.get("last"):
                continue
            funds_tag = " ".join(sorted(ticker_funds.get(t, [])))
            rows += (
                "<tr>"
                "<td style='padding:7px 8px;border-top:1px solid %s;font-weight:700'>%s</td>"
                "<td style='padding:7px 8px;border-top:1px solid %s;color:%s;font-size:13px'>%s</td>"
                "<td style='padding:7px 8px;border-top:1px solid %s;text-align:right;font-variant-numeric:tabular-nums'>$%.2f</td>"
                "<td style='padding:7px 8px;border-top:1px solid %s;text-align:right;color:%s;font-weight:600'>%s</td>"
                "<td style='padding:7px 8px;border-top:1px solid %s;text-align:right;color:%s;font-weight:600'>%s</td>"
                "<td style='padding:7px 8px;border-top:1px solid %s;color:%s;font-size:11px'>%s</td>"
                "</tr>"
            ) % (GRID, esc(t), GRID, INK2, esc(ticker_name[t]),
                 GRID, p["last"],
                 GRID, color_for(p.get("ret_1m")), pct(p.get("ret_1m")),
                 GRID, color_for(p.get("ret_ytd")), pct(p.get("ret_ytd")),
                 GRID, BLUE, funds_tag)
        return rows

    def cat_block(c, show_countdown=True):
        d = days_until(c["sort_date"])
        tag = ""
        if show_countdown and d is not None and d >= 0:
            tag = "<span style='color:%s;font-weight:600'>&nbsp;· T−%d d</span>" % (NEG, d)
        holders = " ".join(sorted(ticker_funds.get(c["ticker"], [])))
        impc = {"high": NEG, "medium": "#b9770e", "low": MUTED}.get(c["importance"], MUTED)
        return (
            "<tr><td style='padding:11px 0;border-top:1px solid %s'>"
            "<div style='font-size:13px'>"
            "<span style='font-weight:700'>%s</span> "
            "<span style='color:%s'>%s</span>"
            "<span style='color:%s;font-weight:600;font-size:11px'>&nbsp;· %s</span>%s</div>"
            "<div style='font-weight:600;margin-top:2px'>%s <span style='color:%s;font-weight:400'>— %s</span></div>"
            "<div style='color:%s;font-size:12px;margin-top:3px;max-width:60ch'>%s</div>"
            "<div style='color:%s;font-size:11px;margin-top:4px'>Held by %s · <span style='color:%s'>%s importance</span></div>"
            "</td></tr>"
        ) % (GRID,
             esc(c["ticker"]), MUTED, esc(c["display"]),
             INK2, esc(c["type"]), tag,
             esc(c["asset"]), INK2, esc(c["indication"]),
             INK2, esc(c["description"]),
             MUTED, esc(holders) or "—", impc, esc(c["importance"]))

    soon_rows = "".join(cat_block(c) for c in soon) or \
        "<tr><td style='padding:10px 0;color:%s'>No dated catalysts in the next ~100 days.</td></tr>" % MUTED
    recent_rows = "".join(cat_block(c, show_countdown=False) for c in recent) or \
        "<tr><td style='padding:10px 0;color:%s'>No readouts reported in the last ~35 days.</td></tr>" % MUTED
    recurring_rows = "".join(cat_block(c, show_countdown=False) for c in recurring)

    price_asof = prices.get("as_of") or "pending first refresh"

    html_out = TEMPLATE
    subs = {
        "month": month,
        "n_positions": str(len(ticker_name)),
        "n_soon": str(len(soon)),
        "n_recent": str(len(recent)),
        "price_asof": esc(price_asof),
        "holdings_asof": esc(holdings.get("as_of", "")),
        "perf_rows": perf_table(),
        "soon_rows": soon_rows,
        "recent_rows": recent_rows,
        "recurring_rows": recurring_rows,
    }
    for k, v in subs.items():
        html_out = html_out.replace("@@%s@@" % k, v)

    os.makedirs(OUTPUT, exist_ok=True)
    hpath = os.path.join(OUTPUT, "monthly_email.html")
    with open(hpath, "w") as f:
        f.write(html_out)

    # plaintext fallback
    lines = ["CLINICAL CATALYST MONTHLY BRIEF — %s" % month, "=" * 48, ""]
    lines.append("UPCOMING CATALYSTS (next ~100 days):")
    for c in soon:
        d = days_until(c["sort_date"])
        lines.append("  [%s] %s — %s (%s) %s%s" % (
            c["display"], c["ticker"], c["asset"], c["indication"], c["type"],
            (" T-%dd" % d) if d is not None and d >= 0 else ""))
    lines.append("")
    lines.append("RECENT READOUTS (last ~35 days):")
    for c in recent:
        lines.append("  [%s] %s — %s (%s)" % (c["display"], c["ticker"], c["asset"], c["indication"]))
    lines.append("")
    lines.append("Prices as of %s | Holdings as of %s" % (price_asof, holdings.get("as_of", "")))
    lines.append("Not investment advice. Verify catalyst dates against primary sources.")
    tpath = os.path.join(OUTPUT, "monthly_email.txt")
    with open(tpath, "w") as f:
        f.write("\n".join(lines))

    print("Wrote", hpath, "and", tpath)
    return hpath


TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f4f4f1;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0b0b0b">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f1;padding:24px 12px">
<tr><td align="center">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background:#ffffff;border:1px solid #e6e5df;border-radius:14px;overflow:hidden">

  <tr><td style="background:#0b0b0b;color:#ffffff;padding:22px 26px">
    <div style="font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#c3c2b7">Clinical Catalyst Monthly Brief</div>
    <div style="font-size:24px;font-weight:700;margin-top:4px">@@month@@</div>
    <div style="font-size:13px;color:#c3c2b7;margin-top:4px">RTW Investments · Avoro Capital · Frazier Life Sciences</div>
  </td></tr>

  <tr><td style="padding:18px 26px 4px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="text-align:center;padding:8px"><div style="font-size:26px;font-weight:700">@@n_positions@@</div><div style="font-size:11px;color:#52514e">positions</div></td>
      <td style="text-align:center;padding:8px;border-left:1px solid #e6e5df"><div style="font-size:26px;font-weight:700">@@n_soon@@</div><div style="font-size:11px;color:#52514e">catalysts &lt;100d</div></td>
      <td style="text-align:center;padding:8px;border-left:1px solid #e6e5df"><div style="font-size:26px;font-weight:700">@@n_recent@@</div><div style="font-size:11px;color:#52514e">recent readouts</div></td>
    </tr></table>
  </td></tr>

  <tr><td style="padding:20px 26px 6px">
    <div style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#52514e;border-bottom:2px solid #0b0b0b;padding-bottom:6px">Performance snapshot</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px;font-size:13px">
      <tr style="color:#898781;font-size:11px;text-transform:uppercase;letter-spacing:0.04em">
        <td style="padding:4px 8px">Ticker</td><td style="padding:4px 8px">Company</td>
        <td style="padding:4px 8px;text-align:right">Last</td><td style="padding:4px 8px;text-align:right">1M</td>
        <td style="padding:4px 8px;text-align:right">YTD</td><td style="padding:4px 8px">Funds</td></tr>
      @@perf_rows@@
    </table>
  </td></tr>

  <tr><td style="padding:20px 26px 6px">
    <div style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#52514e;border-bottom:2px solid #0b0b0b;padding-bottom:6px">Upcoming catalysts &mdash; next ~100 days</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">@@soon_rows@@</table>
  </td></tr>

  <tr><td style="padding:20px 26px 6px">
    <div style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#52514e;border-bottom:2px solid #0b0b0b;padding-bottom:6px">Recent readouts &amp; news</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">@@recent_rows@@</table>
  </td></tr>

  <tr><td style="padding:20px 26px 6px">
    <div style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:#52514e;border-bottom:2px solid #0b0b0b;padding-bottom:6px">Commercial trajectories to check</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">@@recurring_rows@@</table>
  </td></tr>

  <tr><td style="padding:18px 26px 26px;color:#898781;font-size:11px;border-top:1px solid #e6e5df">
    Prices as of @@price_asof@@ · Holdings (13F) as of @@holdings_asof@@.<br>
    <b>Not investment advice.</b> Catalyst dates are estimates from company IR and public reporting and can shift; verify against primary sources.
  </td></tr>

</table>
</td></tr></table>
</body></html>"""


if __name__ == "__main__":
    build()
