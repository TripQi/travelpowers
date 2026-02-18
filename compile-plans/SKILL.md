---
name: compile-plans
description: Use after writing-plans to convert a plan document into a JSONL issues snapshot for long-term task boundary tracking and status management
argument-hint: "<path to plan file (optional, defaults to latest in docs/plans/)>"
---

You are now in "Plan -> Issues JSONL" mode.

Goal: Convert a writing-plans output (`docs/plans/YYYY-MM-DD-<feature-name>.md`) into a **uniquely named issues JSONL snapshot** (`docs/issues/<timestamp>-<slug>.jsonl`) for long-term task boundary tracking and status management.

> Core principle: The issues JSONL is a "meeting-grade task boundary contract", not an AI vanity document.
> Every entry must clearly define **what to do, how to verify, how to review, and how to test**.

**Announce at start:** "I'm using the compile-plans skill to generate the issues JSONL snapshot."

## 1. Input and Defaults

1. `$ARGUMENTS` may be empty:
   - If empty: select the **latest** `*.md` in `docs/plans/` as input.
   - If provided: treat as a plan file path (relative or absolute).
2. Read the plan file. If needed, follow references in the plan to read minimal additional context (read-only, least necessary).
3. If the plan file is missing or insufficient to split into tasks: explain in 1-2 sentences and state the minimum information needed.

## 2. General Rules

1. The goal is a **maintainable JSONL file**, not prose.
2. Never use percentage progress. All progress uses status enums (see Section 6).
3. Every issue must include:
   <!-- workflow-contract:compile-plans.schema.depends_on -->
   - `depends_on`: explicit dependency IDs (or empty array)
   - `acceptance_criteria`: verifiable, testable conditions (quantify where possible)
   - `review_initial_requirements`: what to check during development
   - `review_regression_requirements`: what to retest after all tasks are complete
   - `test_approach`: testing strategy (test files, commands, runner)
   <!-- workflow-contract:compile-plans.schema.blocked -->
   - `blocked`: structured blocking flag (`false` by default)
4. Do not stuff detailed code or background into JSONL. Use the `refs` array to point to specific lines in the plan document.
5. Write output to the `docs/issues/` directory using a uniquely named snapshot (for audit and traceability).
6. **Never** create a fixed-name "summary" file (e.g. `docs/issues/issues.jsonl`).

## 3. Splitting Rules (Plan -> Issues)

Convert each `### Task N:` in the plan into a JSONL line:

1. Default granularity: **one Task = one issue line**.
2. Splitting allowed: if a Task contains clearly independent sub-work (e.g. separate frontend and backend paths, multiple independent modules), split into multiple lines.
3. Merging allowed: if adjacent Tasks are nearly identical and belong to the same module, merge into one line and use refs to point to each Task's steps.
4. Target size: 5-30 lines is easiest to maintain. Over 30: merge similar items and use refs for detail.

### Field Mapping (Plan -> JSONL)

Plan Tasks already contain structured metadata. **Extract directly - do not fabricate.**

| Plan Task Field | JSONL Field | Extraction |
|-----------------|-------------|------------|
| `### Task N: [Name]` | `phase`, `title` | N -> phase, Name -> title |
| `**Priority:**` | `priority` | Direct extract |
| `**Area:**` | `area` | Direct extract |
| `**Depends On:**` | `depends_on` | `none` -> `[]`; `Task N` -> mapped issue IDs |
| `**Acceptance Criteria:**` | `acceptance_criteria` | Direct extract |
| `**Review (Dev):**` | `review_initial_requirements` | Direct extract |
| `**Review (Regression):**` | `review_regression_requirements` | Direct extract |
| `**Files:** + test commands from Steps` | `test_approach` | Combine: test file path + run command + test scenario summary |
| Overall Task description (from Files + Steps) | `description` | Summarize in 1-2 sentences, focus on boundaries, not implementation detail |

## 4. JSONL Schema

### Line 1: Metadata

```json
{"type":"meta","plan":"<Feature Name>","goal":"<from plan header>","tech_stack":"<from plan header>","execution_context":{"worktree_path":"<from header>","branch":"<from header>","base_branch":"<from header>"},"source":"docs/plans/YYYY-MM-DD-<feature-name>.md","total_issues":<N>}
```

### Lines 2+: Issue Lines

One JSON object per line. Field definitions:

```json
{
  "id": "FEAT-010",
  "priority": "P0",
  "phase": 1,
  "area": "backend",
  "title": "JWT Token Generation",
  "description": "Implement generate_token and verify_token functions using PyJWT with HS256",
  "depends_on": [],
  "acceptance_criteria": "generate_token(user_id) returns valid JWT; verify_token decodes correctly; expired tokens raise error",
  "test_approach": "pytest tests/auth/test_jwt.py - unit tests for generation, verification, and expiry",
  "review_initial_requirements": "Secret key not hardcoded; token expiry configurable; no sensitive data in payload",
  "review_regression_requirements": "All auth-dependent endpoints still pass; token rotation scenario tested",
  "dev_state": "pending",
  "review_initial_state": "pending",
  "review_regression_state": "pending",
  "git_state": "uncommitted",
  "blocked": false,
  "owner": "",
  "refs": ["docs/plans/2024-01-15-user-auth.md:12-88"],
  "notes": ""
}
```

**Note:** In actual output, each JSON object must be compressed to a **single line**. The multi-line format above is for readability only.

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique identifier, `<PREFIX>-NNN`, increment by 10 for easy insertion |
| `priority` | string | yes | `P0` / `P1` / `P2` |
| `phase` | number | yes | Source Task number (use `1.1`, `1.2` if split) |
| `area` | string | yes | `backend` / `frontend` / `both` (extend per project) |
| `title` | string | yes | One-line title - short, readable, meeting-discussable |
| `description` | string | yes | 1-2 sentences on "what to do", emphasize boundaries, not implementation |
| `depends_on` | array | yes | Dependency issue IDs, e.g. `[]` or `["AUTH-010"]` |
| `acceptance_criteria` | string | yes | Testable acceptance conditions (thresholds, key assertions) |
| `test_approach` | string | yes | Testing strategy: test file paths, commands, runner |
| `review_initial_requirements` | string | yes | Review checkpoints during development |
| `review_regression_requirements` | string | yes | Regression/retest checkpoints after completion |
| `dev_state` | string | yes | Development status enum (see Section 6) |
| `review_initial_state` | string | yes | Initial review status enum |
| `review_regression_state` | string | yes | Regression review status enum |
| `git_state` | string | yes | Git status enum |
| `blocked` | boolean | yes | Structured blocking flag (`false` default) |
| `owner` | string | yes | Assignee (default empty, filled after meeting) |
| `refs` | array | yes | Reference list, `["path:start_line-end_line", ...]`, pointing to plan lines |
| `notes` | string | yes | Free-form notes (default empty) |

### ID Rules

- Prefix extracted from plan name, uppercased (e.g. `user-auth` -> `AUTH`, `payment-gateway` -> `PAY`)
- Numbering increments by 10: `AUTH-010`, `AUTH-020`, `AUTH-030`...
- Allows inserting intermediate tasks later (e.g. `AUTH-015`)

## 5. Test Approach Field

Combine and extract from the plan Task's `**Files:**` and `**Step:**` sections:

- **Test file path:** from the `Test:` line under `**Files:**`
- **Test command:** from `Run:` lines in Steps (pytest or other test commands)
- **Test scenarios:** summarize key scenarios from test function names and assertions
- Format example: `"pytest tests/auth/test_jwt.py - covers token generation, verification, expiry edge cases"`
- If the project uses a specific test runner or MCP, state it explicitly

## 6. Status and Control Fields (Enums Only, No Percentages)

| Field | Values | Default |
|-------|--------|---------|
| `dev_state` | `pending` / `in_progress` / `done` | `pending` |
| `review_initial_state` | `pending` / `in_progress` / `done` | `pending` |
| `review_regression_state` | `pending` / `in_progress` / `done` | `pending` |
| `git_state` | `uncommitted` / `committed` | `uncommitted` |
| `blocked` | `false` / `true` | `false` |

## 7. File Naming and Encoding

1. Directory: ensure `docs/issues/` exists at project root (create if missing).
2. Uniquely named snapshot:
   - Format: `docs/issues/YYYY-MM-DD_HH-mm-ss-<slug>.jsonl`
   - Timestamp uses current time; slug extracted and normalized from the plan filename.
3. **Never** create a fixed-name summary entry (e.g. `docs/issues/issues.jsonl`).
4. Encoding: **UTF-8** (JSONL standard, no BOM needed).

## 8. JSONL Output Rules

1. One valid JSON object per line - no pretty-printing, no trailing commas.
2. Escape double quotes inside strings with `\"`.
3. Paths in `refs` array must be precise to `file:start_line-end_line`.
4. Order issues with **dependency-aware topological sorting**. Tie-breakers within same dependency level: priority (`P0` -> `P1` -> `P2`), then phase.
   <!-- workflow-contract:compile-plans.topological_sorting -->
5. If dependency cycles are detected, stop and report the cycle instead of generating a misleading order.

## 9. Execution Steps

1. **Locate input** - use `$ARGUMENTS` or default to the latest plan.
2. **Read plan** - parse header (Goal / Architecture / Tech Stack / Execution Context) and all Task sections.
3. **Extract issues** - follow field mapping in Section 3: directly extract metadata fields (Priority / Area / Depends On / Acceptance Criteria / Review); combine Files + Steps to generate `test_approach` and `description`.
4. **Resolve dependencies** - map `Task N` references to final issue IDs in `depends_on`.
5. **Write JSONL** - write uniquely named snapshot to `docs/issues/`.
6. **Validate:**
   - Every line is valid JSON (use `JSON.parse` or `json.loads` per line)
   - All `id` values are unique
   - `total_issues` in meta matches actual issue line count
   - Status/control fields use only allowed values
   - `refs` is non-empty and paths point to real content
   - Every `depends_on` id exists
   - No dependency cycle exists
7. **Automated health gate (mandatory):**
   <!-- workflow-contract:compile-plans.health_gate.checker_path -->
   - Resolve `<checker_path>` via `workflow-health-check/SKILL.md` protocol
   <!-- workflow-contract:compile-plans.health_gate.issues -->
   - Run: `python <checker_path> --mode issues --project-root . --issues docs/issues/YYYY-MM-DD_HH-mm-ss-<slug>.jsonl --fail-on error`
   - Expected: exit code `0`
   - Anti-loop policy: max 2 attempts (initial + 1 retry)
   - If checker unavailable/runtime-failed: mark `health_gate:degraded(unavailable)` in handoff and run manual JSONL checklist
   - If attempt 2 still fails with validation errors: stop automatic retries and escalate findings
8. **Commit** - `git add` and commit the JSONL file only after health gate pass/degraded decision is explicitly recorded.

## 10. Full Example

```jsonl
{"type":"meta","plan":"User Auth","goal":"Add JWT authentication to the API","tech_stack":"Python, FastAPI, PyJWT","execution_context":{"worktree_path":"/repo-auth","branch":"feature/auth","base_branch":"main"},"source":"docs/plans/2024-01-15-user-auth.md","total_issues":3}
{"id":"AUTH-010","priority":"P0","phase":1,"area":"backend","title":"JWT Token Generation","description":"Implement generate_token and verify_token using PyJWT with HS256; tokens carry user_id claim and configurable expiry","depends_on":[],"acceptance_criteria":"generate_token(user_id) returns valid JWT; verify_token decodes correctly; expired tokens raise ExpiredTokenError","test_approach":"pytest tests/auth/test_jwt.py - generation, verification, expiry edge cases","review_initial_requirements":"Secret key from env var not hardcoded; token expiry configurable; no PII in payload","review_regression_requirements":"All auth-dependent endpoints still pass after token format changes","dev_state":"pending","review_initial_state":"pending","review_regression_state":"pending","git_state":"uncommitted","blocked":false,"owner":"","refs":["docs/plans/2024-01-15-user-auth.md:12-88"],"notes":""}
{"id":"AUTH-020","priority":"P0","phase":2,"area":"backend","title":"Auth Middleware","description":"FastAPI dependency that extracts JWT from Authorization header and injects current_user into request","depends_on":["AUTH-010"],"acceptance_criteria":"Missing token returns 401; invalid token returns 401; valid token injects user_id into request state","test_approach":"pytest tests/auth/test_middleware.py - missing token, invalid token, valid token, expired token scenarios","review_initial_requirements":"Consistent error response format; no stack trace leakage; middleware order documented","review_regression_requirements":"Public endpoints still accessible without token; rate limiting unaffected","dev_state":"pending","review_initial_state":"pending","review_regression_state":"pending","git_state":"uncommitted","blocked":false,"owner":"","refs":["docs/plans/2024-01-15-user-auth.md:90-165"],"notes":""}
{"id":"AUTH-030","priority":"P1","phase":3,"area":"backend","title":"Protected Route Integration","description":"Apply auth middleware to all /api/v1/users/* endpoints and update OpenAPI schema","depends_on":["AUTH-020"],"acceptance_criteria":"All protected endpoints return 401 without token; 200 with valid token; OpenAPI docs show security scheme","test_approach":"pytest tests/auth/test_routes.py - integration tests with real middleware chain","review_initial_requirements":"Backward-compatible with existing API clients during migration; deprecation headers if needed","review_regression_requirements":"Full endpoint matrix tested; no unprotected admin routes","dev_state":"pending","review_initial_state":"pending","review_regression_state":"pending","git_state":"uncommitted","blocked":false,"owner":"","refs":["docs/plans/2024-01-15-user-auth.md:167-230"],"notes":""}
```

## 11. Conversation Output (Brief Handoff)

After completion, output only:

- Snapshot path: `docs/issues/YYYY-MM-DD_HH-mm-ss-<slug>.jsonl`
- Line count (number of issues)
- Health gate: `passed` / `degraded` / `failed` (with one-line reason)
- Risks or caveats (if any)
- Suggested next step: `travelpowers:executing-plan-issues <snapshot path>`
