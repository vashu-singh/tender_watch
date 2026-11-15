#!/usr/bin/env python3
"""Daily scan: visits every source in sources.json, keeps disaster-related tenders,
updates tenders.json and status.json, and emails new finds if SMTP_* secrets are set."""
import hashlib, json, os, re, smtplib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urljoin, urlparse
import requests, urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings()
HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda f: os.path.join(HERE, f)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DisasterTenderTracker/1.0)"}

KEYWORDS = ["disaster", "drr", "risk assessment", "risk reduction", "risk management", "risk index",
    "vulnerab", "cvra", "hazard", "exposure", "resilien", "sdma", "ndma", "flood", "cyclone",
    "landslide", "earthquake", "seismic", "drought", "tsunami", "heat wave", "heatwave",
    "early warning", "climate risk", "climate change", "adaptation", "emergency", "preparedness",
    "pdna", "post-disaster", "sendai", "glof", "wildfire", "forest fire", "storm surge", "multi-hazard",
    "geospatial", "remote sensing", "gis ", "mitigation", "evacuation", "shelter", "civil defence"]
TENDER_WORDS = ["rfp", "rfq", "eoi", "tender", "expression of interest", "request for proposal",
    "request for quotation", "request for bid", "call for proposal", "invitation for bid", "invitation to bid",
    "notice inviting", "bid", "consultancy", "consulting services", "terms of reference", "empanelment"]
KW = re.compile(r"\b(" + "|".join(re.escape(k) for k in KEYWORDS) + ")", re.I)
TW = re.compile(r"\b(" + "|".join(re.escape(k) for k in TENDER_WORDS) + r")s?\b", re.I)
# jobs, academic posts and similar noise are dropped even if they contain a tender word
BLOCK = re.compile(r"\b(recruit|vacanc|walk-in|walk in|deputation|contractual basis|on contract|appointment|"
    r"position of|post of|posts of|filling up|jobs?|career|internship|fellowship|scholarship|admission|"
    r"professor|faculty|lecturer|individual consultant|individual contractor|apply now)", re.I)
NATIVE = ("Central: nodal", "Central: science", "Central: water", "State SDMA", "State institutes", "State remote")
DATE_RE = re.compile(r"\b(\d{1,2})[-/. ]+(\d{1,2}|[A-Za-z]{3,9})[-/. ,]+(\d{4})\b")
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def relevant(text, native):
    """Return tag list if this looks like a real RFP/tender, else None."""
    text = " ".join(text.split())
    if len(text) < 30 or len(text.split()) < 5 or BLOCK.search(text) or not TW.search(text):
        return None
    tags = sorted({t.lower().strip() for t in KW.findall(text)})
    return tags[:6] if (tags or native) else None


def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
    except requests.exceptions.SSLError:  # many .gov.in sites have certificate problems
        r = requests.get(url, headers=HEADERS, timeout=25, verify=False)
    r.raise_for_status()
    return r.text


def find_deadline(text):
    """Best guess: the latest plausible date in the text (usually the closing date)."""
    today, best = datetime.now(timezone.utc).date(), None
    for d, m, y in DATE_RE.findall(text):
        try:
            mo = int(m) if m.isdigit() else MONTHS[m[:3].lower()]
            dt = datetime(int(y), mo, int(d)).date()
        except (ValueError, KeyError):
            continue
        if today - timedelta(days=30) <= dt <= today + timedelta(days=400):
            best = max(best, dt) if best else dt
    return best.isoformat() if best else None


def scan(src, html=None):
    url, native = src["url"], src["category"].startswith(NATIVE)
    soup = BeautifulSoup(html if html is not None else fetch(url), "html.parser")
    items, links = {}, set()

    def add(text, href):
        text = " ".join(text.split())
        if not text or len(text) > 600 or not href or href.startswith(("javascript:", "mailto:", "#")):
            return
        tags = relevant(text, native)
        if tags is None:
            return
        link = urljoin(url, href)
        if urlparse(link).path in ("", "/") or link.rstrip("/") == url.rstrip("/"):
            return  # a home page, not a tender
        if link in links:
            return
        links.add(link)
        items[text[:200].lower()] = {"title": text[:300], "link": link, "tags": tags,
                                     "deadline": find_deadline(text)}

    for tr in soup.select("tr"):
        a = tr.find("a", href=True)
        if a:
            add(tr.get_text(" ", strip=True), a["href"])
    for a in soup.find_all("a", href=True):
        add(a.get_text(" ", strip=True), a["href"])
    return list(items.values())


def notify(new):
    if not os.getenv("SMTP_HOST"):
        return
    msg = EmailMessage()
    msg["Subject"] = f"{len(new)} new disaster-management tenders"
    msg["From"], msg["To"] = os.environ["SMTP_USER"], os.environ["MAIL_TO"]
    msg.set_content("\n\n".join(f"{n['source']}\n{n['title']}\n{n['link']}" for n in new[:150]))
    with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], 465) as s:
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)


def main():
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    sources = json.load(open(P("sources.json"), encoding="utf-8"))
    try:
        old = json.load(open(P("tenders.json"), encoding="utf-8"))
        baseline = False
    except FileNotFoundError:
        old, baseline = [], True  # first run: everything found is "existing", not "new"
    native_cats = {x["category"] for x in sources if x["category"].startswith(NATIVE)}
    db = {t["id"]: t for t in old
          if relevant(t["title"], t["category"] in native_cats) is not None}  # drop old junk

    def work(src):
        try:
            return src, scan(src), None
        except Exception as e:
            return src, [], f"{type(e).__name__}: {str(e)[:110]}"

    new, health = [], []
    with ThreadPoolExecutor(8) as ex:
        for src, items, err in ex.map(work, sources):
            health.append({"id": src["id"], "name": src["name"], "category": src["category"],
                           "geo": src["geo"], "url": src["url"], "ok": err is None,
                           "count": len(items), "error": err})
            for it in items:
                tid = hashlib.sha1(f'{src["id"]}|{it["title"].lower()}'.encode()).hexdigest()[:16]
                if tid in db:
                    db[tid]["last_seen"] = today
                    db[tid]["deadline"] = it["deadline"] or db[tid].get("deadline")
                    continue
                db[tid] = {"id": tid, "source": src["name"], "category": src["category"], "geo": src["geo"],
                           **it, "first_seen": today, "last_seen": today, "baseline": baseline}
                new.append(db[tid])

    cutoff = (now.date() - timedelta(days=180)).isoformat()
    tenders = sorted((t for t in db.values() if t["last_seen"] >= cutoff),
                     key=lambda t: t["first_seen"], reverse=True)
    json.dump(tenders, open(P("tenders.json"), "w", encoding="utf-8"), ensure_ascii=False)
    ok = sum(h["ok"] for h in health)
    json.dump({"run_at": now.isoformat(timespec="minutes"), "run_date": today, "baseline": baseline,
               "new_count": 0 if baseline else len(new), "total": len(tenders),
               "sources_ok": ok, "sources_failed": len(health) - ok, "sources": health},
              open(P("status.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{len(new)} new, {len(tenders)} total, {ok}/{len(health)} sources ok")
    if new and not baseline:
        notify(new)


if __name__ == "__main__":
    main()
