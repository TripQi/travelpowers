---
name: executing-plan-issues
description: "Execute the closed-loop development workflow driven by an issues JSONL file: implement -> review -> self-verify -> git commit, issue by issue, without manual intervention."
argument-hint: "<path to issues JSONL file>"
---

You are now in "Issues JSONL Execution Mode (Closed-Loop)".

Goal: Use a `docs/issues/*.jsonl` file as the single source of truth for task boundaries and workflow state. Drive each issue through the full closed loop: **implement -> review -> self-verify -> git commit** (no push). Process all issues autonomously, stopping only when all are complete or all remaining issues are non-executable (blocked or dependency-blocked).

> This skill activates only when explicitly invoked. It does not affect normal conversation.

## 1. General Rules (Must Follow)

1. **JSONL is the boundary and state source.** Only do work described by the issue line. Any scope change must be written back to JSONL before changing code.
2. **Default: complete all issues (order is your call).** You decide execution order (prefer high-value, unblocking, context-switch-minimizing), but the goal is to push every issue to closed-loop complete. Record `picked_reason:<why>` in the issue's `notes` field each time you pick one.
3. **Closed loop is non-negotiable.** Implementation + doc sync + review + self-verify + git commit - all required. No shortcuts.
4. **Status-driven.** Only use these values:
   - `dev_state`: `pending` | `in_progress` | `done`
   - `review_state`: `pending` | `in_progress` | `done`
   - `git_state`: `uncommitted` | `committed`
   <!-- workflow-contract:executing-plan-issues.schema.blocked -->
   - `blocked`: `false` | `true`
5. **Track progress with `update_plan`.** Multi-step tasks (>=2 steps) must use the `update_plan` tool to advance `pending -> in_progress -> completed`. Do not enter plan mode or create plan files - use JSONL status as the fine-grained progress source.
6. **KISS / YAGNI.** No unrelated refactoring. No new architecture. Fix root causes. Maintain backward compatibility.
7. **No fabricated results; limited acceptance allowed.**
   - Run real tests whenever possible. Prefer actual test output as evidence.
   - If tests cannot run due to environment, permissions, or dependencies: continue with delivery, but `notes` must include: `validation_limited:<reason>`; `manual_test:<command or steps to run later>`; `evidence:<alternative verification done>`; `risk:<low|medium|high> <explanation>`.
   - Under limited acceptance, never claim "tests passed". Handoff output must explicitly state what was not tested and why.

**Supplementary rules (tooling / safety):**

- **Shell and filesystem:** Read more than you write. Avoid destructive commands (`rm -rf`, force overwrite) unless explicitly authorized. Large-scope operations: test on small scope first.
- **Security and compliance:** Do not access or leak secrets, tokens, private keys, or personal data. For potentially destructive changes, state the impact scope before executing.
- **Single workflow state source:** The passed JSONL file is the only workflow state store. Code/docs/tests are normal work targets, but do not create additional issues snapshots unless explicitly requested.
- **Health checker path resolution:** Always resolve `<checker_path>` via `workflow-health-check/SKILL.md` protocol; never assume a fixed relative path.
- **No unauthorized snapshots:** Do not create `docs/issues/issues.jsonl` or any other summary/snapshot JSONL unless the user explicitly requests it.

## 2. Workflow (6-Phase Execution)

Every issue must progress through these phases in order. Each phase must use tools to actually modify files and verify - never "imagine" completion.

### Core Loop (Quick Reference, Mandatory)

Use this as the minimal execution skeleton to avoid phase omissions:

1. Phase 1: validate JSONL + run `issues` health gate (once per execution run).
2. Phase 2: pick one eligible issue + output summary + record `picked_reason`.
3. Phase 3: set `in_progress`, collect context, implement, test, verify (autonomous — one phase, your rhythm).
4. Phase 4: review against `review_requirements` + commit + health gate + update JSONL.
5. Phase 5: loop back to Phase 2, or proceed to Phase 6 if done/stuck.
6. Phase 6: cross-issue regression + full health gate.

If this quick reference conflicts with later details, follow the later phase details.

### Phase 1: Init (Read JSONL + Validate Schema)

Run this phase **once per execution run**, not per issue.

- Verify the file contains one valid meta line and issue lines matching compile-plans schema.
- Validate every issue has: `depends_on` (array), `blocked` (boolean), status fields, non-empty `refs`.
- Validate dependency integrity: every `depends_on` id exists, no self-dependency, no cycle.
- **Automated health gate (mandatory):** resolve `<checker_path>` and run `python <checker_path> --mode issues --project-root . --issues <jsonl-path> --fail-on error`.
- Anti-loop policy: max 2 attempts (initial + 1 retry after fixes).
- If checker is unavailable/runtime-failed: do not loop; mark `validation_limited:health_gate_unavailable` in notes and continue with manual schema checklist.
- If attempt 2 still fails with validation errors: stop and tell the user to regenerate/fix via compile-plans before execution.

### Phase 2: Pick Target Issue + Output Summary

**Eligibility rule (must pass before picking):**

- `blocked == false`
- All `depends_on` issues are already closed-loop complete
- Issue itself is not already closed-loop complete

**Picking rules (order is your call, but must be explainable):**

1. **First, converge half-finished work:** among eligible issues, pick one with `git_state=uncommitted` and (`dev_state=in_progress` or `dev_state=done`) first.
2. **Then pick deliverables:** among remaining eligible issues, choose autonomously. Suggested heuristics: P0 -> P1 -> P2; prefer tasks that unblock others; minimize context switches.
3. **Record reason:** write `picked_reason:<1 sentence>` into `notes`.

If no issue is eligible, go to Phase 5 stop-condition logic.

**Output summary:** `id` / `title` / `description` / `acceptance_criteria` / `test_approach` / `depends_on` / `refs` (concise).

### Phase 3: Execute (Autonomous Implementation)

You have full autonomy in this phase. The goal is to make `acceptance_criteria` pass. How you get there is your decision.

**On entry:** Set `dev_state` -> `in_progress`, `review_state` -> `in_progress`. Save JSONL.

**Guidelines (not rigid steps):**
- Start from `refs` to understand context. Read as much as needed — no artificial tool call budget.
- Implement the change. You decide the rhythm: TDD, code-first, whatever works.
- Run tests during implementation, not just at the end.
- Fix failures before advancing.
- Keep changes within the issue boundary (`description` + `acceptance_criteria`).
- Update docs, comments, and `refs` directly related to this issue.

**Quality gates (shifted left):**
- Single responsibility, nesting depth <= 3
- No obvious O(N^2), unbounded caches, or missing timeouts
- `git diff` before commit to verify change boundary — no unrelated formatting or renames

**Self-verify:** Provide pass/fail **evidence** for each acceptance criterion. Run test commands from `test_approach`. If tests cannot run, follow limited acceptance (Section 1, rule 7).

**When done:** set `dev_state` → `done`, proceed to Phase 4.

### Phase 4: Review & Commit

1. **Review:** Check against `review_requirements` point by point. Set `review_state` -> `done`.
   - If review cannot fully run in the current environment: follow limited acceptance. Still set `review_state` -> `done`, but do not claim tests passed.

2. **Finalize status:** Set `dev_state` -> `done`. Keep `git_state` as `uncommitted` until commit succeeds. Append `done_at:<date>` and acceptance evidence summary to `notes`. Save JSONL.

3. **Git commit:**
   - `git status` / `git diff` to confirm changes only cover this issue. Remove unrelated changes.
   - `git add` must include: code changes + JSONL (same issue commit).
   - Commit granularity: one issue = one commit.
   - Commit message format: `[<id>] <title>` (add brief explanation if needed).

4. **Per-issue automated health gate (mandatory, before amend):** resolve `<checker_path>` and run `python <checker_path> --mode issues --project-root . --issues <jsonl-path> --fail-on error`.
   <!-- workflow-contract:executing-plan-issues.health_gate.per_issue_pre_amend -->
   - Anti-loop policy: max 2 attempts.
   <!-- workflow-contract:executing-plan-issues.health_gate.anti_loop -->
   - If checker unavailable/runtime-failed: record `validation_limited:health_gate_unavailable` and continue to amend step.
   - If attempt 2 still fails with validation errors:
     - stop automatic retries and do not amend
     - keep `git_state=uncommitted`
     - set `blocked=true`
     - append `blocked:health_gate_failed(attempt=2)` + concise reason in `notes`
     - write JSONL and stop this run (escalate to user); do not loop

5. **Amend JSONL into commit:** After health gate pass/degraded:
   - set `git_state` -> `committed`
   - append `commit:<hash>` in `notes`
   - run `git add <jsonl> && git commit --amend --no-edit` so code + final state stay in one issue commit

6. **Commit failure handling:** If commit/amend fails:
   - keep `git_state` as `uncommitted`
   - set `blocked` -> `true`
   - record `blocked:git commit failed <reason>` in `notes`
   - stop (do not continue to next issue)

7. **Handoff (per issue, concise):**
   - Issue `id` / `title` processed.
   - If multiple issues processed this round: completed count / remaining count / blocked ids (if any).
   - Key changes with file references (`path:line`).
   - Actual tests run and results.
   - If limited acceptance: untested items, reasons, and `manual_test` commands.
   - Local commit hash (if committed).
   - Risks and follow-up suggestions (if any).

### Phase 5: Loop and Stop Conditions

After finishing one issue, return to Phase 2 until one condition is met:

- **All issues reach closed-loop complete** -> go to Phase 6 global convergence.
- **No eligible issue exists**:
  - if unresolved issues are all `blocked=true`, stop and report blocking list with minimum decision info
  - if unresolved issues are only dependency-blocked, report which upstream issue(s) are missing
  - if dependency cycle is detected late, stop and report cycle

### Phase 6: Final Gate (Global Convergence)

When all issues are closed-loop complete:

- Run a final cross-issue regression pass (reuse existing project test commands; prioritize integration paths affected by multiple issues).
- Run workflow full health gate: `python <checker_path> --mode full --project-root . --plan <meta.source> --issues <jsonl-path> --require-plan --require-issues --fail-on error`.
  <!-- workflow-contract:executing-plan-issues.health_gate.full_convergence -->
- Anti-loop policy: max 2 attempts. If checker unavailable/runtime-failed, record `health_gate:degraded(unavailable)` and switch to manual convergence checklist.
- Only if the full health gate passes (or degraded path is explicitly recorded), summarize final delivery: total completed, any limited acceptance cases, residual risks, and suggested follow-up.
- Do not create a new issues snapshot file unless the user explicitly requests it.

## 3. Closed-Loop Completion Definition

An issue is closed-loop complete only when ALL of the following are true:

- `dev_state` = `done`
- `review_state` = `done`
- `git_state` = `committed`
- `blocked` = `false`

If limited acceptance was used: `review_state` may be `done`, but `notes` must contain `validation_limited:` and `manual_test:`.

## 4. Failure and Blocking (Must Be Recorded)

When any of the following occurs, first try to resolve autonomously. If truly unresolvable in the current context, follow the record-and-skip protocol:

- Acceptance criteria are unclear
- `refs` targets not found / code location failed
- Tests fail and cannot be fixed in current context
- Required changes exceed this issue's `description` boundary

**Note:** "Tests cannot run" != blocked. If implementation is complete and risk is manageable, prefer limited acceptance (record in `notes`) and commit. Only treat as blocked when skipping tests would carry high risk (data migration, permissions, payments, deletions, large-scale refactoring).

**Recording protocol:**

1. Set `blocked` -> `true`, and write `blocked:<reason>` + investigation done + next-step suggestions into `notes`.
2. Keep `dev_state` / `review_state` at true progress (usually `in_progress`). `git_state` must remain `uncommitted`.
3. **Continue strategy:**
   - if other eligible issues remain, skip to the next issue
   - if no eligible issues remain, stop and report blocking/dependency constraints in 1-3 sentences

## 5. JSONL Update Protocol (Atomic Write)

To update a single issue in-place using atomic write:

1. Read all lines of the JSONL file into memory.
2. Find the line with the matching `id`.
3. Parse it as JSON, update target fields.
4. Serialize back to a single-line JSON string.
5. Write all lines to a **temporary file** (`<original>.tmp`) — preserve line order.
6. **Validate** the temporary file: every line must be valid JSON, line count must match the original.
7. If the original file exists, create a **backup** (`<original>.bak`) by copying it.
8. **Atomic rename:** use `os.replace("<original>.tmp", "<original>")` to atomically replace the original file.
9. On success, the `.bak` file may be kept for one cycle (overwritten on next update) or deleted.

**Never reorder lines.** Line order is the canonical execution priority order set by compile-plans.

### Recovery Protocol

If the process crashes mid-write:

- **`.tmp` exists, original exists:** The write was interrupted before rename. Discard `.tmp` and use the original (last known good state).
- **`.tmp` exists, original missing:** The rename may have partially failed. Validate `.tmp` — if valid, rename it to the original filename. If invalid, check for `.bak` and restore from backup.
- **`.bak` exists, original missing:** Restore from `.bak`.

### Cross-Platform Note

`os.replace()` is atomic on POSIX (single filesystem). On Windows (NTFS), it is also atomic for same-volume renames. Always ensure `.tmp` and the target are on the same filesystem/volume.

## 5a. Mid-Execution Issue Append Protocol

During execution, a **small number** of new issues may be appended to the active JSONL without returning to compile-plans, provided all eligibility conditions are met.

### Eligibility (all 4 must be true)

1. The new issue is a **direct consequence** of work on an existing issue (e.g., discovered edge case, required follow-up fix).
2. It affects **at most 1 file** not already in the JSONL's existing issue set.
3. It is estimated at **≤ 30 lines of code change**.
4. The user has explicitly approved the append (or the issue is blocked and cannot proceed without the new work).

### Append Protocol (7 steps)

1. **Identify the parent issue** — the existing issue whose execution revealed the need.
2. **Draft the new issue** — follow the same schema as compile-plans (all 17 required fields).
3. **Assign ID** — use the next available ID in the existing prefix sequence (e.g., if last is `AUTH-030`, use `AUTH-035` or `AUTH-040`).
4. **Set `notes`** — include: `origin:mid_execution_append; reason:<why>; parent_issue:<id>`.
5. **Update `meta.total_issues`** — increment by the number of appended issues.
6. **Append the new issue line(s)** at the end of the JSONL file (after all existing issue lines).
7. **Run the `issues` health gate** to validate the updated JSONL.

### Limits

- **Maximum 2 appended issues** per execution run. If more are needed, stop execution and return to compile-plans for a proper re-planning cycle.
- Appended issues must not introduce new dependency cycles.
- Appended issues should reference the parent issue in `depends_on` if there is a logical dependency.

## 6. Pre-Commit Self-Check

**Closed-loop must-pass:**

- Acceptance criteria have reproducible evidence (test output / reproduction steps / screenshot path).
- If limited acceptance: `notes` contains `validation_limited` / `manual_test` / `evidence` / `risk`, and handoff states what was not tested.
- `review_state` is advanced as required.
- JSONL and code are committed together for the issue (`git add` covers both; final `git_state` is `committed`).
- Documentation / comments / refs are synced with implementation (minimal but accurate).
- Commit message starts with `[<id>] <title>` and contains no unrelated changes.

**Self-reflection quality check:**

- Maintainability (readable, locatable, easy to revert)
- Test coverage (key tests added/updated, or `notes` explains why not)
- Performance (no obvious regressions; minimal measurement/comparison added if needed)
- Security (no leaked secrets; input validation / permission boundaries not degraded)
- Code style (follows project conventions; no unrelated formatting/renames)
- Documentation (consistent with behavior; acceptance criteria / usage / limitations are clear)
- Backward compatibility (existing API/CLI/data formats not broken; compatibility strategy documented if needed)

**Process self-check:**

- Init phase validated JSONL before any code was touched.
- Dependency eligibility was enforced before picking each issue.
- Per-issue `issues` health gate result was recorded (`passed` or explicit `degraded`).
- Handoff output includes `path:line` references, risks, and follow-up steps.
- Final global convergence and `full` health gate were both run (or explicitly marked as degraded with reason).
- No health gate used unbounded retry loops.

## 7. Rollback and Recovery

When execution hits an unrecoverable problem or requirements change mid-flight, use one of the following rollback protocols. **General principles:** preserve history (`git revert`, not `git reset --hard`); archive rather than delete; require human judgment for rollback decisions; only roll back one stage at a time.

### 7.1 Reopen a Completed Issue

Use when a committed issue is discovered to be incorrect or incomplete after its closed-loop was finalized.

1. `git revert <commit-hash>` — create a revert commit that undoes the issue's changes.
2. In the JSONL, reset the issue's status fields:
   - `dev_state` → `pending`
   - `review_state` → `pending`
   - `git_state` → `uncommitted`
   - `blocked` → `false`
3. Append to `notes`: `reopened:<date>; reason:<why>; revert_commit:<hash>`.
4. Write JSONL using the atomic write protocol (Section 5).
5. Re-enter the execution loop — the reopened issue is now eligible again.

### 7.2 Roll Back from Execution to Planning

Use when execution reveals that the plan itself is flawed (wrong task decomposition, missing tasks, incorrect dependencies).

1. Archive the current JSONL: rename `<filename>.jsonl` → `<filename>.archived.jsonl`.
2. If the meta line has an `archived` field, set `"archived": true`. Otherwise, add it.
3. Commit the archive rename.
4. Return to the `planning` skill to revise the plan, then re-run `compile-plans` to generate a fresh JSONL.

### 7.3 Roll Back from Planning to Design

Use when planning reveals that the design itself needs fundamental rethinking.

1. Archive the current plan: rename `<filename>.md` → `<filename>.archived.md` in `docs/plans/`.
2. Commit the archive rename.
3. Return to the `designing` skill to revise the design.

### Rollback Constraints

- **One stage at a time:** Do not jump from execution directly to designing. Go execution → planning → design if needed.
- **Human approval required:** All rollback actions require explicit user approval before execution.
- **Archived files are permanent records:** Never delete `.archived.*` files. They serve as audit trail.
