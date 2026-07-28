\# Build Session Log — Falcon FO Assessment



\## H 0.0 – 0.5  Setup + free-stack decisions

\- Chose Python + DDGS + BeautifulSoup + Chroma + sentence-transformers + Streamlit.

\- Rejected paid APIs (SerpAPI, OpenAI paid tier) per constraints.

\- Chose Groq free tier for LLM (backup: template-based answer if API fails).



\## H 0.5 – 1.5  Discovery arm 1 (web search, multi-angle)

\- 4 initial queries → 40 hits across 28 domains.

\- Ran a 2nd pass with 8 more angles → 113 total hits, 58 additional domains.

\- Domain diversity: 0.7 (healthy — no single source dominates).

\- Discovered `sec.gov` appearing organically → suggested SEC as arm 2.



\## H 1.5 – 2.0  Firm-name extraction

\- Regex-based extractor with strong bad-token filters.

\- v1 produced 19 candidates; noise like "LinkedIn. WE Family Offices" appeared.

\- v2 added leading-token stripping, phrase blacklist, and near-duplicate merge → 49 clean candidates.



\## H 2.0 – 2.5  Discovery arm 2 (SEC EDGAR)

\- Fixed API endpoint (`efts.sec.gov/LATEST/search-index`), used correct `q=` param.

\- Retrieved 56 unique CIKs. Most turned out to be investment advisors mentioning FOs in filings, not FOs themselves — useful signal but not the primary source.

\- Kept SEC as a corroborating channel rather than primary.



\## H 2.5 – 3.0  Firm verification against own website

\- For each candidate: found their own domain via search, fetched page, checked for FO self-description.

\- 22 firms passed; 18 were retained after triage.

\- Non-firm captures (article titles, YouTube pages) were logged, then curated out in the next step.



\## H 3.0 – 3.5  People extraction

\- Fetched each verified firm's home + team page.

\- Rule-based extraction of name + title + email + LinkedIn from card-like DOM blocks.

\- Extracted 291 raw candidates across 16 firms.

\- Explicitly noted: 291 is over-extraction; downstream curation is required.



\## H 3.5 – 4.0  Curation + final dataset

\- Wrote allowlist-based firm curator (rejects article titles, YouTube results, etc.).

\- Wrote name/title plausibility filters + email MX validation.

\- Deduplicated within firm.

\- Final: 50 rows across 12 firms, 10 with published+MX-verified emails.

\- All rejects logged to `data/audit/` files.



\## Key judgment calls

\- Rejected UBS Global Family Office (division, not standalone) and Willoughby/Horizon (only third-party evidence).

\- Renamed "Billion Omnia Family Wealth" → "Omnia Family Wealth" (extractor captured a $ amount).

\- Chose 5-per-firm cap for people diversity, then filled remaining slots.

\- Chose to leave city/state blank in v1 pass — will enrich in next step rather than guess.



\## What the AI produced vs what I changed

\- AI produced: raw HTML → regex extraction, initial firm list, initial people list.

\- I changed: added 2 more discovery arms after seeing arm-1 gaps, curated firm allowlist by hand

&#x20; (because the automated verifier accepted YouTube pages), triaged 22→14 firms.



\## Known limitations (honest)

\- Email coverage is 20% because most firm sites don't publish emails; guessing patterns would violate the "no unverified claims" rule.

\- City/State/Region are blank in v1; will enrich next step.

\- 12 firms is smaller than 25 target; single-source-per-firm risk mitigated by verifying each firm on its own domain.

H 3.9: Manually removed 4 FCS marketing-blurb rows (FOC_007-010) that the v2 DOM extractor mis-tagged as people. Real FCS people (with emails) were captured by the v1 extractor but lost in v2 — accepted trade-off documented in methodology.
H 4.2: Confirmed via HTML diagnostic that FCS (and by inference other target firm sites) serve a 5.5KB JS shell; team-page emails render only after client-side JavaScript execution. Server-side fetch cannot see them. Playwright/headless browser would recover but is out of 10-hour budget scope. Documented as known limitation. Dataset LOCKED at 26 rows / 6 firms / 0 verified emails.
H 5.0-9.0: Wrote methodology, validation chains, and Task 2 analysis. Deployed to Streamlit Cloud.
