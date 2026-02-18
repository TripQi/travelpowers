# Workflow Health Check

`workflow_health_check.py` is a validator for the travelpowers workflow:

- `brainstorming -> writing-plans -> compile-plans -> executing-plan-issues`

It validates skills contracts, plan structure, issues JSONL schema, dependency graphs,
and workflow state coherence with low-false-positive defaults.

## Key Design Choices

- Automatic gates use `--fail-on error` (warnings are non-blocking by default)
- `full` mode checks plan+issues by default; skills check is opt-in via `--include-skills`
- `full` mode can be strict with `--require-plan --require-issues`
- Missing/incomplete `meta.execution_context` uses fallback (`project-root` + current branch), non-blocking by default
- Skills contracts are marker-based (`<!-- workflow-contract:... -->`) to reduce wording-coupled false positives
- Built-in anti-loop usage policy: max 2 attempts per gate in SKILL workflows

## Quick Start

From project root:

```bash
python workflow-health-check/workflow_health_check.py --mode full --project-root .
```

Run specific checks:

```bash
python workflow-health-check/workflow_health_check.py --mode skills --skills-root . --fail-on error
python workflow-health-check/workflow_health_check.py --mode plan --project-root . --plan docs/plans/2026-02-16-my-feature.md --fail-on error
python workflow-health-check/workflow_health_check.py --mode issues --project-root . --issues docs/issues/2026-02-16_10-30-00-my-feature.jsonl --fail-on error
```

Strict warnings (optional, usually for CI hard mode):

```bash
python workflow-health-check/workflow_health_check.py --mode full --project-root . --fail-on warning
```

## Recommended Usage Checklist

1. After changing workflow skills (`SKILL.md` files):
   - `--mode skills --skills-root <travelpowers-root> --fail-on error`
2. After generating plan markdown:
   - `--mode plan --project-root . --plan <plan.md> --fail-on error`
3. After compile-plans outputs snapshot:
   - `--mode issues --project-root . --issues <snapshot.jsonl> --fail-on error`
4. Before final handoff/release:
   - `--mode full --project-root . --plan <plan.md> --issues <snapshot.jsonl> --require-plan --require-issues --fail-on error`

## What It Validates

### Skills

- Required workflow contract markers exist across core skills
- Marker checks are text-wording agnostic (contract-first, not prose-regex-first)
- Health-gate integration points are explicitly tagged

### Plan Markdown

- Header fields: Goal / Architecture / Tech Stack / Execution Context
- `### Task N:` sections exist
- Required task fields exist
- `Depends On` references are valid and acyclic

### Issues JSONL

- First line is valid `meta`
- Required meta and issue fields exist
- Enum values are valid (`dev_state`, `review_*`, `git_state`, `blocked`)
- `depends_on` references valid issue IDs and has no cycle
- `refs` format is valid (`path:start` or `path:start-end`)
- State coherence checks (for example, committed issue cannot be blocked)

## Exit Codes

- `0`: pass for configured threshold
- `1`: validation error exists
- `2`: warning threshold failure (when `--fail-on warning`)
- `3`: unexpected checker runtime failure

## Checker Self-tests

Run checker unit tests:

```bash
python -m unittest discover -s workflow-health-check/tests -p "test_*.py"
```
