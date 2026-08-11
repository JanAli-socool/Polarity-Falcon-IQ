# Falcon FO — evidence-led family-office research

[![Lint and import](https://github.com/JanAli-socool/falcon-fo/actions/workflows/lint-and-import.yml/badge.svg)](https://github.com/JanAli-socool/falcon-fo/actions/workflows/lint-and-import.yml)
[![Dataset integrity](https://github.com/JanAli-socool/falcon-fo/actions/workflows/dataset-integrity.yml/badge.svg)](https://github.com/JanAli-socool/falcon-fo/actions/workflows/dataset-integrity.yml)

A free-tier pipeline and buyer workspace for finding family-office decision-makers without guessed contact data or unsupported fit claims. This repository is the source of truth for the Falcon Scaling / PolarityIQ Stage 2 assessment.

> **Current release truth (11 Aug 2026):** 0 qualifying records and 0 qualifying person-owned emails. The 26 Stage 1 rows are quarantined under the stricter policy; they are not counted. The release is not ready and the repository does not claim otherwise.

## Buyer capabilities

- **Evidence search:** exact filters, lexical evidence terms, denominator-scoped counts, source/route/country aggregates, and compound natural-language decomposition.
- **Research agent:** Groq plans only allowlisted read calls; deterministic tools execute them; complete raw traces preserve requests, responses, retries, calls, results, refusals, and render decisions.
- **Healthcare LP comparison:** four explicit evidence signals with visible missing-mandate limitations. Missing LP appetite is never inferred.
- **Trust and operations:** current release gate, source mix, quarantine totals, freshness state, checksums, and scheduler-owned cycle history.

Every read re-evaluates policy before filtering. Every agent output is replayed through deterministic tools before rendering, preventing a modified person, title, firm, route, aggregate, or citation from reaching the buyer.

## Quick start

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt

# Verify all Stage 2 controls and release reconciliation
python -m pytest -q tests/stage2
python -m stage2.release --reconcile-only

# Run the buyer workspace
streamlit run app/main.py
```

The app works in deterministic search mode without a model key. To enable model planning, set `GROQ_API_KEY` in the environment or Streamlit secret controls. Never commit the key. `GROQ_MODEL` is optional.

## Pipeline operation

```bash
# Show command options
python -m stage2.pipeline --help

# Execute and preserve all three required goal packets
python scripts/run_stage2_goals.py
# Explicitly test deterministic fallback
python scripts/run_stage2_goals.py --no-model
```

The intended 12-hour scheduled job is preserved at `docs/stage2/workflow_templates/stage2-refresh.yml.example`, but it is **not installed** under `.github/workflows/`: the connected GitHub App cannot push workflow changes, and the user confirmed that permission cannot be enabled. [Manual installation steps](docs/stage2/04_MANUAL_WORKFLOW_SETUP.md) are explicit. Once installed, each run produces append-only operating events, a signed summary, durable candidates/observations/canonical state, and synchronized final representations. Replenishment targets a 550-record/220-email buffer; publication is blocked until at least 500 records and 200 qualifying emails exist.

## Canonical data and outputs

| Path | Purpose |
|---|---|
| `data/stage2/state/records.jsonl` | Sole canonical publish-state input |
| `data/stage2/state/candidates.jsonl` | Durable discovery candidates; never production by itself |
| `data/stage2/quarantine/` | Failed, unresolved, and legacy records excluded from counts |
| `data/final/release_manifest.json` | Recomputable counts, checksums, source mix, and readiness |
| `data/final/family_office_contacts.{csv,jsonl}` | Generated buyer representations |
| `data/stage2/operating_logs/` | Uncurated scheduled-cycle events and summaries |
| `data/stage2/goal_outputs/` | Exact goals, manual retrieval, structured agent output, raw trace |
| `docs/stage2/` | Acceptance map, architecture, decisions, time/provenance gaps, submission status |

## Documentation

- [Architecture and operations](docs/stage2/02_ARCHITECTURE_AND_OPERATIONS.md)
- [Requirements and acceptance map](docs/stage2/00_REQUIREMENTS_AND_ACCEPTANCE.md)
- [Engineering decisions](docs/stage2/01_ENGINEERING_DECISIONS.md)
- [Human-owned actions and evidence gaps](docs/stage2/HUMAN_ACTIONS.md)
- [AI session index](docs/stage2/AI_SESSION_INDEX.md)

The existing Streamlit deployment is expected to remain at <https://falcon-fo-3gsnwrplstwjvdw4sp7vpg.streamlit.app/> after the branch is merged and the service redeploys. Until then, repository state—not the old deployed Stage 1 interface—is authoritative.
