# Methodology — Family Office Contacts Dataset & Micro-RAG

**Build window:** ~10 hours, single engineer, $0 tooling budget (all free/local stack).
**Final artifact:** 26 verified contact records across 6 family offices + live RAG app.

---

## 1. Discovery

We used a **multi-arm, multi-angle** discovery strategy to avoid inheriting any single source's blind spots — the Critical Sourcing Rule from the brief.

### Arm 1 — Web search across 12 query angles
Using DuckDuckGo (via the `ddgs` library — free, no API key), we ran 12 deliberately non-overlapping queries designed to surface family offices through different lenses:
- Direct: `"family office" appointed OR promoted OR joined 2024`
- Regulatory: `Form ADV "family office" site:sec.gov`
- Team pages: `"family office" "team" OR "our people" site:*.com`
- News/PR: `"family office" press release appoints OR names OR joins`
- (see `pipeline/01_discover_probe.py` and `01b_discover_more.py` for full list)

**Result:** 113 total hits across **80 distinct domains**. The single highest-frequency domain (linkedin.com) contributed 10 hits (~9%). No aggregator dominated the pool. This is our concrete proof of source diversity.

### Arm 2 — SEC EDGAR full-text search
We noticed `sec.gov` surfacing organically in Arm 1, so we added a dedicated SEC search using `efts.sec.gov/LATEST/search-index` (public, no key). This returned **56 unique registered entities (CIKs)** matching `"family office"`, `"single family office"`, `"multi-family office"`, and `"family investment office"`.

**Insight recorded:** most SEC ADV filings that mention "family office" are investment advisors *serving* family offices, not family offices themselves. SEC was retained as a corroborating channel rather than a primary source of firms.

---

## 2. Firm extraction

`pipeline/02_extract_firms.py` parses titles+snippets from Arm 1's raw hits using regex patterns tuned for firm-name shapes (`<Proper Noun> Family Office(s)` and `<Proper Noun> {Capital|Partners|Holdings|Ventures|Wealth|Group}`).

Two iterations were required:
- **v1:** produced 19 candidates with visible noise (`"LinkedIn. WE Family Offices"`, `"As Angeles Wealth"`).
- **v2:** added leading-token stripping, phrase blacklist, near-duplicate merging → **49 clean candidates**.

Only 2 firms met the initial auto-verification bar of "≥2 distinct discovery domains." That was too strict — a firm surfaced once by Forbes and once by SEC is genuinely real but only counts as 1-2 domains in raw search. This drove a stronger verification approach in the next step.

---

## 3. Firm verification (the pivot)

Instead of relying on discovery-domain diversity as verification, we did **ground-truth verification**: for each candidate, programmatically locate the firm's own website, fetch it, and check whether the site itself contains a family-office self-description.

`pipeline/04_verify_firms.py` verified **18 firms** this way. A subsequent manual triage pass (`pipeline/04b_curate_verified_firms.py`) removed false positives:

**Rejected and why:**
- `MPI Family Office` — auto-verifier returned a YouTube page, not the firm site
- `Startup Mindset For Family Offices` — article title, not a firm
- `Find Single Family Offices` — publication article
- `Rise Of The Family Office` — Tharawat Magazine article
- `Evolution Of Family Office` — academic paper
- `Inside Wealth` — YouTube result
- `UBS Global Family Office` — a division/report of a global bank, not a standalone FO
- `Willoughby Capital Holdings`, `Horizon Family Office` — only third-party profiles found, insufficient primary evidence

**Kept:** 14 curated firms with official-domain verification.

Two of these had unusable auto-discovered URLs (Matter → job board page; Blu → mailchimp landing) that we manually corrected to their real domains. These manual patches are recorded in `docs/BUILD_LOG.md`.

---

## 4. People extraction

`pipeline/05_extract_people.py` fetches each verified firm's home + team pages and extracts named people with titles.

Two extractor iterations:
- **v1** (card-block scan): produced 291 raw people but with widespread name/title mis-splits — e.g. `Contact Full Name = "Operations Santa Monica"` while the real name lived in the title field. Unusable.
- **v2** (DOM-anchored): uses heading tags (`<h2>`/`<h3>`/`<h4>`) as the name anchor, walks siblings for the title, and extracts email + LinkedIn from an expanded neighbor region. Produced **230 candidate people** across 11 firms.

**Trade-off explicitly accepted:** v2 recovered 0 emails (v1 had 10), because most target firm sites render team-page emails client-side via JavaScript, which server-side `requests.get()` cannot see. **Diagnostic evidence:** fetching `fcspwm.com/wealth-planning-services/` returned a 5.5KB shell HTML with zero email strings and zero `mailto:` links; the rendered page (in a browser) would be ~200-500KB. A Playwright-based headless-browser approach would recover these emails but was descoped — 2+ hours of work for one column when the rest of the pipeline needed those hours.

The email validation subsystem (V1/V2/V3/U1/U2 code taxonomy, MX-record verification, `mailto:` link scanning) is implemented and tested; it simply had no inputs on this run.

---

## 5. Curation to final dataset

`pipeline/06_build_final_dataset.py` applies:
- **Firm allowlist** — only curated firms enter the final dataset
- **Name plausibility** — 2-4 tokens, proper-noun shape, no stop-words, no digits
- **Title plausibility** — must contain a role keyword (director / officer / partner / etc.)
- **Deduplication** — one row per (firm, person)
- **Email validation** — MX record check (`dns.resolver`), assigns V2/U2/P0 codes matching the sample dataset's convention
- **Confidence scoring** — high/medium/low based on presence of title + email + team-page URL + firm verification tier
- **Diversity cap** — max 5 people per firm to prevent single-firm dominance

Of the 230 raw candidates, **52 were rejected** by these filters and logged in `data/audit/people_filter_audit.jsonl`. Rejection reasons include: name failed proper-noun shape check, title lacked a role keyword, duplicate within firm, or firm not in curated allowlist.

**Final output:** 26 rows across 6 firms.

**Rows by firm:**

| Firm | Rows |
|---|---|
| Angeles Wealth | 5 |
| Omnia Family Wealth | 5 |
| TFO Family Office Partners | 5 |
| The Boston Family Office | 5 |
| WE Family Offices | 5 |
| Cresset Partners | 1 |

The dataset was **locked at 26 rows rather than padded to 50**: an additional pass would have required either accepting noisy rows the v2 extractor mis-tagged as people, or fabricating rows from firms where the extractor found nothing. Both violate the brief's "no unverified claims" rule. Shipping 26 clean rows is defensible; padding to 50 with noise is not.

---

## 6. Micro-RAG architecture

- **Chunking:** one text block per contact record (`{name} works at {firm}. Title: {title}. ...`). Records are the natural unit; sub-chunking a 100-character record adds no value.
- **Embedding:** `sentence-transformers/all-MiniLM-L6-v2` (local, ~80MB, free). Chosen over API embeddings for the $0 constraint.
- **Vector store:** ChromaDB, persistent local disk.
- **LLM:** Groq's free tier serving `llama-3.1-8b-instant`. Chosen over hosted OpenAI/Anthropic for cost (free) and speed (~0.5s latency).

### The 3-layer epistemic control

The brief demands a "working control that limits what an answer may claim." Prompt instructions alone don't qualify. Our control has three code-level layers:

**Layer 1 — Distance gate.**
Retrieval returns top-k with L2 distances. If the effective top-hit distance exceeds **0.50** (calibrated from empirical probe: strong matches like `"who runs Boston Family Office"` score ~0.32; weak matches like `"partner in Miami"` where Miami is not in the data score ~0.53), the system refuses with an explanation naming the actual distance and the threshold.

**Keyword boost (part of Layer 1):** small embedding models sometimes rank a partial match (`"Chief ... & Partner"`, with "Chief" repeated) above an exact match (`"Chief Investment Officer"`). We apply a −0.15 distance boost when the query names a specific role phrase AND a retrieved title contains that exact phrase. Empirical impact: for the query `"chief investment officer"`, Chuck Carroll (raw distance 0.612 with an exact title match) gets boosted to effective 0.462, promoting him to rank 1 above Edward Lowndes (raw 0.541, no exact match). Without this boost, exact-match queries silently return semantically-adjacent-but-wrong records.

**Layer 2 — Field-presence gate.**
Naive intent detection identifies when a user asks for a specific field (`"email"`, `"phone"`, `"linkedin"`). If the top-hit record has that field blank in metadata, the system refuses with the specific record and field named. This prevents the LLM from ever needing to invent contact data. Empirical example: `"what is Chuck Carroll's email"` → refuses with "Chuck Carroll at TFO Family Office Partners does not have an 'email' value in the dataset."

**Layer 3 — Post-generation claim check.**
After the LLM answers, we regex-extract any emails from the response and confirm each one appears in the retrieved evidence. If the LLM hallucinates an email, it's caught and the UI flags the response as unverified.

A stress test of 17 adversarial / off-topic / malformed / in-domain queries is available via `pipeline/99_stress_test.py`. All 14 out-of-scope prompts (empty input, prompt-injection attempts, SQL/XSS payloads, off-topic questions, and in-domain-but-not-in-data queries) refused correctly with distances 0.54–0.93. The 3 legitimate queries (`chief investment officer`, `Chuck Carroll`, `who works at WE Family Offices`) returned grounded matches at 0.40–0.46.

### Why this satisfies the brief

The brief says: *"Prompt instructions alone are not enough. Telling the model to use only the provided data does not prove that it will obey."* Our control does not rely on the LLM's obedience — Layers 1 and 2 refuse **before** the LLM sees anything, and Layer 3 catches misbehavior **after**. The LLM is bounded on both sides by code.

---

## 7. Known limitations (explicit)

1. **No published emails in the final dataset.** Root cause diagnosed: client-side JS rendering. Fix path known (Playwright); descoped for time. Email validation subsystem is implemented and would activate the moment inputs arrive.
2. **6 firms in the final dataset (14 curated), not 25.** Discovery volume was constrained by free-tier DDG rate limits. A budgeted SerpAPI or Google Custom Search key would 3-5× the pool. Additionally, several curated firms (DCA, Callan, Cresset for most rows) yielded 0-1 people because their team pages use non-standard DOM structures (SPA rendering or `<a>`-tag layouts) that the DOM-anchored extractor doesn't traverse. All extraction rejects are logged in `data/audit/people_filter_audit.jsonl` (52 rejections total, with explicit reasons).
3. **Location fields blank.** We chose not to guess firm cities from press-release datelines; the brief penalizes unverified enrichment. A follow-up pass would parse each firm's "Contact" page for its stated HQ address.
4. **Title field verbosity on Boston Family Office rows.** The DOM extractor captured full bio sentences (`"George helped found The Boston Family Office and now is its Managing Partner..."`) rather than clean role strings. A follow-up pass would use an LLM-based title normalization step.

## 8. What the AI produced vs. what the human decided

- **AI produced:** raw regex extraction, DOM traversal, embedding + retrieval, LLM generation.
- **Human decided:** discovery query angles (chosen for source diversity), the pivot from "≥2 domains" to "own-site verification" (after seeing v1 give only 2-3 verified firms), the curation allowlist (removing YouTube/article false-positives), the decision to ship 26 rows honest rather than 50 padded, the choice of 0.50 threshold (calibrated from real query distances), the −0.15 keyword-boost magnitude (calibrated from Chuck Carroll's specific misranking), the descope of Playwright.

Every judgment call in the audit files and the build log is a human one, informed by AI output.