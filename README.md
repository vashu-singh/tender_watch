# Disaster tender watch

Scans ~200 disaster, climate, GIS and risk organisations every day and publishes a searchable site.

## Set up (about 10 minutes, free)
1. Create a new GitHub repository and upload everything in this folder (keep the `.github` folder).
2. Repo Settings > Pages > Source: **GitHub Actions**.
3. Actions tab > "Daily tender scan" > **Run workflow**. The first run (5-15 min) builds the baseline and publishes the site.
4. Your site is at `https://<your-username>.github.io/<repo-name>/`. After that it refreshes daily at 07:30 IST.

## Email alerts (optional)
Repo Settings > Secrets and variables > Actions: add `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `MAIL_TO`. New finds are emailed each day (not on the first run).

## Improve coverage
- Open the site's **Source health** tab. Sources marked failed need a different URL or a browser-based scraper.
- Edit `disaster-tender-sources.xlsx`: paste the real tenders-page URL in "Tender page URL", or set Status to `Skip`. Then run `python make_sources.py` and upload the new `sources.json`.
- Edit `KEYWORDS` in `tracker.py` to widen or narrow what counts as relevant.

## Know the limits
- CAPTCHA and JavaScript-only portals (CPPP, GeM, many state portals) return little or nothing to this plain scraper. They need Playwright, which is the next upgrade.
- Closing dates are guessed from page text and can be wrong. Always open the original tender.
- Check each site's terms of use. The scraper is polite (few requests per site, once a day).
