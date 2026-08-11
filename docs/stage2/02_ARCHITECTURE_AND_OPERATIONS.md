# Stage 2 architecture and operating notes

**Snapshot:** 11 Aug 2026. This document distinguishes implemented controls from operating evidence that has actually been earned.

## 1. Product and source strategy

The buyer job is to turn a mandate into a defensible family-office shortlist and a route to the named decision-maker without rechecking every public page. The product adds three connected capabilities:

1. evidence search with hard filters, lexical mandate terms, exact aggregates, compound decomposition, and downloadable evidence packets;
2. a bounded natural-language planner that can call those read tools but cannot create facts; and
3. an explicit healthcare-services LP comparison using healthcare, lower-middle-market, private-markets, and external-fund/LP signals. A missing signal lowers or prevents the recommendation; it is never silently inferred.

Source classes are used for what they can establish. Directories, search results, registries, association lists, and regulatory pages create candidates and provenance. Official team/person pages establish identity, title, firm relationship, and an explicitly published person-owned route. Official investment pages, filings, and dated releases support mandate/activity. Professional profiles may support a current principal route when they resolve to that individual. A candidate is not enriched merely because a seed row was normalized.

The pipeline rotates candidate source classes instead of exhausting one list first. It aims above the release floor—550 qualifying records and 220 qualifying emails—to replenish attrition while the public release remains gated at 500/200. Every production row still needs the same field-level support.

## 2. One data truth and authority flow

```text
external page/search
  → candidate + discovery provenance
  → official-page enrichment and route ownership checks
  → deterministic policy evaluation
  → publish state OR physical quarantine with reasons
  → atomic CSV/JSONL/manifest release
  → read-time policy re-evaluation and identity de-duplication
  → deterministic retrieval/comparison
  → full output replay + cited-ID authority check
  → buyer display
```

`data/stage2/state/records.jsonl` is the sole canonical publish-state input. `stage2/release.py` is the sole customer exporter. It writes CSV, JSONL, counts, source mix, release ID, and checksums as one transaction and then reconciles IDs, ordering, rows, and hashes. The app reads the manifest and authorized record summaries; it has no hard-coded production total and does not read the Stage 1 files.

Policy uses hard floors, not a confidence score that lets one strong field compensate for a missing person, route, or enrichment. Each evidence object names its URL, observation time, source class, extraction method, quote, supported claims, and stable evidence ID. Trust is separately represented as supported current, supported with limitations, conflicted/stale, or quarantined. Generic/shared/guessed/inferred/pattern-generated email can never be upgraded by a deliverability result.

Read authority is defense in depth: even an injected `records` argument is re-evaluated before retrieval. Agent render authority reruns each exact tool call and compares the full output, then confirms all cited IDs belong to the authorized corpus. A changed name, title, firm, route, evidence, aggregate, fit signal, or limitation fails replay and is withheld before Streamlit receives it.

## 3. Agentic versus deterministic boundary

| Model may decide | Model cannot decide |
|---|---|
| Whether a supported user goal needs search or fixed healthcare comparison | Whether a record qualifies or is fresh |
| Two to six allowlisted read calls and their supported filters | A person's identity, role, route ownership, firm class, evidence, or aggregate |
| Query sequence for a compound buyer request | Fit-signal truth, confidence vocabulary, release readiness, or rendering authority |
| Refuse a request it cannot map | Writes to candidate/canonical/quarantine state |

Groq receives a planning prompt and tool schemas and must return JSON. The validator rejects unknown tools, filters, arguments, malformed scalar/list shapes, over-limit calls, and refusal plans that also request work. Model errors trigger a second model attempt; exhaustion invokes a visibly labelled deterministic parser. The fallback keeps search usable but is not represented as model-selected agent behavior. Raw traces keep the exact model request/prompt/schema, unedited response, usage, latency, retries/failures, authorized plan, calls, raw results, replay decision, refusal/abstention, and completion.

The fixed Goal 2 comparator is intentionally deterministic. Its score communicates which published signals are present; it does not estimate investment probability. “No current appetite for external funds found” is a limitation, not evidence that appetite is absent. The supported next action is to use the person-owned route to test mandate and allocation timing without presenting the office as a confirmed LP.

## 4. State, replay, and idempotency

Firm/person normalization produces a stable identity key and record ID. Candidate IDs are stable across discovery cycles. Canonical and candidate files are atomically replaced; repeated enrichment merges route and intelligence values by stable tuples, retains the newer freshness check, and recomputes policy. Release IDs are content-derived, so the same canonical state yields the same release identity even if exported later.

A GitHub run/attempt creates a distinct cycle ID. Operating events have a monotonically increasing per-attempt sequence and are appended to a raw JSONL file; a hashed summary points to that raw log. HTTP start/completion/failure, retry delay, extraction rejection, trust transition, replenishment progress, final state, and exceptions remain observable. A failed atomic state write leaves the prior file intact. A rerun upserts stable identities rather than adding a second production person.

Trust refresh starts with the oldest checks. It fetches the route evidence source (or performs a profile lookup), compares content hashes with prior observations, and verifies that the named person and route remain present. Missing required evidence changes trust state, removes the row from release, writes quarantine evidence, and triggers replenishment. A dependency timeout is deferred only where absence cannot be established; a required official source that fails under the implemented path is conservatively quarantined and logged.

## 5. Cost, latency, recovery, and the first 5,000 records

The stack uses Streamlit Community Cloud, GitHub Actions, public sources, DuckDuckGo search, and a Groq free-tier key. Scheduled data acquisition does not require an LLM. Agent traces record provider usage and label externally reported model cost as `$0.00` only when that is what the configured free-tier run reports; the system does not convert missing billing data into a fabricated cost estimate.

**Measurements currently available:** the 49-test Stage 2 suite, including Streamlit page integration, completes in 1.11 seconds locally. The first preserved goal run completed on an empty release using deterministic fallback because no local Groq key was configured; its deterministic tool events rounded to near-zero milliseconds and are not a valid 500-record production latency or refresh-cost measurement. No scheduler cycle has run, so refresh cost per record/all 500, production p50/p95 HTTP latency, and model planning latency remain unmeasured. They must be computed from uncurated cycle/goal logs after deployment rather than predicted as facts.

The first 5,000-record bottleneck is evidence acquisition, not JSON filtering: official sites vary in DOM structure, block automation, change staff pages, and require multiple requests per person. The current polite client is mostly serial, has a 150 ms minimum interval and up to three bounded attempts with 1/2-second backoff; worst-case source timeouts dominate. Before 5,000, move to domain-aware bounded concurrency, per-domain rate limits, observation caching/content-hash no-op refreshes, source-specific queues, and checkpointed batches. Keep policy evaluation synchronous and deterministic. Retrieval can remain a linear scan at 5,000 while measured latency is low; only then consider SQLite indexes. Do not introduce a vector database merely to mask source-acquisition throughput.

Recovery is fail-closed. Retryable HTTP statuses and network failures use bounded attempts, then emit failure and continue/quarantine according to claim authority. The uninstalled workflow template includes a transparently labelled induced 503 exercise and separate recovery probe. That code path does not prove a running dependency event, and no such acceptance evidence currently exists. Unhandled cycle errors emit `cycle.exception`, finalize a failed summary, and exit non-zero.

## 6. Demonstrated value and current gaps

Stage 1 exposed semantic-nearest records and could display an answer after a post-generation warning. Stage 2 removes vector distance from buyer copy, decomposes compound work, calculates exact corpus-wide mixes/counts, exposes ownership/freshness evidence, withholds modified claims before render, and makes missing LP support change the action. The buyer can download retrieval evidence and a complete agent trace rather than manually transcribing links.

This value is implemented and tested, but the current dataset is not a finished commercial release. The truthful state is 0 qualifying records, 0 emails, and an empty source mix; 26 legacy rows remain quarantined. Goal packets from `RUN_20260811T131652Z` preserve that empty-state result and a Goal 2 abstention, but they used deterministic fallback and must be rerun with model planning after data exists. GitHub rejected workflow-file pushes because the connected App lacks workflow permission, so there are no scheduler-owned cycles, 48-hour span, running dependency event, later-cycle trust event, or valid production cost/latency measurement yet.
