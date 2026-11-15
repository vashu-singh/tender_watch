#!/usr/bin/env python3
"""Checks every source in sources.json: can it be reached and read?
Run:  python check_sources.py        (about 3-6 minutes)
Output: a summary on screen plus sources_check.csv with one row per source.
Tip: run it from India. Some .gov.in sites block foreign servers (including GitHub's)."""
import csv, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import requests, urllib3
from bs4 import BeautifulSoup
import tracker

urllib3.disable_warnings()
FIX = {
    "OK": "",
    "CAPTCHA": "Needs browser automation (Playwright), or check this site manually.",
    "EMPTY / JS-ONLY": "Page loads but has almost no readable links. Needs Playwright, or find the real tenders-page URL.",
    "NOT FOUND": "URL has changed. Find the current page and update 'Tender page URL' in the Excel.",
    "BLOCKED": "Site refuses automated access. Try from India, use Playwright, or skip.",
    "SERVER ERROR": "Site is down or struggling. Retry later.",
    "TIMEOUT": "Too slow or unreachable from here. Retry, or run from India.",
    "DNS ERROR": "Domain does not exist. The URL is probably wrong.",
    "CONNECTION ERROR": "Could not connect. Retry, or check the URL.",
}


def check(src):
    t0, ssl_issue, row = time.time(), False, {"id": src["id"], "name": src["name"],
        "category": src["category"], "url": src["url"], "verdict": "", "http": "", "seconds": "",
        "links": "", "matches": "", "note": ""}
    try:
        try:
            r = requests.get(src["url"], headers=tracker.HEADERS, timeout=25)
        except requests.exceptions.SSLError:
            ssl_issue = True
            r = requests.get(src["url"], headers=tracker.HEADERS, timeout=25, verify=False)
        row["http"], row["seconds"] = r.status_code, round(time.time() - t0, 1)
        code, low = r.status_code, r.text.lower()
        if code in (404, 410):
            row["verdict"] = "NOT FOUND"
        elif code in (401, 403, 429):
            row["verdict"] = "BLOCKED"
        elif code >= 500:
            row["verdict"] = "SERVER ERROR"
        elif code >= 400:
            row["verdict"] = "BLOCKED"
        else:
            soup = BeautifulSoup(r.text, "html.parser")
            links = len(soup.find_all("a", href=True))
            row["links"] = links
            if "captcha" in low and links < 40:
                row["verdict"] = "CAPTCHA"
            elif links < 5 or len(soup.get_text(" ", strip=True)) < 200:
                row["verdict"] = "EMPTY / JS-ONLY"
            else:
                row["verdict"] = "OK"
                row["matches"] = len(tracker.scan(src, html=r.text))
                if row["matches"] == 0:
                    row["note"] = "Readable, but no disaster tenders matched today. Normal for many sources."
            if urlparse(r.url).netloc != urlparse(src["url"]).netloc:
                row["note"] = (row["note"] + " Redirects to " + urlparse(r.url).netloc + ".").strip()
        if ssl_issue:
            row["note"] = (row["note"] + " Certificate problem (read anyway).").strip()
    except requests.exceptions.Timeout:
        row["verdict"] = "TIMEOUT"
    except requests.exceptions.ConnectionError as e:
        m = str(e).lower()
        row["verdict"] = "DNS ERROR" if ("name or service" in m or "getaddrinfo" in m or "nodename" in m) else "CONNECTION ERROR"
    except Exception as e:
        row["verdict"], row["note"] = "CONNECTION ERROR", f"{type(e).__name__}: {str(e)[:80]}"
    return row


def main():
    sources = json.load(open(tracker.P("sources.json"), encoding="utf-8"))
    print(f"Checking {len(sources)} sources...")
    with ThreadPoolExecutor(10) as ex:
        rows = list(ex.map(check, sources))
    with open("sources_check.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) + ["fix"])
        w.writeheader()
        for r in rows:
            w.writerow({**r, "fix": FIX.get(r["verdict"], "")})
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    ok = counts.get("OK", 0)
    out = [f"Readable: {ok} of {len(rows)} sources", ""]
    out += [f"  {v}: {c}" for v, c in sorted(counts.items(), key=lambda x: -x[1])]
    out += ["", "Sources that need attention:"]
    out += [f"  [{r['verdict']}] {r['name']}  {r['url']}" for r in rows if r["verdict"] != "OK"]
    text = "\n".join(out)
    print(text)
    print("\nFull report with suggested fixes: sources_check.csv")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write("```\n" + text + "\n```\n")


if __name__ == "__main__":
    main()
