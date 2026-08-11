# Stage 2 checkpoint deliverable index

**Snapshot:** 11 Aug 2026 PKT. This index locates what exists and names what does not. It is not a statement that final acceptance has been reached.

## Customer and repository links

| Deliverable | Direct location | Current truth |
|---|---|---|
| Evidence retrieval | <https://falcon-fo-3gsnwrplstwjvdw4sp7vpg.streamlit.app/> | Existing public service remains the Stage 1 revision until PR merge/redeploy. |
| Research agent | <https://falcon-fo-3gsnwrplstwjvdw4sp7vpg.streamlit.app/Research_Agent> | Expected Streamlit page route after merge/redeploy; not yet a verified live Stage 2 link. |
| Trust and operations | <https://falcon-fo-3gsnwrplstwjvdw4sp7vpg.streamlit.app/Trust_and_Operations> | Expected Streamlit page route after merge/redeploy; not yet verified live. |
| Repository review/history | <https://github.com/JanAli-socool/falcon-fo/pull/1> | Open PR from the Arena session branch with the complete checkpoint commit history. |
| GitHub Actions history | <https://github.com/JanAli-socool/falcon-fo/actions> | Lint passed on PR 1. The unchanged Stage 1 dataset check failed as disclosed; there is no Stage 2 scheduler. |

Do not use the two expected deep links in the Day-2 email until they have been opened successfully in a signed-out browser after merge.

## Data, logs, goals, and reproducibility

| Requested material | Repository location | Current truth |
|---|---|---|
| Final customer CSV/JSONL and release manifest | `data/final/` | Reconciled release `REL_4FC7D7694DEEDC6E`; 0 records and 0 qualifying emails; not release-ready. |
| Canonical record/freshness state | `data/stage2/state/records.jsonl` | Empty canonical state. |
| Candidate/source observations | `data/stage2/state/` | Empty at this checkpoint; no candidate is counted as production. |
| Stage 1 revalidation | `data/stage2/quarantine/stage1_records.jsonl` and `stage1_sibling_drift.jsonl` | 26 quarantined rows and four rejected fragments. |
| Entire-window operating logs | `data/stage2/operating_logs/` | No scheduled production event exists; the directory disclosure explains the absence. |
| Three exact goal packets | `data/stage2/goal_outputs/RUN_20260811T131652Z/` | Complete four-part packets, but empty-release deterministic fallback; Goal 2 abstained. |
| Raw agent trace copies | `data/stage2/goal_logs/` | Three unedited JSONL traces from the preserved goal run. |
| Retrieval/tool schemas and authority | `stage2/retrieval.py`, `stage2/agent.py` | Implemented and tested; exact schema is also embedded in every raw trace. |
| Setup and commands | `README.md` | Local app, tests, reconciliation, pipeline, and goal-run commands. |
| Scheduler setup | `docs/stage2/04_MANUAL_WORKFLOW_SETUP.md` | Required human workaround; templates are not active workflows. |
| Architecture/operations | `docs/stage2/02_ARCHITECTURE_AND_OPERATIONS.md` | Source strategy, boundaries, state/replay, cost/latency, recovery, scaling bottleneck, and value. |
| Sub-half-page build summary | `docs/stage2/03_BUILD_SUMMARY.md` | Truthful checkpoint summary and gaps. |
| Acceptance map | `docs/stage2/00_REQUIREMENTS_AND_ACCEPTANCE.md` | Requirement-by-requirement implemented/observed/blocked state. |
| Human actions/final review | `docs/stage2/HUMAN_ACTIONS.md` | Incomplete checklist; no human action is pre-checked. |
| Time record | `docs/stage2/TIME_LOG.csv` | Agent events only; Jan's active-attention field remains blank. |
| Exact AI prompts/raw sessions | `docs/stage2/AI_SESSION_INDEX.md` | This Arena session is indexed, but the complete human export is absent. |

## Evidence that does not yet exist

There is no valid 500-record state, 200-email state, scheduler-active screenshot, pair of scheduled cycles spanning 48 hours, naturally encountered running dependency failure, later-cycle evidence-based trust transition, production refresh cost/latency sample, sent Day-2 email, complete Arena export, or personal final-review record. These cannot be replaced by code, tests, templates, local runs, candidates, or predictions.
