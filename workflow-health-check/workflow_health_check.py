#!/usr/bin/env python3
"""Workflow health checks for the travelpowers workflow.

Goals:
- Keep workflow gates deterministic and portable.
- Avoid false positives from environment-only differences.
- Avoid infinite retry loops by returning stable, actionable results.

Modes:
- skills: validate core SKILL.md contracts under skills root
- plan: validate one plan markdown
- issues: validate one issues JSONL snapshot
- full: validate plan + issues (optionally include skills)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


TASK_HEADER_RE = re.compile(r"^###\s+Task\s+([0-9]+(?:\.[0-9]+)?):\s+(.+)$")
TASK_REF_RE = re.compile(r"Task\s+([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
REF_RE = re.compile(r"^(.+):(\d+)(?:-(\d+))?$")
SKILL_MARKER_RE = re.compile(r"<!--\s*workflow-contract:\s*([a-zA-Z0-9._-]+)\s*-->")

SKILL_CONTRACTS: Dict[str, Dict[str, List[str]]] = {
    "brainstorming/SKILL.md": {
        "required_markers": [
            "brainstorming.worktree_handoff",
            "brainstorming.transition_writing_plans",
        ]
    },
    "writing-plans/SKILL.md": {
        "required_markers": [
            "writing-plans.execution_context_header",
            "writing-plans.depends_on_field",
            "writing-plans.health_gate.plan",
            "writing-plans.health_gate.checker_path",
        ]
    },
    "compile-plans/SKILL.md": {
        "required_markers": [
            "compile-plans.schema.depends_on",
            "compile-plans.schema.blocked",
            "compile-plans.topological_sorting",
            "compile-plans.health_gate.issues",
            "compile-plans.health_gate.checker_path",
        ]
    },
    "executing-plan-issues/SKILL.md": {
        "required_markers": [
            "executing-plan-issues.schema.blocked",
            "executing-plan-issues.health_gate.per_issue_pre_amend",
            "executing-plan-issues.health_gate.full_convergence",
            "executing-plan-issues.health_gate.anti_loop",
        ]
    },
    "workflow-health-check/SKILL.md": {
        "required_markers": [
            "workflow-health-check.path_resolution_protocol",
            "workflow-health-check.anti_loop_policy",
            "workflow-health-check.integration_contract",
        ]
    },
}

STATUS_ENUMS = {
    "dev_state": {"pending", "in_progress", "done"},
    "review_initial_state": {"pending", "in_progress", "done"},
    "review_regression_state": {"pending", "in_progress", "done"},
    "git_state": {"uncommitted", "committed"},
}


@dataclass
class Finding:
    severity: str  # ERROR | WARN | INFO
    message: str
    location: str = ""


@dataclass
class Report:
    name: str
    findings: List[Finding] = field(default_factory=list)

    def add(self, severity: str, message: str, location: str = "") -> None:
        self.findings.append(Finding(severity, message, location))

    def error(self, message: str, location: str = "") -> None:
        self.add("ERROR", message, location)

    def warn(self, message: str, location: str = "") -> None:
        self.add("WARN", message, location)

    def info(self, message: str, location: str = "") -> None:
        self.add("INFO", message, location)

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "ERROR")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "WARN")


def read_text(path: Path, report: Report) -> Optional[str]:
    if not path.exists():
        report.error("File does not exist", str(path))
        return None
    if not path.is_file():
        report.error("Path is not a file", str(path))
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        report.error("File is not UTF-8 decodable", str(path))
        return None


def resolve_under(base: Path, maybe_relative: Path) -> Path:
    if maybe_relative.is_absolute():
        return maybe_relative
    return (base / maybe_relative).resolve()


def latest_file(directory: Path, pattern: str) -> Optional[Path]:
    if not directory.exists() or not directory.is_dir():
        return None
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def detect_git_branch(project_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return "unknown"

    if proc.returncode != 0:
        return "unknown"

    branch = (proc.stdout or "").strip()
    return branch if branch else "unknown"


def detect_cycle(nodes: Iterable[str], edges: Dict[str, Sequence[str]]) -> Optional[List[str]]:
    state: Dict[str, int] = {n: 0 for n in nodes}  # 0 unseen, 1 visiting, 2 done
    parent: Dict[str, str] = {}

    def dfs(node: str) -> Optional[List[str]]:
        state[node] = 1
        for nxt in edges.get(node, []):
            nxt_state = state.get(nxt, 0)
            if nxt_state == 0:
                parent[nxt] = node
                cycle = dfs(nxt)
                if cycle:
                    return cycle
            elif nxt_state == 1:
                # 中文注释：构造可读环路径，避免只给出“有环”这种不可操作结论。
                chain = [nxt]
                cur = node
                while cur != nxt and cur in parent:
                    chain.append(cur)
                    cur = parent[cur]
                chain.append(nxt)
                chain.reverse()
                return chain
        state[node] = 2
        return None

    for node in nodes:
        if state[node] == 0:
            cycle = dfs(node)
            if cycle:
                return cycle
    return None


def check_skills(skills_root: Path) -> Report:
    report = Report("skills")
    for rel_path, contract in SKILL_CONTRACTS.items():
        path = skills_root / rel_path
        text = read_text(path, report)
        if text is None:
            continue

        markers = {
            match.group(1).strip().lower() for match in SKILL_MARKER_RE.finditer(text)
        }
        required_markers = [m.lower() for m in contract.get("required_markers", [])]
        for marker in required_markers:
            if marker not in markers:
                report.error(f"Missing workflow contract marker `{marker}`", str(path))

    return report


def parse_tasks(plan_text: str) -> List[Tuple[str, str, int, List[str]]]:
    lines = plan_text.splitlines()
    starts: List[Tuple[str, str, int]] = []
    for idx, line in enumerate(lines, start=1):
        match = TASK_HEADER_RE.match(line.strip())
        if match:
            starts.append((match.group(1), match.group(2).strip(), idx))

    tasks: List[Tuple[str, str, int, List[str]]] = []
    for i, (task_id, title, start_line) in enumerate(starts):
        end_line = starts[i + 1][2] - 1 if i + 1 < len(starts) else len(lines)
        block = lines[start_line - 1 : end_line]
        tasks.append((task_id, title, start_line, block))
    return tasks


def extract_field(block: Sequence[str], field_name: str) -> str:
    field_re = re.compile(rf"^\s*\*\*{re.escape(field_name)}:\*\*\s*(.*)\s*$", re.IGNORECASE)
    for line in block:
        m = field_re.match(line)
        if m:
            return m.group(1).strip()
    return ""


def parse_depends(raw_value: str) -> List[str]:
    value = raw_value.strip()
    if not value or value.lower() == "none":
        return []
    return TASK_REF_RE.findall(value)


def check_plan(plan_path: Path) -> Report:
    report = Report("plan")
    text = read_text(plan_path, report)
    if text is None:
        return report

    header_patterns = {
        "Goal": r"^\s*\*\*Goal:\*\*\s*\S+",
        "Architecture": r"^\s*\*\*Architecture:\*\*\s*\S+",
        "Tech Stack": r"^\s*\*\*Tech\s+Stack:\*\*\s*\S+",
        "Execution Context": r"^\s*\*\*Execution\s+Context:\*\*\s*\S+",
    }
    for label, pattern in header_patterns.items():
        if not re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            report.error(f"Missing required header `{label}`", str(plan_path))

    tasks = parse_tasks(text)
    if not tasks:
        report.error("No task section found (`### Task N:`)", str(plan_path))
        return report

    task_ids = {task_id for task_id, _, _, _ in tasks}
    edges: Dict[str, List[str]] = {task_id: [] for task_id in task_ids}

    required_fields = [
        "Priority",
        "Area",
        "Depends On",
        "Acceptance Criteria",
        "Review (Dev)",
        "Review (Regression)",
    ]

    for task_id, title, start_line, block in tasks:
        location = f"{plan_path}:{start_line}"

        for field_name in required_fields:
            if not extract_field(block, field_name):
                report.error(
                    f"Task {task_id} ({title}) missing field `{field_name}`",
                    location,
                )

        priority = extract_field(block, "Priority")
        if priority and priority not in {"P0", "P1", "P2"}:
            report.error(f"Task {task_id} invalid Priority `{priority}`", location)

        depends_raw = extract_field(block, "Depends On")
        deps = parse_depends(depends_raw)
        edges[task_id] = deps

        if depends_raw and depends_raw.lower() != "none" and not deps:
            report.error(f"Task {task_id} has invalid Depends On `{depends_raw}`", location)

        for dep in deps:
            if dep not in task_ids:
                report.error(f"Task {task_id} depends on unknown Task {dep}", location)
            if dep == task_id:
                report.error(f"Task {task_id} cannot depend on itself", location)

        if not any(line.strip().startswith("**Files:**") for line in block):
            report.error(f"Task {task_id} missing `**Files:**` section", location)

    cycle = detect_cycle(task_ids, edges)
    if cycle:
        report.error(f"Task dependency cycle detected: {' -> '.join(cycle)}", str(plan_path))

    return report


def parse_json_line(line: str, line_no: int, report: Report, path: Path) -> Optional[dict]:
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError as exc:
        report.error(f"Invalid JSON: {exc.msg}", f"{path}:{line_no}")
        return None
    if not isinstance(parsed, dict):
        report.error("JSONL line must be a JSON object", f"{path}:{line_no}")
        return None
    return parsed


def check_issues(issues_path: Path, project_root: Path) -> Report:
    report = Report("issues")
    text = read_text(issues_path, report)
    if text is None:
        return report

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        report.error("JSONL is empty", str(issues_path))
        return report

    rows: List[Tuple[int, dict]] = []
    for idx, line in enumerate(lines, start=1):
        parsed = parse_json_line(line, idx, report, issues_path)
        if parsed is not None:
            rows.append((idx, parsed))

    if not rows:
        return report

    meta_line_no, meta = rows[0]
    if meta.get("type") != "meta":
        report.error("First line must be `type=meta`", f"{issues_path}:{meta_line_no}")

    required_meta_fields = ["plan", "goal", "tech_stack", "source", "total_issues"]
    for field_name in required_meta_fields:
        if field_name not in meta:
            report.error(f"Meta missing field `{field_name}`", f"{issues_path}:{meta_line_no}")

    fallback_branch = detect_git_branch(project_root)
    fallback_context = {
        "worktree_path": str(project_root),
        "branch": fallback_branch,
        "base_branch": fallback_branch,
    }

    execution_context = meta.get("execution_context")
    if execution_context is None:
        report.info(
            "Meta `execution_context` missing; using fallback context (project_root/current_branch)",
            f"{issues_path}:{meta_line_no}",
        )
    elif isinstance(execution_context, dict):
        for key in ("worktree_path", "branch", "base_branch"):
            if not str(execution_context.get(key, "")).strip():
                report.info(
                    f"Meta execution_context missing `{key}`; fallback available ({fallback_context[key]})",
                    f"{issues_path}:{meta_line_no}",
                )
    else:
        report.info(
            "Meta `execution_context` is not an object; fallback context will be used",
            f"{issues_path}:{meta_line_no}",
        )

    source = meta.get("source")
    if isinstance(source, str) and source.strip():
        source_path = resolve_under(project_root, Path(source))
        if not source_path.exists():
            report.info("Meta source path not found (non-blocking)", f"{issues_path}:{meta_line_no}")

    issue_rows = rows[1:]
    if not issue_rows:
        report.error("No issue rows after meta", str(issues_path))
        return report

    total_issues = meta.get("total_issues")
    if isinstance(total_issues, int) and total_issues != len(issue_rows):
        report.error(
            f"Meta total_issues={total_issues} does not match actual={len(issue_rows)}",
            f"{issues_path}:{meta_line_no}",
        )

    required_issue_fields = [
        "id",
        "priority",
        "phase",
        "area",
        "title",
        "description",
        "depends_on",
        "acceptance_criteria",
        "test_approach",
        "review_initial_requirements",
        "review_regression_requirements",
        "dev_state",
        "review_initial_state",
        "review_regression_state",
        "git_state",
        "blocked",
        "owner",
        "refs",
        "notes",
    ]

    issue_map: Dict[str, Tuple[int, dict]] = {}
    for line_no, issue in issue_rows:
        location = f"{issues_path}:{line_no}"

        for field_name in required_issue_fields:
            if field_name not in issue:
                report.error(f"Issue missing field `{field_name}`", location)

        issue_id = issue.get("id")
        if not isinstance(issue_id, str) or not issue_id.strip():
            report.error("Issue `id` must be a non-empty string", location)
            continue
        if issue_id in issue_map:
            report.error(f"Duplicate issue id `{issue_id}`", location)
        issue_map[issue_id] = (line_no, issue)

        if issue.get("priority") not in {"P0", "P1", "P2"}:
            report.error(f"Invalid priority `{issue.get('priority')}`", location)

        for field_name, allowed in STATUS_ENUMS.items():
            value = issue.get(field_name)
            if value not in allowed:
                report.error(f"Invalid {field_name} `{value}`", location)

        if not isinstance(issue.get("blocked"), bool):
            report.error("`blocked` must be boolean", location)

        depends_on = issue.get("depends_on")
        if not isinstance(depends_on, list):
            report.error("`depends_on` must be an array", location)

        refs = issue.get("refs")
        if not isinstance(refs, list) or not refs:
            report.error("`refs` must be a non-empty array", location)
        else:
            for ref in refs:
                if not isinstance(ref, str):
                    report.error("Each ref must be string", location)
                    continue
                match = REF_RE.match(ref)
                if not match:
                    report.error(f"Invalid ref format `{ref}`", location)
                    continue
                ref_path = Path(match.group(1))
                resolved = resolve_under(project_root, ref_path)
                if not resolved.exists():
                    report.info(f"Referenced path not found (non-blocking): {ref_path}", location)

        if issue.get("git_state") == "committed":
            for state_name in ("dev_state", "review_initial_state", "review_regression_state"):
                if issue.get(state_name) != "done":
                    report.error(f"Committed issue must have `{state_name}=done`", location)
            if issue.get("blocked") is True:
                report.error("Committed issue cannot be blocked", location)

    issue_ids = list(issue_map.keys())
    edges: Dict[str, List[str]] = {issue_id: [] for issue_id in issue_ids}

    for issue_id, (line_no, issue) in issue_map.items():
        location = f"{issues_path}:{line_no}"
        depends_on = issue.get("depends_on", [])
        if not isinstance(depends_on, list):
            continue
        for dep_id in depends_on:
            if not isinstance(dep_id, str) or not dep_id.strip():
                report.error("depends_on entries must be non-empty strings", location)
                continue
            if dep_id == issue_id:
                report.error("Issue cannot depend on itself", location)
                continue
            if dep_id not in issue_map:
                report.error(f"Issue depends on unknown id `{dep_id}`", location)
                continue
            edges[issue_id].append(dep_id)

    cycle = detect_cycle(issue_ids, edges)
    if cycle:
        report.error(f"Issue dependency cycle detected: {' -> '.join(cycle)}", str(issues_path))

    return report


def print_reports(reports: Sequence[Report]) -> Tuple[int, int]:
    error_count = 0
    warning_count = 0

    for report in reports:
        print(f"== {report.name} ==")
        if not report.findings:
            print("PASS: no findings")
        else:
            for finding in report.findings:
                suffix = f" [{finding.location}]" if finding.location else ""
                print(f"{finding.severity}: {finding.message}{suffix}")
        print()
        error_count += report.errors
        warning_count += report.warnings

    print("== summary ==")
    print(f"errors={error_count} warnings={warning_count}")

    return error_count, warning_count


def resolve_plan_report(project_root: Path, plan_arg: Optional[Path], required: bool) -> Report:
    if plan_arg is not None:
        plan_path = resolve_under(project_root, plan_arg)
        return check_plan(plan_path)

    candidate = latest_file(project_root / "docs" / "plans", "*.md")
    if candidate is None:
        report = Report("plan")
        if required:
            report.error("No plan file found under docs/plans")
        else:
            report.info("Plan check skipped: no file under docs/plans")
        return report
    return check_plan(candidate)


def resolve_issues_report(project_root: Path, issues_arg: Optional[Path], required: bool) -> Report:
    if issues_arg is not None:
        issues_path = resolve_under(project_root, issues_arg)
        return check_issues(issues_path, project_root)

    candidate = latest_file(project_root / "docs" / "issues", "*.jsonl")
    if candidate is None:
        report = Report("issues")
        if required:
            report.error("No issues snapshot found under docs/issues/")
        else:
            report.info("Issues check skipped: no file under docs/issues/")
        return report
    return check_issues(candidate, project_root)


def decide_exit_code(errors: int, warnings: int, fail_on: str) -> int:
    if fail_on == "never":
        return 0
    if errors > 0:
        return 1
    if fail_on == "warning" and warnings > 0:
        return 2
    return 0


def run(args: argparse.Namespace) -> int:
    project_root = args.project_root.resolve()
    script_dir = Path(__file__).resolve().parent
    default_skills_root = script_dir.parent
    skills_root = (args.skills_root.resolve() if args.skills_root else default_skills_root)

    fail_on = "warning" if args.strict_warnings else args.fail_on

    reports: List[Report] = []

    if args.mode == "skills":
        reports.append(check_skills(skills_root))

    elif args.mode == "plan":
        reports.append(resolve_plan_report(project_root, args.plan, required=True))

    elif args.mode == "issues":
        reports.append(resolve_issues_report(project_root, args.issues, required=True))

    elif args.mode == "full":
        if args.include_skills:
            reports.append(check_skills(skills_root))
        reports.append(resolve_plan_report(project_root, args.plan, required=args.require_plan))
        reports.append(resolve_issues_report(project_root, args.issues, required=args.require_issues))

    else:
        raise ValueError(f"Unsupported mode: {args.mode}")

    errors, warnings = print_reports(reports)
    return decide_exit_code(errors, warnings, fail_on)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Workflow health checks for travelpowers")
    parser.add_argument(
        "--mode",
        choices=["skills", "plan", "issues", "full"],
        default="full",
        help="Check mode",
    )
    parser.add_argument(
        "--project-root",
        "--root",
        dest="project_root",
        type=Path,
        default=Path.cwd(),
        help="Project root path (default: current working directory)",
    )
    parser.add_argument(
        "--skills-root",
        type=Path,
        help="Skills root path (default: inferred from checker script location)",
    )
    parser.add_argument(
        "--plan",
        type=Path,
        help="Plan markdown path; relative paths are resolved under project root",
    )
    parser.add_argument(
        "--issues",
        type=Path,
        help="Issues JSONL path; relative paths are resolved under project root",
    )
    parser.add_argument(
        "--include-skills",
        action="store_true",
        help="In full mode, include skills contract checks",
    )
    parser.add_argument(
        "--require-plan",
        action="store_true",
        help="In full mode, fail if no plan is found/provided",
    )
    parser.add_argument(
        "--require-issues",
        action="store_true",
        help="In full mode, fail if no issues snapshot is found/provided",
    )
    parser.add_argument(
        "--fail-on",
        choices=["error", "warning", "never"],
        default="error",
        help="Failure threshold (default: error)",
    )
    parser.add_argument(
        "--strict-warnings",
        action="store_true",
        help="Deprecated alias of --fail-on warning",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as exc:  # defensive guard to prevent silent hangs
        print("== runtime ==")
        print(f"ERROR: unexpected checker failure: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
