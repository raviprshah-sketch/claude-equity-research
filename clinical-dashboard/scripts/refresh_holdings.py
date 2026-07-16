"""Refresh top 13F holdings for each tracked fund from SEC EDGAR.

For each fund CIK: find the latest 13F-HR, download its information table XML,
aggregate market value by issuer, attach tickers via companies.json name aliases,
rank, compute percent of portfolio, and write the top N back into holdings.json.

Requires unrestricted outbound HTTPS to sec.gov / data.sec.gov (works in GitHub
Actions). Set DASHBOARD_UA to a descriptive contact string (SEC requirement).
"""
import re
import xml.etree.ElementTree as ET

from lib import http_get, load_json, save_json, today

TOP_N = 12


def latest_13f(cik):
    cik10 = cik.zfill(10)
    subs = load_json_url("https://data.sec.gov/submissions/CIK%s.json" % cik10)
    recent = subs["filings"]["recent"]
    for form, acc, doc, pdate in zip(
        recent["form"], recent["accessionNumber"], recent["primaryDocument"], recent["filingDate"]
    ):
        if form == "13F-HR":
            return acc.replace("-", ""), pdate
    return None, None


def load_json_url(url):
    import json
    return json.loads(http_get(url).decode("utf-8"))


def info_table_url(cik, accession):
    base = "https://www.sec.gov/Archives/edgar/data/%s/%s/" % (cik.lstrip("0"), accession)
    idx = http_get(base).decode("utf-8", "replace")
    # find the information table xml (not the primary_doc.xml)
    candidates = re.findall(r'href="([^"]+\.xml)"', idx)
    for c in candidates:
        low = c.lower()
        if "primary_doc" in low:
            continue
        return base + c.split("/")[-1]
    # fallback: any xml
    for c in candidates:
        return base + c.split("/")[-1]
    return None


def parse_info_table(xml_bytes):
    """Return list of (issuer_name, cusip, value) with value in USD.
    Post-2022 13F values are in dollars; older filings in thousands. We detect
    by magnitude at the end and normalize to dollars.
    """
    text = xml_bytes.decode("utf-8", "replace")
    # strip namespaces for easy parsing
    text = re.sub(r'xmlns(:\w+)?="[^"]+"', "", text)
    text = re.sub(r"<(/?)\w+:", r"<\1", text)
    root = ET.fromstring(text)
    rows = []
    for it in root.iter("infoTable"):
        name = (it.findtext("nameOfIssuer") or "").strip()
        cusip = (it.findtext("cusip") or "").strip()
        val = it.findtext("value")
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        rows.append([name, cusip, val])
    return rows


def normalize_values(rows):
    total = sum(r[2] for r in rows)
    # Heuristic: modern filings report dollars; if the total looks like thousands
    # (e.g. a $10B book showing as ~10,000,000), scale up.
    if total and total < 5e8 and len(rows) > 5:
        for r in rows:
            r[2] *= 1000.0
    return rows


def attach_tickers(rows, companies):
    alias_map = []
    for tk, meta in companies.items():
        for a in meta.get("name_aliases", []):
            alias_map.append((a.upper(), tk))
    out = []
    for name, cusip, val in rows:
        up = name.upper()
        ticker = None
        for alias, tk in alias_map:
            if alias in up:
                ticker = tk
                break
        out.append({"name": name, "cusip": cusip, "value": val, "ticker": ticker})
    return out


def main():
    funds = load_json("funds.json")
    holdings = load_json("holdings.json")
    companies = load_json("companies.json")["companies"]

    for fund in funds["funds"]:
        cik = fund.get("cik")
        if not cik:
            continue
        try:
            acc, pdate = latest_13f(cik)
            if not acc:
                print("%s: no 13F-HR found" % fund["id"])
                continue
            url = info_table_url(cik, acc)
            rows = normalize_values(parse_info_table(http_get(url)))
        except Exception as e:  # noqa
            print("%s: refresh failed (%s) - keeping seed data" % (fund["id"], e))
            continue

        # aggregate by ticker (a fund may hold multiple share classes / calls)
        enriched = attach_tickers(rows, companies)
        total = sum(r["value"] for r in enriched) or 1.0
        agg = {}
        for r in enriched:
            key = r["ticker"] or ("~" + r["name"][:24])
            a = agg.setdefault(key, {"value": 0.0, "name": r["name"], "ticker": r["ticker"]})
            a["value"] += r["value"]
        ranked = sorted(agg.values(), key=lambda a: -a["value"])[:TOP_N]

        new_list = []
        for i, a in enumerate(ranked, 1):
            new_list.append({
                "ticker": a["ticker"] or "N/A",
                "name": companies.get(a["ticker"], {}).get("name", a["name"].title()) if a["ticker"] else a["name"].title(),
                "rank": i,
                "pct": round(100.0 * a["value"] / total, 2),
                "pct_estimated": False,
                "value_usd": round(a["value"]),
            })
        holdings["holdings"][fund["id"]] = new_list
        fund["portfolio_value_usd"] = round(total)
        fund["filing_date"] = pdate
        print("%s: refreshed %d holdings (portfolio $%.1fB, filed %s)" % (
            fund["id"], len(new_list), total / 1e9, pdate))

    holdings["as_of"] = today()
    holdings["source"] = "SEC EDGAR 13F-HR (auto-refreshed)"
    save_json("holdings.json", holdings)
    save_json("funds.json", funds)


if __name__ == "__main__":
    main()
