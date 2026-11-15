"""Turns the Excel registry into sources.json. Run after editing the spreadsheet:
python make_sources.py disaster-tender-sources.xlsx
Uses 'Tender page URL' when filled, else the website. Status 'Skip' removes a source."""
import json, sys
from openpyxl import load_workbook
ws = load_workbook(sys.argv[1] if len(sys.argv) > 1 else "disaster-tender-sources.xlsx")["Registry"]
out = []
for r in ws.iter_rows(min_row=2, values_only=True):
    id_, cat, name, short, geo, site, conf, method, prio, tender, status = r[:11]
    url = (tender or site or "").strip()
    if not url or (status or "").strip().lower() == "skip":
        continue
    out.append(dict(id=id_, name=name, short=short, category=cat, geo=geo, url=url,
                    method=method, priority=prio, conf=conf))
json.dump(out, open("sources.json", "w"), indent=1, ensure_ascii=False)
print(len(out), "sources written")
