# Manual workflow installation required

## Why this is separate

The Arena GitHub App authenticated successfully but GitHub rejected every push containing `.github/workflows/*` because the App lacks workflow-file permission. Jan confirmed on 11 Aug 2026 that this permission cannot be enabled. To allow the application code to be pushed, workflow changes are preserved as inert `.example` files rather than pretending the scheduler is installed.

This is a human/platform blocker. Until the files below are installed on `main`, there is no Stage 2 schedule, no scheduler-owned history, and no basis for the 48-hour operating claim.

## Install through the GitHub web interface

Using Jan's normal GitHub account—not a credential pasted into Arena:

1. Merge the Stage 2 pull request if repository policy permits. Existing Stage 1 checks may fail because they expect the legacy 20+ row schema; do not describe those checks as Stage 2 validation.
2. In the repository web interface, replace these files using the exact template contents:
   - `docs/stage2/workflow_templates/lint-and-import.yml.example` → `.github/workflows/lint-and-import.yml`
   - `docs/stage2/workflow_templates/dataset-integrity.yml.example` → `.github/workflows/dataset-integrity.yml`
3. Create `.github/workflows/stage2-refresh.yml` from `docs/stage2/workflow_templates/stage2-refresh.yml.example`.
4. Commit the web edits to `main`. No Groq secret is needed for the scheduled data pipeline.
5. Open **Actions → Stage 2 Unattended Refresh → Run workflow** once. Confirm that the run page shows `workflow_dispatch`, a run ID, logs, and committed operating artifacts.
6. Leave the 12-hour schedule enabled. Preserve a screenshot of the Actions run list and each qualifying run detail page.

## Required verification before making scheduler claims

```bash
python -m pytest -q
python -m stage2.release --reconcile-only
```

Then verify in GitHub—not only in the committed files—that:

- at least two `schedule`-owned runs are genuinely separate and span at least 48 hours;
- raw `data/stage2/operating_logs/*.jsonl` files name GitHub run IDs and `scheduler_owned: true`;
- a running dependency failure has bounded retry/recovery/escalation evidence;
- a later run produces an evidence-based trust event against a record processed earlier; and
- current CSV, JSONL, canonical state, UI totals, source mix, release ID, and checksums reconcile.

A manual dispatch can prove deployment but does not become a scheduled cycle by changing its label. If Jan cannot perform this installation, the final submission must state that the schedule and all dependent evidence are incomplete.
