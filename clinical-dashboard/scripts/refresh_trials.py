"""Enrich catalysts with live trial status from ClinicalTrials.gov API v2.

For each distinct sponsor in companies.json, pull recent interventional studies
and write data/trials.json: a per-ticker list of {nct, title, phase, status,
primary_completion, last_update}. The dashboard cross-references named trials to
show live phase/status next to each catalyst, and surfaces primary completion
dates that fall inside the tracking window.

Requires outbound HTTPS to clinicaltrials.gov (works in GitHub Actions).
"""
import json
import urllib.parse

from lib import http_get, load_json, save_json, today

API = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = [
    "NCTId", "BriefTitle", "Phase", "OverallStatus",
    "PrimaryCompletionDate", "LastUpdatePostDate", "LeadSponsorName",
]


def fetch_sponsor(sponsor):
    params = {
        "query.spons": sponsor,
        "filter.overallStatus": "RECRUITING|ACTIVE_NOT_RECRUITING|ENROLLING_BY_INVITATION|NOT_YET_RECRUITING|COMPLETED",
        "fields": ",".join(FIELDS),
        "pageSize": "50",
        "sort": "LastUpdatePostDate:desc",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    try:
        data = json.loads(http_get(url).decode("utf-8"))
    except Exception as e:  # noqa
        print("  ! %s failed: %s" % (sponsor, e))
        return []
    out = []
    for s in data.get("studies", []):
        p = s.get("protocolSection", {})
        ident = p.get("identificationModule", {})
        status = p.get("statusModule", {})
        design = p.get("designModule", {})
        out.append({
            "nct": ident.get("nctId"),
            "title": ident.get("briefTitle"),
            "phase": ",".join(design.get("phases", []) or []),
            "status": status.get("overallStatusModule", status.get("overallStatus"))
            if isinstance(status.get("overallStatus"), str) else status.get("overallStatus"),
            "primary_completion": (status.get("primaryCompletionDateStruct", {}) or {}).get("date"),
            "last_update": (status.get("lastUpdatePostDateStruct", {}) or {}).get("date"),
        })
    return out


def main():
    companies = load_json("companies.json")["companies"]
    out = {"as_of": today(), "trials": {}}
    for ticker, meta in companies.items():
        sponsor = meta.get("sponsor")
        if not sponsor:
            continue
        studies = fetch_sponsor(sponsor)
        out["trials"][ticker] = studies
        print("  %s (%s): %d studies" % (ticker, sponsor, len(studies)))
    save_json("trials.json", out)
    print("Wrote trials for %d tickers" % len(out["trials"]))


if __name__ == "__main__":
    main()
