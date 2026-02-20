---
name: workflow-health-check
description: Run automated health gates for the travelpowers workflow (`skills`, `plan`, `issues`, `full`) with low-false-positive defaults and anti-loop controls.
argument-hint: "--mode <skills|plan|issues|full> [--plan <path>] [--issues <path>]"
---

# Workflow Health Check

Use this skill to validate workflow integrity via:

`workflow-health-check/workflow_health_check.py`

This is a verification utility skill. It is called automatically by other workflow skills at mandatory gates.

## Checker Path Resolution Protocol (Mandatory)
<!-- workflow-contract:workflow-health-check.path_resolution_protocol -->

When another skill needs to run health checks, resolve `<checker_path>` in this order:

1. `TRAVELPOWERS_HEALTH_CHECK` env var (if points to an existing file)
2. `${CODEX_HOME}/skills/travelpowers/workflow-health-check/workflow_health_check.py` (if `CODEX_HOME` is set)
3. `~/.codex/skills/travelpowers/workflow-health-check/workflow_health_check.py`
4. `workflow-health-check/workflow_health_check.py`
5. `../workflow-health-check/workflow_health_check.py`

If no path is found:
- Do not retry in a loop
- Mark `health_gate:degraded(unavailable)` in notes/handoff
- Switch to manual checklist for that phase

## Command Templates

From project root, run one of:

```bash
python <checker_path> --mode skills --skills-root <travelpowers-root> --fail-on error
python <checker_path> --mode plan --project-root . --plan <plan-path> --fail-on error
python <checker_path> --mode issues --project-root . --issues <issues-jsonl-path> --fail-on error
python <checker_path> --mode full --project-root . --plan <plan-path> --issues <issues-jsonl-path> --require-plan --require-issues --fail-on error
```

## Pass/Fail Policy

- Exit code `0`: pass
- Exit code `1`: validation error exists
- Exit code `2`: warning threshold failure (only when `--fail-on warning`)
- Exit code `3`: checker runtime failure

For automatic gates, use `--fail-on error` to reduce false positives.

## Execution Context Fallback Policy

For `issues` checks, if `meta.execution_context` is missing/incomplete/non-object:

- Do not fail the gate by default
- Fallback context is assumed as:
  - `worktree_path = --project-root`
  - `branch = current git branch` (or `unknown` when unavailable)
  - `base_branch = branch`
- Emit INFO messages for traceability

## Anti-loop Policy
<!-- workflow-contract:workflow-health-check.anti_loop_policy -->

- Maximum 2 attempts per gate (initial run + 1 retry after fixes)
- If the same failure repeats on attempt 2, stop automatic retries
- Escalate with concise failure summary and next-step options
- Never use unbounded "re-run until pass" loops

## Integration Contract
<!-- workflow-contract:workflow-health-check.integration_contract -->

- `planning`: run `--mode plan` before committing plan doc
- `compile-plans`: run `--mode issues` before committing snapshot
- `executing-plan-issues`:
  - Phase 1: run `--mode issues`
  - After each issue commit: run `--mode issues`
  - Final convergence: run `--mode full --require-plan --require-issues`
