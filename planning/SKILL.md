---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before touching code
---

# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for our codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume they are a skilled developer, but know almost nothing about our toolset or problem domain. Assume they don't know good test design very well.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

## Preflight (Must Pass)

Before writing any plan content, confirm all of these:

1. Approved design exists (from brainstorming)
2. Dedicated worktree context exists: `worktree_path`, `branch`, `base_branch`
3. Scope and success criteria are clear enough to split into testable tasks

If any item is missing, stop and ask for the minimum missing info first.

**Save plans to:** `docs/plans/YYYY-MM-DD-<feature-name>.md`

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Implementation Plan

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

<!-- workflow-contract:writing-plans.execution_context_header -->
**Execution Context:** `worktree_path=<...>; branch=<...>; base_branch=<...>`

---
```

## Task Structure

````markdown
### Task N: [Component Name]

**Priority:** P0 | P1 | P2
**Area:** backend | frontend | both
<!-- workflow-contract:writing-plans.depends_on_field -->
**Depends On:** none | Task N[, Task M]
**Acceptance Criteria:** [Testable, verifiable conditions that define "done" - use semicolons to separate multiple criteria]
**Review (Dev):** [What to check during development - security, compatibility, logging, performance concerns]
**Review (Regression):** [What to retest after all tasks are done - cross-task side effects, integration points]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

**Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

### Task Metadata Field Guide

| Field | Required | How to fill |
|-------|----------|-------------|
| **Priority** | Yes | `P0` = blocking / core path, `P1` = important but not blocking, `P2` = nice-to-have |
| **Area** | Yes | `backend` / `frontend` / `both` (extend per project) |
| **Depends On** | Yes | `none` for root tasks; otherwise explicit `Task N` references only |
| **Acceptance Criteria** | Yes | Concrete, testable conditions; use semicolons to list multiple; include key assertions from tests |
| **Review (Dev)** | Yes | What a reviewer should check during development: security, error handling, naming, edge cases |
| **Review (Regression)** | Yes | What to retest after all tasks complete: cross-module side effects, integration, performance |

## Dependency Rules

- Every non-root task must declare `Depends On`
- Dependencies must point to existing tasks in the same plan
- No circular dependencies
- Prefer the minimum dependency set needed for correctness

## Remember
- Exact file paths always
- Complete code in plan (not "add validation")
- Exact commands with expected output
- Reference relevant skills with @ syntax
- DRY, YAGNI, TDD, frequent commits
- Every Task must have Priority, Area, Depends On, Acceptance Criteria, and Review fields filled

## Automated Health Gate (Mandatory)

After the plan file is written, run an automatic health check before any commit.

<!-- workflow-contract:writing-plans.health_gate.checker_path -->
Use the checker path resolution protocol defined in `workflow-health-check/SKILL.md` to resolve `<checker_path>`, then run:

<!-- workflow-contract:writing-plans.health_gate.plan -->
Run: `python <checker_path> --mode plan --project-root . --plan docs/plans/YYYY-MM-DD-<feature-name>.md --fail-on error`
Expected: exit code `0`

Health gate anti-loop policy:
- Attempt at most 2 times (initial + 1 retry)
- If checker is unavailable/runtime-failed, do not loop; record `health_gate:degraded(unavailable)` and perform manual plan checklist
- If attempt 2 still fails with validation errors, stop automatic retries and escalate findings to user

## After the Plan

**Documentation:**
- Ensure `docs/plans/YYYY-MM-DD-<feature-name>.md` is saved
- Commit the plan document to git only after the health gate passes, or is explicitly degraded with recorded manual checklist evidence

**Strict Serialization:**
- Invoke the compile-plans skill to generate the issues JSONL snapshot for this plan.
- compile-plans will output to `docs/issues/YYYY-MM-DD_HH-mm-ss-<slug>.jsonl`.
- Do NOT invoke any other skill. compile-plans is the next step.
