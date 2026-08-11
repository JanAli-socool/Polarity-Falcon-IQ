# Stage 2 engineering decision record

This log records decisions as they are made. Later changes remain visible rather than rewriting earlier judgment.

## D-001 — Treat Stage 1 corrections as release gates, not a side task

**Date:** 2026-08-11 PKT  
**Decision:** A Stage 2 record, answer, index, or interface cannot ship through a compatibility exception for Stage 1. The canonical-release, claim-governance, evidence-alignment, aggregate-query, regression, and product-language corrections block release.  
**Reason:** The brief applies one inclusion and language standard to all 500 records, including Stage 1 records. The current 26 CSV rows have no qualifying contact route, so they do not qualify merely because they shipped before.  
**Rejected:** Hand-correcting the Stage 1 JSONL and retaining the existing app while building a separate 500-row file. That would fix a visible symptom while preserving two product truths.

## D-002 — Use external directories only for candidate discovery

**Date:** 2026-08-11 PKT  
**Decision:** A registry, directory, search result, association page, or filing can create a candidate. It cannot create a production contact by itself. Firm classification, named-person identity, contact-route ownership/current-use, and decision-relevant enrichment each require field-level evidence through the same pipeline.  
**Reason:** This enforces the no-preassembled-list rule and prevents a convenient source's blind spots from becoming product claims.  
**Rejected:** Importing a family-office directory and filling only its missing columns.

## D-003 — Deterministic policy owns release and assurance language

**Date:** 2026-08-11 PKT  
**Decision:** Models may plan searches and compose candidate wording, but cannot authorize records, upgrade evidence labels, calculate release totals, or decide whether unsupported text reaches the buyer. Deterministic validators own those boundaries.  
**Reason:** A prompt is not an enforced control, and a failed check must affect what ships.  
**Rejected:** Asking an LLM to self-grade its answer as grounded.

## D-004 — Canonical operational state plus generated customer representations

**Date:** 2026-08-11 PKT  
**Decision:** Keep one canonical, machine-readable operational record state with explicit authorized/quarantined/rejected status. Generate customer CSV, customer JSONL, search documents, and a count/checksum manifest in one release transaction. CI re-runs reconciliation and fails on drift.  
**Reason:** The Stage 1 CSV/JSONL conflict must become structurally difficult, not merely corrected once.  
**Implementation choice:** Canonical JSONL was selected for atomic replacement, transparent diffs, portable scheduled artifacts, and acceptable linear-scan cost at the 500-record target. SQLite remains a measured-latency option at larger scale, not a default dependency.

## D-005 — New retrieval capability: evidence-aware mandate search

**Date:** 2026-08-11 PKT  
**Decision:** Build a hybrid capability that decomposes a buyer mandate into structured constraints and evidence-bearing soft-fit criteria, searches the complete release, exposes coverage/unknowns, and returns exact denominator-scoped counts.  
**Buyer job:** Find, evaluate, and prioritize family offices without treating missing mandate evidence as negative evidence.  
**Why it exceeds Stage 1:** Stage 1 retrieves semantically close people. It cannot compute whole-dataset coverage, combine filters with mandate evidence, distinguish a weak fit from missing evidence, or explain the decision burden remaining.  
**Rejected:** A generic score/ranking screen. A ranking is not valuable unless each contribution and missing input changes what the buyer can defensibly do.

## D-006 — Agent boundary

**Date:** 2026-08-11 PKT  
**Decision:** The model may choose the sequence of read-only tools needed for a natural-language goal, revise its search after inspecting coverage, compare candidates, and decide that more evidence is required. Tool schemas, row authorization, aggregate computation, confidence vocabulary, claim-to-evidence checks, and final display policy remain deterministic.  
**Reason:** This makes model judgment inspectable while keeping trust-bearing decisions under fixed control.  
**Rejected:** Fixed one-pass retrieval disguised with multiple named agents; autonomous writes to production records from a customer query.

## D-007 — Free-tier deployment and scheduling

**Date:** 2026-08-11 PKT  
**Decision:** Reuse the existing Streamlit Community Cloud deployment for buyer pages and use GitHub Actions on the default branch for scheduled refreshes, subject to Jan merging the deployable pull request. Scheduled refreshes should not require an LLM key unless evidence later establishes a need.  
**Reason:** Both platforms retain their own visible history, fit the existing stack, and can remain live without paid infrastructure.  
**Known boundary:** This working session is fixed to `arena/019ff03c-falcon-fo`; Jan must merge its pull request to `main` for the existing Streamlit deployment to update. Because the connected App cannot write workflow files, Jan must also install the preserved templates through GitHub's web interface before any Stage 2 schedule exists (see D-009).

## D-008 — Do not fabricate human provenance

**Date:** 2026-08-11 PKT  
**Decision:** The repository will mark Jan's active-attention time, exact receipt time, AI-export completeness, email sending, screenshots, and personal final review as pending until Jan supplies or performs them.  
**Reason:** These facts are outside the code and cannot be inferred from agent activity.  
**Rejected:** Converting tool-call timestamps into Jan's hands-on time or stating that he reviewed files because they exist.

## D-009 — Preserve workflow templates without blocking all application delivery

**Date:** 2026-08-11 PKT  
**Decision:** After two atomic push rejections and Jan's confirmation that workflow permission cannot be enabled, restore `.github/workflows/` to the repository baseline and preserve the Stage 2 definitions as inert, exact templates under `docs/stage2/workflow_templates/`. Push the application branch without claiming a schedule; require Jan to install the templates through GitHub's web interface under his own authority.  
**Reason:** GitHub rejects the entire branch when this App changes a workflow. Keeping those changes in branch history would also prevent the buyer application, policy, and evidence tooling from reaching review. A template is not a deployed scheduler, so the UI and documentation explicitly say no scheduled evidence exists.  
**Rejected:** Calling a local process “scheduled,” omitting workflow files without preserving the intended configuration, retrying the same denied push, or asking Jan for a token.
