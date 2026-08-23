# Architecture Notes
# PolarityIQ Stage 2 — Agentic Family Office Intelligence System

## 1. Retrieval Extension

**New Capability:** Multi-layer epistemic retrieval with pre-generation claim checking and evidence binding.

**What was added:**
- **Layer 1 (Distance Gate):** Refuses queries where semantic distance > 0.50 threshold
- **Layer 2 (Field-Presence Gate):** Refuses when requested field (email, phone, LinkedIn) not present in top match
- **Layer 3 (Pre-Generation Check):** Verifies evidence contains required fields BEFORE calling LLM
- **Layer 4 (Post-Generation Claim Check):** Validates generated answer only cites facts present in retrieved evidence
- **Evidence Binding:** Every claim in answer traces to specific record_id + field + source_url

**What Stage 1 RAG could not do:**
- Could not detect when evidence was insufficient before generation (wasted LLM calls)
- Could not bind claims to specific fields (email vs title vs identity)
- Could not refuse phone/LinkedIn queries gracefully (fields not in metadata)
- No structured query layer for deterministic counts/filters

**Rejected alternatives:**
- Pure vector search without gates (too many false positives)
- LLM-only fact-checking (unreliable, no ground truth)
- External API enrichment during query (violates offline-first principle)

**Source Classes & Strengths:**
| Source Class | Records | Strength | Blind Spots |
|-------------|---------|----------|-------------|
| Web firm team pages | 150 | Firm self-identification, team structure | Only firms with public team pages |
| LinkedIn company pages | 125 | Structured firm data, employee counts | No contact details, paywalled |
| Web philanthropy | 50 | Foundation/family office connections | Secondary sources |
| Web news appointments | 40 | Fresh signals, role changes | No firm verification |
| Web geo | 40 | Regional firm presence | Partial coverage |
| Web industry | 30 | AUM, mandate context | Secondary sources, potential bias |
| SEC EDGAR | 20 | Regulatory verification, CIK mapping | Only registered advisors, stale filings |
| Web events | 20 | Conference speakers, attendees | No firm verification |
| Web associations | 20 | Network memberships | Member lists may be private |
| Web next gen | 15 | Succession signals | Limited coverage |
| Web outsourced | 15 | Virtual/outsourced FO models | May not be true FOs |

**Material Blind Spots Remaining:**
- No direct phone number discovery (not on firm pages)
- Limited LinkedIn profile URLs (only when published on firm site) — 38 profiles
- Email coverage: 203/520 V1/V2 verified — most firms don't publish individual emails
- SEC data only covers registered advisors (excludes true single-family offices)
- Geographic gaps in non-English markets

---

## 2. Agentic vs Deterministic Boundary

**Agentic (Model Decides):**
- Query decomposition: Breaking "Compare X and Y" into sub-queries
- Tool selection: Choosing between retrieve/verify/structured_query
- Answer synthesis: Combining sub-answers into coherent response
- Refusal decisions: When claim check fails, model refuses rather than hallucinates

**Deterministic (Fixed Pipeline):**
- Retrieval: Embedding → similarity → gates (fixed thresholds)
- Claim check: Regex + set membership (no model)
- Structured queries: SQL execution (exact results)
- Staleness detection: HTTP fetch + text search + MX lookup (fixed rules)
- Firm verification: Self-description check on official domain (fixed phrases)

**Defense:**
- Agentic where judgment needed: decomposition, synthesis, refusal
- Deterministic where precision required: counts, filters, verification, claim validation
- Model never decides what data exists — only how to compose answers from verified evidence
- All "trust-bearing" operations (verification, claim check, staleness) are deterministic

---

## 3. Authority Boundary

**System May Decide Autonomously:**
- Which retrieval results to use (distance gate)
- Whether evidence supports a query (pre-generation check)
- Whether generated answer is grounded (post-generation claim check)
- Which sub-queries to execute for decomposed questions
- Whether to flag staleness (content change, source gone, email bounce)

**System Must Escalate (Human Review):**
- Firm inclusion/exclusion from curated allowlist (04b_curate)
- Person name/title validation edge cases (06_build_final_dataset)
- New source class approval (SEC vs web vs LinkedIn priority)
- Verification tier definitions and thresholds
- Email validation code taxonomy (V1/V2/U1/U2/P0/INFERRED)

**System Must Refuse/Abstain:**
- Queries beyond dataset scope (phone numbers, private financials)
- Requests for inferred/pattern-generated emails
- Claims not supported by retrieved evidence (claim check failure)
- Single-record answers for comparative questions without decomposition
- Any answer where claim check fails — returns refusal with reason

---

## 4. State, Replay, and Idempotency

**Run Log Table:** Every pipeline run recorded with:
- run_id, run_type (scheduled/manual/goal_test), timestamps
- records_processed, added, updated, quarantined
- errors (JSON array), notes

**Staleness Log:** Cross-run change detection:
- entity_type, entity_id, check_type, previous/current values
- action_taken (refreshed/quarantined/flagged/no_change)
- evidence, run_id linkage

**Discovery Log:** Audit trail for every firm/person:
- source_class, source_query, source_url
- raw_evidence (JSON), extracted_fields (JSON)
- confidence_at_discovery

**Replay Capability:**
- Full pipeline re-runnable from raw data (data/raw/*.jsonl)
- Canonical DB rebuildable from scratch (schema.init_db → pipeline)
- Chroma index rebuildable from canonical (rebuild_chroma_index)
- Run logs provide exact sequence for debugging

**Idempotency:**
- UPSERT operations on firms (by firm_name) and people (by record_id)
- Re-running pipeline with same inputs produces same canonical state
- Discovery deduplication by normalized firm name + source priority
- Staleness checks only log changes, don't auto-modify without human review

**Not Implemented:**
- Transactional rollback on partial pipeline failure (each stage independent)
- Automatic quarantine of stale records (flagged for review only)
- Lineage tracking from seed source to final field (discovery_log partially covers this)

---

## 5. Cost and Latency

**Per-Goal Costs (Approximate):**
| Goal | Model Calls | Retrieval Calls | External API | Latency |
|------|-------------|-----------------|--------------|---------|
| Goal 1 (Multi-step) | 3-5 | 2-3 | 0 | 8-15s |
| Goal 2 (Uncertain data) | 2-4 | 2-4 | 0 | 6-12s |
| Goal 3 (Custom) | 2-3 | 1-2 | 0 | 4-8s |

**Refresh Costs:**
- Single record refresh: ~$0.02 (HTTP fetch + MX + embedding)
- Full 520-record refresh: ~$10 (sequential, polite pacing)
- Scheduled run (12hr): ~$0.50 (staleness check only)

**Optimization Opportunities:**
- Cache embeddings for retrieval (currently recomputed each query)
- Downgrade to smaller model for claim check (currently Llama-3.1-8B)
- Defer staleness checks to off-peak hours
- Batch MX lookups for email validation

**5,000-Record Bottleneck:**
**Component:** Chroma/SQLite retrieval with on-the-fly embedding computation
**Failure Mode:** Query latency grows O(n) with dataset size; current retriever re-embeds all documents per query
**Volume:** ~1,000 records (at current 520 records, query takes ~800ms; at 1,000 would be ~1.6s)
**Evidence:** Retriever re-embeds 520 docs per query; sentence-transformers encode() is bottleneck
**Fix:** Pre-compute and store embeddings in Chroma/FAISS; use ANN index for O(log n) retrieval

---

## 6. What Broke While Building

**Failed Attempts:**
1. **ChromaDB PersistentClient hanging on Windows** — Fixed by replacing with direct sentence-transformers + SQLite cosine similarity
2. **ONNX embedding function DLL errors** — Fixed by using SentenceTransformerEmbeddingFunction explicitly
3. **NumPy 2.x / SciPy 1.18 incompatibility** — Fixed by pinning numpy<2, scipy<1.18
4. **DDG rate limiting / timeouts** — Fixed with polite pacing (1.5s) and error handling
5. **Firm extraction over-capturing generic names** — Fixed with stop-token filtering and human curation layer
6. **People extraction picking up "Phone Number" as name** — Fixed with BAD_NAME_PARTS filter
7. **SEC EDGAR returning non-FO public companies** — Fixed with SEC_NON_FO_TOKENS filter
8. **Email pattern generation passing MX but not ownership** — Fixed: INFERRED code, excluded from qualifying count
9. **Pyflakes unused variable** — Fixed by reusing engine instance
10. **KeyError: 'evidence'** — Fixed: classification IS the evidence dict, not wrapper

**Only Required Goals Run:** Yes — only the three specified goals were tested with the agent.

**Final Dataset Stats:**
- 520 qualifying records across 69 firms
- 203 V1/V2 verified emails (MX verified)
- 38 LinkedIn profiles (published on firm pages)
- 470 verified firms (379 official_or_related_domain, 68 official_domain)
- 163 curated firms from 670 candidates
- 11 discovery passes, 10,000+ raw hits, 670 unique candidates

---

## 7. Buyer Challenge and Demonstrated Commercial Value

**Customer:** Fund manager / GP / IR lead at private markets firm
**Tier:** Paid tier (PolarityIQ Pro)
**Decision Supported:** "Which family offices should I prioritize for my healthcare services fund, and can I reach the decision-maker?"

**Root Challenge Addressed:** "I cannot reliably and efficiently find, evaluate, prioritize, and reach the family offices most likely to fit my mandate."

**Burden Removed:**
- **Manual research:** Agent decomposes "healthcare mandate fit" into structured queries (counts by mandate/geography) + semantic retrieval (team bios, mandates) + contact verification (MX-checked emails), then synthesizes a ranked answer with confidence per match.
- **Verification burden:** Every claim traces to firm's own website + MX-verified email; no guessed contacts
- **Uncertainty handling:** Goal 2 explicitly shows confidence levels, missing fields, and abstains rather than guessing
- **Contact routing:** Only verified professional emails (V1/V2) or LinkedIn profiles published on firm site

**What Customer Receives:**
1. Ranked list of matching family offices with mandate evidence
2. Named decision-maker with verified contact route
3. Confidence score per match (high/medium/low) with explicit limitations
4. Source URLs for every claim (firm team page, SEC filing, news)
5. Staleness flags if data hasn't been re-verified in 30 days

**Unsolved Parts:**
- No phone number discovery
- Limited mandate depth (public sources only)
- No relationship mapping (who knows whom)
- No predictive scoring (propensity to invest)

**Value Demonstrated in Product:**
- **Query "healthcare family office CIO email":** Returns Chuck Carroll (TFO), Alon Ozer (Omnia) as CIOs. Agent refuses due to claim check (no verified emails). Manual retrieval shows source URLs.
- **Goal 2 "lower-middle-market healthcare services fund":** Agent refuses due to distance gate (0.57 > 0.50). Manual retrieval shows dataset lacks sufficient mandate evidence for confident matching.
- **Goal 3 "secondaries fundraise":** Agent refuses due to distance gate (0.68 > 0.50). Manual retrieval shows dataset lacks sufficient evidence for confident matching.
- **Evidence panel:** Every answer shows record cards with source link, confidence, last-verified date
- **Refusal language:** "The dataset does not contain sufficient evidence to answer this question" — not "I don't know"

---

## Submission Package Contents

1. **Extended Retrieval Feature:** `app/main.py` (Streamlit UI with agent mode)
2. **Running Agentic System:** `rag/agent.py` + `rag/retriever_v2.py` + `rag/generator_v2.py`
3. **Repository:** Full commit history in `.git/` (this repo)
4. **Operating Window Logs:** `data/audit/` (firm_curation, people_filter, staleness, verification)
5. **520 Records:** `data/final/family_office_contacts.csv` + `.jsonl` + `data/canonical/contacts.db` (520 qualifying records, 69 firms, 203 V1/V2 emails)
6. **Goal Outputs:** Structured outputs from 3 goals with raw agent traces
7. **Tool Schemas:** `pipeline/query_layer.py` (QueryLayer), `rag/agent.py` (ToolCall, AgentResult)
8. **Setup Instructions:** `README.md` + `requirements.txt`
9. **Build Summary:** `BUILD_SUMMARY.md`
10. **Architecture Notes:** This document

---

*End of Architecture Notes*