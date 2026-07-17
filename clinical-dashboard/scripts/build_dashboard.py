"""Generate a self-contained HTML dashboard from the data files.

Sections:
  - Meaningful readout watch (near-term high-importance binaries)
  - Catalyst calendar (upcoming, bucketed by time-to-event) + recent readouts
  - Positions by fund (weights + which have upcoming catalysts)
  - Cross-fund conviction (names held by >1 manager)
  - Performance table (from prices.json when present)

Writes output/dashboard.html. No external assets, theme-aware (light/dark).
"""
import html
import json
from datetime import date

from lib import load_json, days_until, parse_iso, OUTPUT
import os

IMPORTANCE = {
    "high":   {"label": "High",   "color": "var(--critical)"},
    "medium": {"label": "Medium", "color": "var(--warning)"},
    "low":    {"label": "Low",    "color": "var(--muted)"},
}

TYPE_ICON = {
    "PDUFA": "⚖",              # scales - regulatory decision
    "Phase 3 readout": "◉",
    "Phase 3 readout (outcomes)": "◉",
    "Phase 3 (partner-led)": "◉",
    "Phase 3 readout (CVOT)": "◉",
    "Phase 2 readout": "○",
    "Phase 1 readout": "○",
    "Regulatory (NDA filing)": "⚖",
    "Regulatory (NDA review)": "⚖",
    "Regulatory (EMA decision)": "⚖",
    "Regulatory (sNDA/PDUFA)": "⚖",
    "Trial start": "▶",
    "Trial start / progression": "▶",
    "Enrollment milestone": "▶",
    "Commercial update": "■",
    "Commercial / launch": "■",
    "Phase 3 / partnering": "◉",
    "Registrational readout": "◉",
}


def esc(s):
    return html.escape(str(s if s is not None else ""))


def fund_map(funds):
    return {f["id"]: f for f in funds["funds"]}


def holders_of(ticker, holdings):
    out = []
    for fid, lst in holdings["holdings"].items():
        for h in lst:
            if h["ticker"] == ticker:
                out.append((fid, h))
    return out


def fmt_pct(x):
    if x is None:
        return "—"
    return ("+%.1f%%" % (x * 100)) if x >= 0 else ("%.1f%%" % (x * 100))


def perf_class(x):
    if x is None:
        return "flat"
    return "pos" if x >= 0 else "neg"


def bucket(dleft):
    if dleft is None:
        return 4
    if dleft <= 30:
        return 0
    if dleft <= 90:
        return 1
    if dleft <= 180:
        return 2
    return 3


BUCKET_LABEL = ["Next 30 days", "31–90 days", "91–180 days", "6–12 months", "Beyond 12 months"]


def catalyst_row(c, holdings, funds_by_id, prices):
    dleft = days_until(c["sort_date"])
    imp = IMPORTANCE.get(c["importance"], IMPORTANCE["low"])
    holders = holders_of(c["ticker"], holdings)
    chips = "".join(
        '<span class="fundchip" title="%s">%s</span>' % (
            esc(funds_by_id.get(fid, {}).get("name", fid)), esc(fid.upper()))
        for fid, _ in holders
    )
    icon = TYPE_ICON.get(c["type"], "○")
    countdown = ""
    if dleft is not None and c.get("status") != "reported":
        if dleft < 0:
            countdown = '<span class="cd overdue">past due</span>'
        else:
            countdown = '<span class="cd">T−%d d</span>' % dleft
    px = prices.get("prices", {}).get(c["ticker"], {}) if prices else {}
    last = px.get("last")
    pxbadge = ('<span class="px">$%.2f <em class="%s">%s</em></span>' % (
        last, perf_class(px.get("ret_1m")), fmt_pct(px.get("ret_1m")))) if last else ""
    fund_ids = " ".join(sorted(fid for fid, _ in holders))
    return """
    <tr class="catrow filterable imp-%s" data-funds="%s">
      <td class="c-when"><div class="when-main">%s</div>%s</td>
      <td class="c-tk"><span class="tk">%s</span>%s</td>
      <td class="c-what"><span class="ico">%s</span><span class="ctype">%s</span>
          <div class="asset">%s <span class="ind">%s</span></div>
          <div class="desc">%s</div></td>
      <td class="c-imp"><span class="badge" style="--bc:%s">%s</span></td>
      <td class="c-funds">%s</td>
    </tr>""" % (
        esc(c["importance"]), esc(fund_ids),
        esc(c["display"]), countdown,
        esc(c["ticker"]), pxbadge,
        icon, esc(c["type"]), esc(c["asset"]), esc(c["indication"]),
        esc(c["description"]),
        imp["color"], imp["label"],
        chips,
    )


def build():
    funds = load_json("funds.json")
    holdings = load_json("holdings.json")
    catalysts = load_json("catalysts.json")
    try:
        prices = load_json("prices.json")
    except Exception:
        prices = {"prices": {}}
    try:
        trials = load_json("trials.json")
    except Exception:
        trials = {"trials": {}}

    fb = fund_map(funds)
    cats = catalysts["catalysts"]
    upcoming = sorted([c for c in cats if (days_until(c["sort_date"]) or -999) >= 0 and c.get("status") == "upcoming"],
                      key=lambda c: c["sort_date"])
    recent = sorted([c for c in cats if c.get("status") == "reported"],
                    key=lambda c: c["sort_date"], reverse=True)
    recurring = [c for c in cats if c.get("status") == "recurring"]

    # meaningful readout watch = high importance, upcoming, within ~9 months, binary-ish
    watch = [c for c in upcoming if c["importance"] == "high"][:8]

    # ---- Watch cards ----
    watch_cards = ""
    for c in watch:
        dleft = days_until(c["sort_date"])
        holders = holders_of(c["ticker"], holdings)
        chips = " ".join(esc(fid.upper()) for fid, _ in holders)
        fund_ids = " ".join(sorted(fid for fid, _ in holders))
        watch_cards += """
        <div class="wcard filterable" data-funds="%s">
          <div class="wtop"><span class="tk">%s</span><span class="wcd">%s</span></div>
          <div class="wasset">%s</div>
          <div class="wind">%s</div>
          <div class="wmeta"><span class="wtype">%s</span> · <span class="wwhen">%s</span></div>
          <div class="wfunds">%s</div>
        </div>""" % (
            esc(fund_ids),
            esc(c["ticker"]),
            ("T−%d d" % dleft) if dleft is not None else esc(c["display"]),
            esc(c["asset"]), esc(c["indication"]), esc(c["type"]), esc(c["display"]),
            chips,
        )

    # ---- Calendar buckets ----
    buckets = {0: [], 1: [], 2: [], 3: [], 4: []}
    for c in upcoming:
        buckets[bucket(days_until(c["sort_date"]))].append(c)
    calendar = ""
    for b in range(5):
        if not buckets[b]:
            continue
        rows = "".join(catalyst_row(c, holdings, fb, prices) for c in buckets[b])
        calendar += """
        <div class="bucket"><h3 class="bhead">%s <span class="bcount">%d</span></h3>
        <table class="cattable"><tbody>%s</tbody></table></div>""" % (
            BUCKET_LABEL[b], len(buckets[b]), rows)

    recent_rows = "".join(catalyst_row(c, holdings, fb, prices) for c in recent)
    recurring_rows = "".join(catalyst_row(c, holdings, fb, prices) for c in recurring)

    # ---- Positions by fund ----
    upcoming_by_ticker = {}
    for c in upcoming:
        upcoming_by_ticker.setdefault(c["ticker"], []).append(c)
    fund_sections = ""
    for f in funds["funds"]:
        rows = ""
        for h in holdings["holdings"].get(f["id"], []):
            nxt = upcoming_by_ticker.get(h["ticker"], [])
            nxt_sorted = sorted(nxt, key=lambda c: c["sort_date"])
            next_cat = nxt_sorted[0] if nxt_sorted else None
            px = prices.get("prices", {}).get(h["ticker"], {})
            pct = h.get("pct")
            est = " *" if h.get("pct_estimated") else ""
            barw = min(100, (pct or 0) * 5)
            next_html = ("<span class='nc'>%s <em>%s</em></span>" % (
                esc(next_cat["display"]), esc(next_cat["type"]))) if next_cat else "<span class='none'>—</span>"
            rows += """
            <tr>
              <td class="p-tk">%s</td>
              <td class="p-nm">%s</td>
              <td class="p-wt"><div class="wtwrap"><span class="wtbar" style="width:%.0f%%"></span><span class="wtn">%.1f%%%s</span></div></td>
              <td class="p-px">%s</td>
              <td class="p-ytd %s">%s</td>
              <td class="p-next">%s</td>
            </tr>""" % (
                esc(h["ticker"]), esc(h["name"]), barw, (pct or 0), est,
                ("$%.2f" % px["last"]) if px.get("last") else "—",
                perf_class(px.get("ret_ytd")), fmt_pct(px.get("ret_ytd")),
                next_html,
            )
        pv = f.get("portfolio_value_usd")
        pv_str = ("$%.1fB" % (pv / 1e9)) if pv else "—"
        fund_sections += """
        <div class="fund fundblock" data-fund="%s">
          <div class="fhead"><h3>%s</h3><span class="fmeta">%s · %s positions · %s book · %s</span></div>
          <table class="ptable">
            <thead><tr><th>Ticker</th><th>Company</th><th>Weight</th><th>Last</th><th>YTD</th><th>Next catalyst</th></tr></thead>
            <tbody>%s</tbody>
          </table>
        </div>""" % (
            esc(f["id"]), esc(f["name"]), esc(f.get("manager", "")), esc(f.get("positions_count") or "—"),
            pv_str, esc(f.get("filing_quarter", "")), rows)

    # ---- Conviction overlap ----
    ticker_funds = {}
    ticker_name = {}
    for fid, lst in holdings["holdings"].items():
        for h in lst:
            ticker_funds.setdefault(h["ticker"], set()).add(fid)
            ticker_name[h["ticker"]] = h["name"]
    overlap = sorted([(t, fs) for t, fs in ticker_funds.items() if len(fs) > 1],
                     key=lambda x: -len(x[1]))
    overlap_rows = ""
    for t, fs in overlap:
        px = prices.get("prices", {}).get(t, {})
        nxt = sorted(upcoming_by_ticker.get(t, []), key=lambda c: c["sort_date"])
        next_html = ("%s — %s" % (esc(nxt[0]["display"]), esc(nxt[0]["asset"]))) if nxt else "—"
        chips = " ".join('<span class="fundchip">%s</span>' % esc(x.upper()) for x in sorted(fs))
        overlap_rows += """
        <tr class="filterable" data-funds="%s"><td class="o-tk">%s</td><td>%s</td><td class="o-n">%d</td><td>%s</td>
            <td class="%s">%s</td><td class="o-next">%s</td></tr>""" % (
            esc(" ".join(sorted(fs))),
            esc(t), esc(ticker_name[t]), len(fs), chips,
            perf_class(px.get("ret_ytd")), fmt_pct(px.get("ret_ytd")), next_html)

    # ---- Performance table ----
    perf_rows = ""
    all_tickers = sorted(ticker_name.keys())
    for t in all_tickers:
        px = prices.get("prices", {}).get(t, {})
        if not px.get("last"):
            continue
        def cell(k):
            return "<td class='%s'>%s</td>" % (perf_class(px.get(k)), fmt_pct(px.get(k)))
        perf_rows += "<tr class='filterable' data-funds='%s'><td class='pf-tk'>%s</td><td>%s</td><td class='pf-last'>$%.2f</td>%s%s%s%s</tr>" % (
            esc(" ".join(sorted(ticker_funds.get(t, [])))),
            esc(t), esc(ticker_name[t]), px["last"],
            cell("ret_1m"), cell("ret_3m"), cell("ret_ytd"), cell("ret_12m"))
    perf_note = "" if perf_rows else "<p class='empty'>Price data populates after the first data-refresh run (scripts/refresh_prices.py).</p>"

    price_asof = prices.get("as_of", "not yet run")

    # per-manager counts for the live filter (positions, upcoming catalysts, watch)
    def held_by(fid):
        return {h["ticker"] for h in holdings["holdings"].get(fid, [])}
    counts = {"all": {
        "pos": sum(len(v) for v in holdings["holdings"].values()),
        "upc": len(upcoming), "watch": len(watch),
        "name": "All managers"}}
    for f in funds["funds"]:
        tk = held_by(f["id"])
        counts[f["id"]] = {
            "pos": len(holdings["holdings"].get(f["id"], [])),
            "upc": sum(1 for c in upcoming if c["ticker"] in tk),
            "watch": sum(1 for c in watch if c["ticker"] in tk),
            "name": f["name"],
        }
    # filter bar buttons
    filter_btns = ('<button type="button" class="fbtn active" data-fund="all" '
                   'aria-pressed="true">All managers</button>')
    for f in funds["funds"]:
        filter_btns += ('<button type="button" class="fbtn" data-fund="%s" aria-pressed="false">'
                        '%s</button>') % (esc(f["id"]), esc(f["name"].split(",")[0].split(" LLC")[0]))

    subs = {
        "generated": catalysts.get("generated", str(date.today())),
        "holdings_asof": holdings.get("as_of", ""),
        "price_asof": esc(price_asof),
        "trials_asof": esc(trials.get("as_of", "not yet run")),
        "n_upcoming": str(len(upcoming)),
        "n_watch": str(len(watch)),
        "n_positions": str(sum(len(v) for v in holdings["holdings"].values())),
        "filter_btns": filter_btns,
        "counts_json": json.dumps(counts),
        "watch_cards": watch_cards,
        "calendar": calendar,
        "recent_rows": recent_rows,
        "recurring_rows": recurring_rows,
        "fund_sections": fund_sections,
        "overlap_rows": overlap_rows,
        "perf_rows": perf_rows,
        "perf_note": perf_note,
    }
    html_out = PAGE
    for k, v in subs.items():
        html_out = html_out.replace("@@%s@@" % k, str(v))
    os.makedirs(OUTPUT, exist_ok=True)
    path = os.path.join(OUTPUT, "dashboard.html")
    with open(path, "w") as f:
        f.write(html_out)
    print("Wrote", path)
    return path


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clinical Catalyst Dashboard</title>
<style>
:root{
  color-scheme: light dark;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10);
  --blue:#2a78d6; --violet:#4a3aa7;
  --good:#006300; --neg:#d03b3b; --warning:#c98500; --critical:#d03b3b; --serious:#eb6834;
  --wt:#2a78d6;
}
@media (prefers-color-scheme: dark){:root:where(:not([data-theme="light"])){
  --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
  --blue:#3987e5; --violet:#9085e9; --good:#0ca30c; --neg:#e66767; --warning:#eda100;
  --critical:#e34948; --serious:#eb6834; --wt:#3987e5;
}}
:root[data-theme="dark"]{
  --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
  --blue:#3987e5; --violet:#9085e9; --good:#0ca30c; --neg:#e66767; --warning:#eda100;
  --critical:#e34948; --serious:#eb6834; --wt:#3987e5;
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.45;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 80px}
header.top{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-end;gap:16px;
  border-bottom:2px solid var(--ink);padding-bottom:16px;margin-bottom:8px}
h1{font-size:26px;margin:0;letter-spacing:-0.02em}
.sub{color:var(--ink2);font-size:13px;margin-top:4px}
.asof{font-size:12px;color:var(--muted);text-align:right}
.asof b{color:var(--ink2)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0 30px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.kpi .n{font-size:30px;font-weight:650;letter-spacing:-0.02em}
.kpi .l{font-size:12px;color:var(--ink2);margin-top:2px}
h2{font-size:15px;text-transform:uppercase;letter-spacing:0.06em;color:var(--ink2);
  margin:38px 0 14px;padding-bottom:6px;border-bottom:1px solid var(--grid)}
h2 .hint{text-transform:none;letter-spacing:0;font-weight:400;color:var(--muted);font-size:12px;margin-left:8px}
.watch{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:12px}
.wcard{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--critical);
  border-radius:10px;padding:13px 14px}
.wtop{display:flex;justify-content:space-between;align-items:baseline}
.wtop .tk{font-weight:700;font-size:16px}
.wcd{font-size:12px;font-weight:600;color:var(--critical);font-variant-numeric:tabular-nums}
.wasset{font-size:13px;font-weight:600;margin-top:6px}
.wind{font-size:12px;color:var(--ink2)}
.wmeta{font-size:11px;color:var(--muted);margin-top:6px}
.wfunds{font-size:11px;color:var(--blue);font-weight:600;margin-top:5px;letter-spacing:0.03em}
.bucket{margin-bottom:20px}
.bhead{font-size:13px;font-weight:650;margin:0 0 6px;color:var(--ink)}
.bcount{display:inline-block;background:var(--grid);color:var(--ink2);border-radius:10px;
  font-size:11px;padding:0 7px;margin-left:6px;vertical-align:middle}
table{width:100%;border-collapse:collapse}
.cattable td{border-top:1px solid var(--grid);padding:10px 8px;vertical-align:top;font-size:13px}
.catrow .c-when{width:98px;color:var(--ink2)}
.when-main{font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums}
.cd{display:inline-block;font-size:11px;color:var(--serious);font-weight:600;margin-top:3px}
.cd.overdue{color:var(--critical)}
.c-tk{width:96px}
.c-tk .tk{font-weight:700}
.px{display:block;font-size:11px;color:var(--muted);margin-top:2px;font-variant-numeric:tabular-nums}
.px em{font-style:normal}
.ico{color:var(--muted);margin-right:6px}
.ctype{font-size:11px;text-transform:uppercase;letter-spacing:0.04em;color:var(--ink2);font-weight:600}
.asset{font-weight:600;margin-top:3px}
.asset .ind{font-weight:400;color:var(--ink2)}
.desc{color:var(--ink2);font-size:12px;margin-top:3px;max-width:52ch}
.c-imp{width:78px}
.badge{display:inline-block;font-size:11px;font-weight:600;color:var(--bc);
  border:1px solid var(--bc);border-radius:20px;padding:1px 9px}
.c-funds{width:110px}
.fundchip{display:inline-block;background:var(--blue);color:#fff;border-radius:5px;
  font-size:10px;font-weight:700;padding:2px 6px;margin:0 3px 3px 0;letter-spacing:0.03em}
.pos{color:var(--good);font-weight:600;font-variant-numeric:tabular-nums}
.neg{color:var(--neg);font-weight:600;font-variant-numeric:tabular-nums}
.flat{color:var(--muted);font-variant-numeric:tabular-nums}
.fund{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin-bottom:18px}
.fhead{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:8px}
.fhead h3{margin:0;font-size:16px}
.fmeta{font-size:12px;color:var(--muted)}
.ptable th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;
  color:var(--muted);font-weight:600;padding:6px 8px;border-bottom:1px solid var(--grid)}
.ptable td{padding:8px;border-top:1px solid var(--grid);font-size:13px}
.p-tk{font-weight:700;width:64px}
.p-wt{width:150px}
.wtwrap{position:relative;display:flex;align-items:center;gap:8px}
.wtbar{height:8px;background:var(--wt);border-radius:4px;min-width:2px;display:inline-block}
.wtn{font-size:12px;color:var(--ink2);font-variant-numeric:tabular-nums}
.p-next .nc{font-weight:600;font-variant-numeric:tabular-nums}
.p-next .nc em{font-style:normal;font-weight:400;color:var(--ink2);font-size:11px;display:block}
.p-next .none{color:var(--muted)}
.otable td{padding:9px 8px;border-top:1px solid var(--grid);font-size:13px}
.otable th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:0.04em;color:var(--muted);
  font-weight:600;padding:6px 8px;border-bottom:1px solid var(--grid)}
.o-tk{font-weight:700}
.o-n{text-align:center;font-weight:700;color:var(--violet)}
.pf-tk{font-weight:700}
.pf-last{font-variant-numeric:tabular-nums}
.empty{color:var(--muted);font-size:13px;font-style:italic}
.legend{font-size:12px;color:var(--muted);margin-top:8px}
.legend b{color:var(--ink2)}
footer{margin-top:44px;padding-top:16px;border-top:1px solid var(--grid);font-size:11px;color:var(--muted)}
footer p{margin:5px 0}
.filterbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:20px 0 4px}
.flabel{font-size:11px;text-transform:uppercase;letter-spacing:0.06em;color:var(--muted);margin-right:4px}
.fbtn{font-family:inherit;font-size:13px;font-weight:600;color:var(--ink2);background:var(--surface);
  border:1px solid var(--border);border-radius:20px;padding:6px 15px;cursor:pointer;transition:all .12s}
.fbtn:hover{border-color:var(--blue);color:var(--ink)}
.fbtn.active{background:var(--ink);color:var(--page);border-color:var(--ink)}
.kctx{color:var(--blue);font-weight:600}
.emptymsg{color:var(--muted);font-size:13px;font-style:italic;margin:4px 0 0}
@media(max-width:720px){.kpis{grid-template-columns:repeat(2,1fr)}
  .c-imp,.px{display:none}.desc{max-width:none}}
</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div>
    <h1>Clinical Catalyst &amp; Position Dashboard</h1>
    <div class="sub">Meaningful biotech positions across RTW Investments, Avoro Capital &amp; Frazier Life Sciences</div>
  </div>
  <div class="asof">
    Catalysts curated <b>@@generated@@</b><br>
    Holdings (13F) <b>@@holdings_asof@@</b> · Prices <b>@@price_asof@@</b><br>
    Trials <b>@@trials_asof@@</b>
  </div>
</header>

<div class="filterbar" id="mgrfilter" role="group" aria-label="Filter by manager">
  <span class="flabel">Filter by manager</span>
  @@filter_btns@@
</div>

<div class="kpis">
  <div class="kpi"><div class="n" id="kpi-pos">@@n_positions@@</div><div class="l">Tracked positions <span class="kctx" id="kctx-pos"></span></div></div>
  <div class="kpi"><div class="n" id="kpi-upc">@@n_upcoming@@</div><div class="l">Upcoming catalysts</div></div>
  <div class="kpi"><div class="n" id="kpi-watch">@@n_watch@@</div><div class="l">High-impact readouts on watch</div></div>
  <div class="kpi"><div class="n" id="kpi-mgr">3</div><div class="l">Managers shown</div></div>
</div>

<h2>Meaningful Readout Watch <span class="hint">near-term, stock-moving events</span></h2>
<p class="emptymsg" id="empty-watch" hidden>No high-impact readouts on watch for this manager.</p>
<div class="watch">@@watch_cards@@</div>

<h2>Catalyst Calendar <span class="hint">upcoming, by time to event</span></h2>
@@calendar@@

<h2>Positions by Manager <span class="hint">weights from latest 13F; * = estimated weight</span></h2>
@@fund_sections@@

<h2>Cross-Fund Conviction <span class="hint">names held by more than one manager</span></h2>
<table class="otable">
  <thead><tr><th>Ticker</th><th>Company</th><th>Funds</th><th>Held by</th><th>YTD</th><th>Next catalyst</th></tr></thead>
  <tbody>@@overlap_rows@@</tbody>
</table>

<h2>Performance <span class="hint">total return; source Stooq EOD</span></h2>
@@perf_note@@
<table class="otable">
  <thead><tr><th>Ticker</th><th>Company</th><th>Last</th><th>1M</th><th>3M</th><th>YTD</th><th>12M</th></tr></thead>
  <tbody>@@perf_rows@@</tbody>
</table>

<h2>Recent Readouts <span class="hint">reported catalysts to review</span></h2>
<table class="cattable"><tbody>@@recent_rows@@</tbody></table>

<h2>Recurring Watch-items <span class="hint">quarterly commercial trajectories</span></h2>
<table class="cattable"><tbody>@@recurring_rows@@</tbody></table>

<footer>
  <p><b>Not investment advice.</b> Educational tool. Catalyst dates are estimates compiled from company IR
  communications and public reporting and can shift; verify against primary sources before acting.</p>
  <p>Data: SEC EDGAR 13F-HR (holdings) · ClinicalTrials.gov (trial status) · Stooq (prices).
  Regenerate with <code>python scripts/build_dashboard.py</code>.</p>
</footer>
</div>

<script>
(function(){
  var COUNTS = @@counts_json@@;
  var bar = document.getElementById('mgrfilter');
  if(!bar) return;
  var btns = Array.prototype.slice.call(bar.querySelectorAll('.fbtn'));

  function apply(fund){
    // row/card level filter
    document.querySelectorAll('.filterable').forEach(function(el){
      var f = el.getAttribute('data-funds') || '';
      var show = (fund === 'all') || f.split(' ').indexOf(fund) !== -1;
      el.hidden = !show;
    });
    // whole manager blocks (Positions by Manager)
    document.querySelectorAll('.fundblock').forEach(function(el){
      el.hidden = !(fund === 'all' || el.getAttribute('data-fund') === fund);
    });
    // collapse empty calendar buckets
    document.querySelectorAll('.bucket').forEach(function(b){
      var any = Array.prototype.slice.call(b.querySelectorAll('tr.filterable'))
                 .some(function(r){ return !r.hidden; });
      b.hidden = !any;
    });
    // empty-state message for the watch grid
    var watchAny = Array.prototype.slice.call(document.querySelectorAll('.wcard'))
                    .some(function(c){ return !c.hidden; });
    var em = document.getElementById('empty-watch');
    if(em) em.hidden = watchAny;

    // KPIs
    var c = COUNTS[fund] || COUNTS.all;
    setText('kpi-pos', c.pos);
    setText('kpi-upc', c.upc);
    setText('kpi-watch', c.watch);
    setText('kpi-mgr', fund === 'all' ? Object.keys(COUNTS).length - 1 : 1);
    setText('kctx-pos', fund === 'all' ? '' : '· ' + c.name.split(',')[0]);

    btns.forEach(function(b){
      var on = b.getAttribute('data-fund') === fund;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    try { history.replaceState(null, '', fund === 'all' ? location.pathname : '#' + fund); } catch(e){}
  }
  function setText(id, v){ var e = document.getElementById(id); if(e) e.textContent = v; }

  btns.forEach(function(b){
    b.addEventListener('click', function(){ apply(b.getAttribute('data-fund')); });
  });

  // honor a deep link like #rtw on load
  var initial = (location.hash || '').replace('#','');
  apply(COUNTS[initial] ? initial : 'all');
})();
</script>
</body>
</html>"""


if __name__ == "__main__":
    build()
