# Stage 2 requirement and acceptance matrix

**Status as of 11 Aug 2026.** `Implemented` means code and tests exist; it does not substitute for required production operating evidence. `Observed` names an actual artifact. `Blocked — human/platform` cannot be completed truthfully by this coding session.

## Clock and human-owned obligations

| Requirement | Proof | Current status |
|---|---|---|
| Five-calendar-day window | Receipt and submission timestamps | Receipt remains approximate: 10 Aug 2026 around 17:30 PKT. Deadline is therefore approximately 15 Aug around 17:30 PKT. Exact receipt is human-owned. |
| Day-2 checkpoint | Sent email with two live links, scheduler screenshot, and three predictions | **Blocked — human/platform.** Not sent by this agent. |
| Measured time | Elapsed window, human active attention, unattended runtime reported separately | Elapsed window can be computed at submission. Jan's attention is blank. No scheduler runtime exists yet. |
| Complete AI record | Unedited export beginning with this Arena session plus any later material sessions | **Blocked — human action.** Index exists; export is absent. |
| Personal final review | Signed checklist and disclosed omissions | **Blocked — human action.** |

## Dataset and source mandate

| Requirement | Gate / proof | Current status |
|---|---|---|
| 500 unique qualifying records | `stage2/policy.py`, `stage2/release.py`; final gate exits non-zero below 500 | **Implemented, observed at 0/500. Not accepted.** |
| Stage 1 under same policy | `stage2/import_stage1.py`; physical quarantine | **Observed:** all 26 Stage 1 rows quarantined; four sibling-only marketing fragments rejected. None count. |
| Named-person route on every record | `route_qualifies`; policy fixtures | **Implemented/tested.** Current qualifying total 0. |
| At least 200 professional emails | `email_qualifies`; manifest recomputation | **Implemented, observed at 0/200. Not accepted.** Generic, shared, guessed, inferred, and pattern-generated emails fail. |
| Actionable intelligence beyond seed | Evidence/source separation in policy and enrichment | **Implemented/tested.** No seed-only production path. |
| Discovery source and source mix | Per-record discovery fields; manifest `source_mix` | **Implemented; current production mix is truthfully empty.** |
| No preassembled production import | Discovery sources create candidates only; policy controls promotion | **Implemented/tested.** |
| Exclude uncertainty/duplicates | Lifecycle/trust gates, identity-key uniqueness, physical quarantine | **Implemented/tested.** |
| Reject navigation/non-person fragments | DOM-card extraction and adversarial policy fixtures | **Implemented/tested.** |
| Field-level source truth | Stable evidence IDs, URL, observed time, extraction method, supported claims | **Implemented/tested.** |

## Canonical release and controls

| Requirement | Gate / proof | Current status |
|---|---|---|
| One canonical release | `records.jsonl` → atomic CSV/JSONL/manifest export | **Implemented/observed.** Current zero-row release reconciles. |
| Rejected records cannot leak | Policy-authorized reads and canonical export tests | **Implemented/tested.** |
| Every count reconciles | Manifest checksums, IDs, ordering and row counts; app reads manifest | **Implemented/tested.** |
| Claim coverage before render | Agent replays complete deterministic outputs; retrieval emits evidence summaries only | **Implemented/tested**, including modified-title refusal and unauthorized-state exclusion. |
| Failed checks govern display | Quarantine at release; no-match/abstain/refuse before UI render | **Implemented/tested.** |
| Evidence shown is evidence used | UI renders route, role, classification and enrichment evidence from authorized summaries | **Implemented; local preview running.** Deployment pending. |
| Assertions can fail | Stage 2 pytest suite and CI workflows | **Observed:** 49 tests pass locally on 11 Aug 2026, including all three Streamlit pages and governed empty-search integration. |
| Plain, mechanism-accurate language | Replaced Stage 1 distance/confidence UI with buyer search, agent, trust pages | **Implemented; local preview only.** |

## Retrieval, agent, and customer value

| Requirement | Proof | Current status |
|---|---|---|
| Paid-tier retrieval capability | `stage2/retrieval.py`; `app/main.py` | **Implemented/tested.** Exact filters, aggregates, compound decomposition, evidence packets, explicit denominator. |
| Agent uses retrieval tools | `stage2/agent.py`; raw JSONL traces | **Implemented/tested.** Model may plan only; deterministic tools and replay own facts/rendering. |
| Agentic/deterministic boundary | Code plus `02_ARCHITECTURE_AND_OPERATIONS.md` | **Implemented/documented.** |
| Goal 1 | Exact goal/manual output/structured output/raw trace | **Observed with empty release and deterministic fallback** under `data/stage2/goal_outputs/RUN_20260811T131652Z/goal_1/`. Must rerun with model and populated release. |
| Goal 2 verbatim | Same four artifacts plus confidence/abstention | **Observed abstention with empty release and deterministic fallback** under the same run's `goal_2/`. Exact wording preserved. Must rerun with model and populated release. |
| Goal 3 | Named buyer challenge and four artifacts | **Observed with empty release and deterministic fallback** under the same run's `goal_3/`. Must rerun with model and populated release. |
| First-time buyer comprehension | Task/result/evidence/limitation/action in all normal states | **Implemented locally; buyer/deployed integration review pending.** |
| Contact-route usability | Named owner, route type/value, ownership/current-use bases and evidence | **Implemented.** No route is currently rendered because no record qualifies. |

## Scheduled operation

| Requirement | Proof | Current status |
|---|---|---|
| Deployed by end of Day 2 | Live app and scheduler history | **Blocked — GitHub App lacks workflow-file permission.** Exact workflow definitions are inert templates under `docs/stage2/workflow_templates/`, not installed schedules. Existing public app remains Stage 1 until merge/redeploy. |
| Two scheduled cycles over at least 48 hours | Platform run list, detail pages/screenshots, raw logs | **Not started.** The Stage 2 workflow has never reached `.github/workflows/`; see `04_MANUAL_WORKFLOW_SETUP.md`. |
| Complete unattended logs | Sequenced JSONL cycle events and signed summaries | **Implemented, no scheduled production logs yet.** |
| Real dependency failure handled | Raw failure/retry/recovery/escalation events | Transparent dependency-failure exercise implemented; required running-platform event not yet observed. |
| Later evidence-based trust event | Later cycle changes state of earlier processed record for evidence reason | Logic implemented; **not observed** across real cycles. |
| Idempotency/replay | Stable identities, upserts, sequence and tests | **Implemented/tested.** |
| Cost/concurrency/recovery | Per-call latency, attempt/retry/failure and cost fields | **Implemented; production measurements pending.** |
| Stay live 21 days | Hosting/scheduler config plus post-submission monitoring | **Blocked — human/platform monitoring.** |

## Current release result

- Release: `REL_4FC7D7694DEEDC6E`
- Qualifying records: **0**
- Qualifying firms: **0**
- Qualifying professional emails: **0**
- Release ready: **false**
- Failures: `records 0 < 500`; `qualifying_emails 0 < 200`

These figures are deliberately not replaced with candidate, quarantine, or legacy counts.
