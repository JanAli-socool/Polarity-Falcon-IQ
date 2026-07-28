# Validation Chains — 3 Records

Per the brief: "Select 3 records and provide a full validation chain: discovery source, extraction method, enrichment steps, validation logic, confidence assessment, and exact sources or links used."

---

## Record 1: Chuck Carroll — Chief Investment Officer at TFO Family Office Partners

**Record ID:** [Record 1 (Chuck Carroll)   → FOC_013]

### Discovery source
Firm "TFO Family Office Partners" was surfaced by web search query:
`"family office" "team" OR "our people" site:*.com`
via DuckDuckGo, returning the page `https://tfofamilyoffice.com/our-team/`.

### Firm verification
- **URL fetched:** https://tfofamilyoffice.com/
- **Self-description found:** "Ultra-High-Net-Worth Wealth Management Firm - TFO Family Office Partners ... Helping Families Thrive By Connecting Wealth and Purpose"
- **Verification tier:** `official_domain`
- **Cross-source corroboration:** firm appeared in Arm 1 via the team-page query and its own team page URL was found in search results.

### Person extraction method
- **Team page URL:** https://tfofamilyoffice.com/our-team/
- **Extraction strategy:** DOM-anchored — name found in an `<h*>` heading tag, title extracted from adjacent sibling text.
- **Extracted values:** `name="Chuck Carroll"`, `title="Chief Investment Officer"`

### Field-level validation
| Field | Value | Verified? | Method |
|---|---|---|---|
| Family Office Name | TFO Family Office Partners | ✅ | firm-verification pass |
| Contact Full Name | Chuck Carroll | ✅ | extracted from `<h*>` on team page |
| Contact Job Title | Chief Investment Officer | ✅ | extracted from adjacent DOM sibling |
| Family Office Country | United States | ✅ | curation allowlist entry |
| Contact Primary Email | (blank) | ⬜ honest blank | email not in server-rendered HTML; see methodology §4/§7 |
| Contact LinkedIn | (blank) | ⬜ honest blank | not published on team page |
| Family Office City | (blank) | ⬜ honest blank | not enriched; see methodology §7 |

### Confidence: **high**
Basis: title extracted, source is a team page (URL contains `/our-team/`), firm verification tier is `official_domain`.

### Exact sources
- Discovery hit: `data/raw/discovery_probe.jsonl`
- Firm verification snapshot: `data/raw/firms_verified.jsonl`
- Team page: https://tfofamilyoffice.com/our-team/
- Extraction record: `data/raw/people_raw.jsonl`
- Final row: data/final/family_office_contacts.csv, row FOC_013   (for Chuck)

---

## Record 2: George P. Beal — Managing Partner at The Boston Family Office

**Record ID:** [Record 2 (George P. Beal)  → FOC_017]

### Discovery source
Firm "The Boston Family Office" was surfaced by web search query:
`"family office" "team" OR "our people" site:*.com`
via DuckDuckGo, returning the page `https://www.bosfam.com/our-team/`.

### Firm verification
- **URL fetched:** https://www.bosfam.com/
- **Self-description found:** "The Boston Family Office – Investment Services ... THE BOSTON FAMILY OFFICE Your Family's Personal Wealth Management Team"
- **Verification tier:** `official_domain`
- **Cross-source corroboration:** firm site self-describes as a family office; team page URL was independently discoverable via search.

### Person extraction method
- **Team page URL:** https://www.bosfam.com/our-team/
- **Extraction strategy:** DOM-anchored — name found in an `<h*>` heading, bio paragraph extracted from adjacent sibling.
- **Extracted values:** `name="George P. Beal"`, `title="George helped found The Boston Family Office and now is its Managing Partner as well as a Portfolio Manager"`
- **Note:** the title field captured a full bio sentence rather than a clean role string. This is a known limitation of paragraph-heavy team pages — a follow-up pass would use an LLM extraction step to normalize titles like this to "Managing Partner, Portfolio Manager". We chose not to add that pass in the 10-hour budget.

### Field-level validation
| Field | Value | Verified? | Method |
|---|---|---|---|
| Family Office Name | The Boston Family Office | ✅ | firm-verification pass |
| Contact Full Name | George P. Beal | ✅ | extracted from `<h*>` on team page |
| Contact Job Title | (bio sentence — see note above) | ⚠️ partial | title present but not normalized |
| Family Office Country | United States | ✅ | curation allowlist entry |
| Contact Primary Email | (blank) | ⬜ honest blank | Boston site's team page does not publish personal emails |
| Contact LinkedIn | (blank) | ⬜ honest blank | not linked from team page |

### Confidence: **high**
Basis: name extracted from a firm-verified team page, title present (though verbose), firm is on `official_domain` tier. High despite the title cleanliness issue — the fact stated (that Beal is a Managing Partner at the firm) is source-verifiable in the very sentence we captured.

### Exact sources
- Discovery: `data/raw/discovery_probe.jsonl`
- Firm verification: `data/raw/firms_verified.jsonl`
- Team page: https://www.bosfam.com/our-team/
- Extraction record: `data/raw/people_raw.jsonl`
- Final row: data/final/family_office_contacts.csv, row FOC_017   (for George)

---

## Record 3: Mel Lagomasino — CEO & Managing Partner at WE Family Offices

**Record ID:** [Record 3 (Mel Lagomasino)  → FOC_022]

### Discovery source
Firm "WE Family Offices" was surfaced by web search query:
`site:linkedin.com/company "family office" United States`
via DuckDuckGo, returning `https://www.linkedin.com/company/we-family-offices`. Its own domain `wefamilyoffices.com` was then found by the firm-locator step.

### Firm verification
- **URL fetched:** https://www.wefamilyoffices.com/
- **Self-description found:** "WE Family Offices - Building your Wealth Enterprise ... WE Family Offices is a different kind of wealth advisor ... an award-winning independent, family office"
- **Verification tier:** `official_domain`
- **Cross-source corroboration:** LinkedIn company page (discovery source) + wefamilyoffices.com (self-description) + ZoomInfo listing = 3 independent domains. Strongest-verified firm in the dataset.

### Person extraction method
- **Team page URL:** https://www.wefamilyoffices.com/we-family-offices/our-team/
- **Extraction strategy:** DOM-anchored — name and title extracted from adjacent heading/paragraph pair.
- **Extracted values:** `name="Mel Lagomasino"`, `title="Chief Executive Officer & Managing Partner"`
- **External sanity check:** Mel Lagomasino is a publicly-known figure in the family-office industry (previously CEO of JP Morgan's Global Wealth Management). Her role at WE Family Offices is independently verifiable in public press, which validates that our extraction is capturing real people, not hallucinations.

### Field-level validation
| Field | Value | Verified? | Method |
|---|---|---|---|
| Family Office Name | WE Family Offices | ✅ | firm-verification pass + 3-domain cross-check |
| Contact Full Name | Mel Lagomasino | ✅ | extracted from `<h*>` on team page |
| Contact Job Title | Chief Executive Officer & Managing Partner | ✅ | extracted from adjacent DOM sibling |
| Family Office Country | United States | ✅ | curation allowlist entry |
| Contact Primary Email | (blank) | ⬜ honest blank | site renders emails via client-side JavaScript — see methodology §4/§7 |
| Contact LinkedIn | (blank) | ⬜ honest blank | not linked from team page |

### Confidence: **high**
Basis: title extracted cleanly, source is an explicit team page URL (`/our-team/`), firm has the strongest multi-source verification in the dataset, and the extracted person is externally recognizable.

### Exact sources
- Discovery: `data/raw/discovery_probe.jsonl`
- Firm verification: `data/raw/firms_verified.jsonl`
- Team page: https://www.wefamilyoffices.com/we-family-offices/our-team/
- Extraction record: `data/raw/people_raw.jsonl`
- Final row: data/final/family_office_contacts.csv, row FOC_022   (for Mel)

---

## Rejected records — for contrast

Per the methodology, records where a plausibility check failed are logged, not silently dropped. From `data/audit/people_filter_audit.jsonl` (52 rejections total in this build), representative examples: