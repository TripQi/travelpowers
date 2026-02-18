---
name: travelpowers-workflow-status
description: "Scan project artifacts to report current workflow stage and route to the correct downstream skill. Use when resuming a session or checking progress."
argument-hint: "(no arguments)"
---

# Workflow Status

## Overview

Scan project artifacts (`docs/issues/`, `docs/plans/`, `docs/designs/`) to determine the current workflow stage. Report progress and automatically route to the correct downstream skill.

**Announce at start:** "I'm using the travelpowers-workflow-status skill to check the current workflow progress."

## Constraints

- **Read-only:** Do not create, modify, or delete any files.
- **Latest-first:** When multiple artifacts of the same type exist, use the latest one (sorted by filename descending).
- **Freshness guard:** Never declare "Workflow complete" if a newer plan artifact exists and has not been compiled into the active issues snapshot.
- **Auto-route:** After reporting status, automatically invoke the next skill (unless workflow is complete or a safety-stop condition is hit).
- **No route on complete:** If all issues are closed-loop complete, only report — do not invoke any skill.
- **Safety-stop on invalid latest snapshot:** If the latest JSONL is present but invalid, report the error and stop routing. Do **not** silently fall back to older JSONL files.

## Detection Logic (Reverse Order)

Determine the workflow stage by checking artifacts from latest to earliest phase. **Stage determination** stops at the first match; **artifact scanning** always checks all three directories so the status report can show every found artifact.

### Step 1: Check `docs/issues/*.jsonl`

If one or more `.jsonl` files exist in `docs/issues/`:

1. Select the **latest** file (sort filenames descending) and treat it as the active snapshot candidate.
2. Read the file and validate it strictly:
   - First line parses as JSON object and is workflow `meta`.
   - There is at least one issue line after meta.
   - Every issue line includes required workflow status fields: `dev_state`, `review_initial_state`, `review_regression_state`, `git_state`, `blocked`.
3. **Error handling (latest snapshot):** if the latest file is invalid (empty, invalid JSON, missing/invalid meta line, no issue rows, or issue rows missing required status fields), **stop routing** and report the snapshot as invalid. Do not auto-fallback to older JSONL.
4. Classify each issue by closed-loop status. **Evaluate in this exact order — first match wins:**

   | Priority | Category | Condition |
   |----------|----------|-----------|
   | 1 | **complete** | `dev_state=done` AND `review_initial_state=done` AND `review_regression_state=done` AND `git_state=committed` AND `blocked=false` |
   | 2 | **blocked** | `blocked=true` |
   | 3 | **in_progress** | `dev_state=in_progress` OR (`dev_state=done` AND `git_state=uncommitted`) |
   | 4 | **pending** | Everything else |

5. Apply freshness guard before deciding completion:
   - Resolve linked plan from `meta.source` (if valid and exists).
   - Also find the latest plan in `docs/plans/*.md` (if any).
   - If linked plan is missing **or** a newer plan exists than the linked plan (filename-descending order; tie-breaker by file mtime), route to `compile-plans <latest-plan-path>` instead of declaring completion.
6. If all issues are `complete` and freshness guard is clear → report "Workflow complete", do **not** route.
7. If any issues are not `complete` → route to `executing-plan-issues <jsonl-path>`.

### Artifact Tracing (via JSONL meta)

When a JSONL is found, resolve the related plan and design through the artifact chain — **do not independently pick the latest of each type**:

1. **Plan:** read `meta.source` from the JSONL (e.g. `"source":"docs/plans/2026-02-16-auth.md"`). If the file exists, use it. If missing or `meta.source` is absent, show `(none)`.
2. **Design:** scan `docs/designs/*.md` for files whose name-slug matches the plan filename slug (e.g. plan `2026-02-16-auth.md` → design `2026-02-16-auth-design.md`). If no match, show `(none)`.

This ensures the three artifacts displayed in the report belong to the same feature.

### Step 2: Check `docs/plans/*.md`

If one or more `.md` files exist in `docs/plans/` and **no JSONL file exists** in Step 1:

1. Select the **latest** plan file (sort filenames descending).
2. Similarly trace design: look for a matching design file by slug in `docs/designs/`.
3. Route to `compile-plans <plan-path>`.

### Step 3: Check `docs/designs/*.md`

If one or more `.md` files exist in `docs/designs/` but **no** plan was found in Step 2:

1. Select the **latest** design file (sort filenames descending).
2. Read the design doc and look for the **Execution Handoff** block (containing `worktree_path`, `branch`, `base_branch`). If found, include it in the routing context.
3. Route to `writing-plans`, passing the design path and handoff context (if available) in the invocation message. Example: "Resuming from design doc `<path>`. Handoff context: worktree=`<path>`, branch=`<name>`, base=`<name>`."

### Step 4: Nothing found

If none of the above directories contain relevant artifacts:

1. Route to `brainstorming`.

## Output Format

```
== Travelpowers Workflow Status ==

Artifacts:
  design : <path or "(none)">
  plan   : <path or "(none)">
  issues : <path or "(none)">

Progress: <N>/<total> complete | <N> in_progress | <N> blocked | <N> pending

Alert: <message>    # optional, only for safety-stop/degraded cases

Next: <skill-name> <arguments>
```

When no JSONL exists, omit the `Progress:` line.
When safety-stop is triggered (invalid latest snapshot), output `Next: (manual) <action>`.

### Examples

**Active execution (has JSONL with mixed status):**

```
== Travelpowers Workflow Status ==

Artifacts:
  design : docs/designs/2026-02-16-auth-design.md
  plan   : docs/plans/2026-02-16-auth.md
  issues : docs/issues/2026-02-16_10-30-00-auth.jsonl

Progress: 2/5 complete | 1 in_progress | 0 blocked | 2 pending

Next: executing-plan-issues docs/issues/2026-02-16_10-30-00-auth.jsonl
```

**All complete:**

```
== Travelpowers Workflow Status ==

Artifacts:
  design : docs/designs/2026-02-16-auth-design.md
  plan   : docs/plans/2026-02-16-auth.md
  issues : docs/issues/2026-02-16_10-30-00-auth.jsonl

Progress: 5/5 complete | 0 in_progress | 0 blocked | 0 pending

Workflow complete. All issues are closed-loop done.
```

**Latest JSONL invalid (safety-stop):**

```
== Travelpowers Workflow Status ==

Artifacts:
  design : (none)
  plan   : docs/plans/2026-02-16-auth.md
  issues : docs/issues/2026-02-16_10-30-00-auth.jsonl

Alert: latest issues snapshot is invalid (no issue rows after meta); auto-routing stopped

Next: (manual) fix JSONL or regenerate via compile-plans docs/plans/2026-02-16-auth.md
```

**Issues complete but newer plan exists:**

```
== Travelpowers Workflow Status ==

Artifacts:
  design : docs/designs/2026-02-17-billing-design.md
  plan   : docs/plans/2026-02-17-billing.md
  issues : docs/issues/2026-02-16_10-30-00-auth.jsonl

Progress: 5/5 complete | 0 in_progress | 0 blocked | 0 pending

Next: compile-plans docs/plans/2026-02-17-billing.md
```

**Only plan exists:**

```
== Travelpowers Workflow Status ==

Artifacts:
  design : docs/designs/2026-02-16-auth-design.md
  plan   : docs/plans/2026-02-16-auth.md
  issues : (none)

Next: compile-plans docs/plans/2026-02-16-auth.md
```

**Only design exists (with handoff context):**

```
== Travelpowers Workflow Status ==

Artifacts:
  design : docs/designs/2026-02-16-auth-design.md
  plan   : (none)
  issues : (none)

Next: writing-plans (design: docs/designs/2026-02-16-auth-design.md, worktree: /repo-auth, branch: feature/auth)
```

**Empty project:**

```
== Travelpowers Workflow Status ==

Artifacts:
  design : (none)
  plan   : (none)
  issues : (none)

Next: brainstorming
```

## Execution Steps

1. **Scan artifacts** — use `Glob` to check each directory:
   - `docs/issues/*.jsonl`
   - `docs/plans/*.md`
   - `docs/designs/*.md`
2. **Determine stage** — follow the 4-step detection logic above (stage determination stops at first match).
3. **Validate latest JSONL strictly** — if invalid, safety-stop and emit manual next action; do not fallback automatically.
4. **Trace artifact chain** — resolve related artifacts through `meta.source` or filename slug matching, not by independently picking the latest of each type.
5. **If valid JSONL found** — classify each issue (using priority-ordered rules), compute counts, then run freshness guard before deciding completion.
6. **Print status report** — using the output format above.
7. **Route** — invoke the downstream skill directly in the same turn (unless workflow is complete or safety-stop is active). When routing to `writing-plans`, include the design path and any handoff context found in the design doc.
