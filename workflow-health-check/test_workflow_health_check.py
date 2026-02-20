"""Comprehensive tests for workflow_health_check.py.

Covers: Report, read_text, resolve_under, latest_file, detect_git_branch,
detect_cycle, SKILL_MARKER_RE, check_skills, parse_tasks, extract_field,
parse_depends, check_plan, check_issues, decide_exit_code.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

# Ensure the module directory is on sys.path so we can import directly.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import workflow_health_check as whc  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers for check_plan tests
# ---------------------------------------------------------------------------

def _make_valid_plan() -> str:
    """Return a complete valid plan text with all required headers and task fields."""
    return (
        "# Plan Title\n"
        "\n"
        "**Goal:** Build the feature\n"
        "**Architecture:** Monolith\n"
        "**Tech Stack:** Python, Pytest\n"
        "**Execution Context:** local development\n"
        "\n"
        "### Task 1: First task\n"
        "\n"
        "**Priority:** P0\n"
        "**Area:** backend\n"
        "**Depends On:** None\n"
        "**Acceptance Criteria:** It works\n"
        "**Review Requirements:** Manual review, automated tests\n"
        "**Files:** src/main.py\n"
        "\n"
        "### Task 2: Second task\n"
        "\n"
        "**Priority:** P1\n"
        "**Area:** frontend\n"
        "**Depends On:** Task 1\n"
        "**Acceptance Criteria:** It renders\n"
        "**Review Requirements:** Manual review, automated tests\n"
        "**Files:** src/ui.py\n"
    )


# ---------------------------------------------------------------------------
# Helpers for check_issues tests
# ---------------------------------------------------------------------------

def _make_meta(**overrides: Any) -> Dict[str, Any]:
    """Return a valid meta row with optional overrides."""
    base: Dict[str, Any] = {
        "type": "meta",
        "plan": "docs/plans/plan.md",
        "goal": "Build it",
        "tech_stack": "Python",
        "source": "plan.md",
        "total_issues": 1,
        "schema_version": 2,
        "execution_context": {
            "worktree_path": "/project",
            "branch": "main",
            "base_branch": "main",
        },
    }
    base.update(overrides)
    return base


def _make_issue(**overrides: Any) -> Dict[str, Any]:
    """Return a valid issue row with optional overrides."""
    base: Dict[str, Any] = {
        "id": "ISSUE-1",
        "priority": "P0",
        "phase": "implementation",
        "area": "backend",
        "title": "Do something",
        "description": "Details here",
        "depends_on": [],
        "acceptance_criteria": "Works correctly",
        "test_approach": "Unit tests",
        "review_requirements": "Code review; regression suite",
        "dev_state": "pending",
        "review_state": "pending",
        "git_state": "uncommitted",
        "blocked": False,
        "owner": "agent",
        "refs": ["src/main.py:1-10"],
        "notes": "",
    }
    base.update(overrides)
    return base


def _write_jsonl(
    tmp_path: Path,
    meta: Dict[str, Any],
    issues: List[Dict[str, Any]],
    filename: str = "issues.jsonl",
) -> Path:
    """Write meta + issues as JSONL and return the file path."""
    lines = [json.dumps(meta)]
    for issue in issues:
        lines.append(json.dumps(issue))
    p = tmp_path / filename
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


# ===================================================================
# TestReport
# ===================================================================

class TestReport:

    def test_empty_report(self) -> None:
        r = whc.Report("empty")
        assert r.errors == 0
        assert r.warnings == 0
        assert len(r.findings) == 0

    def test_error_counting(self) -> None:
        r = whc.Report("r")
        r.error("e1")
        r.error("e2")
        assert r.errors == 2
        assert r.warnings == 0

    def test_warn_counting(self) -> None:
        r = whc.Report("r")
        r.warn("w1")
        assert r.warnings == 1
        assert r.errors == 0

    def test_info_does_not_count_as_error_or_warning(self) -> None:
        r = whc.Report("r")
        r.info("informational")
        assert r.errors == 0
        assert r.warnings == 0
        assert len(r.findings) == 1

    def test_mixed_severity(self) -> None:
        r = whc.Report("r")
        r.error("e")
        r.warn("w")
        r.info("i")
        assert r.errors == 1
        assert r.warnings == 1
        assert len(r.findings) == 3


# ===================================================================
# TestReadText
# ===================================================================

class TestReadText:

    def test_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")
        r = whc.Report("r")
        result = whc.read_text(f, r)
        assert result == "hello world"
        assert r.errors == 0

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        f = tmp_path / "missing.txt"
        r = whc.Report("r")
        result = whc.read_text(f, r)
        assert result is None
        assert r.errors == 1
        assert "does not exist" in r.findings[0].message.lower()

    def test_directory_instead_of_file(self, tmp_path: Path) -> None:
        d = tmp_path / "subdir"
        d.mkdir()
        r = whc.Report("r")
        result = whc.read_text(d, r)
        assert result is None
        assert r.errors == 1
        assert "not a file" in r.findings[0].message.lower()

    def test_non_utf8_file(self, tmp_path: Path) -> None:
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\x80\x81\x82\xff\xfe")
        r = whc.Report("r")
        result = whc.read_text(f, r)
        assert result is None
        assert r.errors == 1
        assert "utf-8" in r.findings[0].message.lower()


# ===================================================================
# TestResolveUnder
# ===================================================================

class TestResolveUnder:

    def test_relative_path(self, tmp_path: Path) -> None:
        result = whc.resolve_under(tmp_path, Path("sub/file.txt"))
        assert result == (tmp_path / "sub" / "file.txt").resolve()

    def test_absolute_path(self, tmp_path: Path) -> None:
        abs_target = tmp_path / "abs_target"
        abs_target.mkdir()
        result = whc.resolve_under(tmp_path, abs_target)
        assert result == abs_target


# ===================================================================
# TestLatestFile
# ===================================================================

class TestLatestFile:

    def test_finds_latest(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("older", encoding="utf-8")
        f2.write_text("newer", encoding="utf-8")
        # Explicitly set mtimes so the test is deterministic.
        os.utime(str(f1), (1000, 1000))
        os.utime(str(f2), (2000, 2000))
        result = whc.latest_file(tmp_path, "*.txt")
        assert result is not None
        assert result.name == "b.txt"

    def test_empty_dir(self, tmp_path: Path) -> None:
        result = whc.latest_file(tmp_path, "*.txt")
        assert result is None

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        result = whc.latest_file(tmp_path / "nope", "*.txt")
        assert result is None


# ===================================================================
# TestDetectGitBranch
# ===================================================================

class TestDetectGitBranch:

    @patch("workflow_health_check.subprocess.run")
    def test_successful(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="feature-branch\n")
        result = whc.detect_git_branch(tmp_path)
        assert result == "feature-branch"

    @patch("workflow_health_check.subprocess.run", side_effect=FileNotFoundError)
    def test_git_unavailable(self, mock_run: MagicMock, tmp_path: Path) -> None:
        result = whc.detect_git_branch(tmp_path)
        assert result == "unknown"

    @patch("workflow_health_check.subprocess.run")
    def test_non_git_repo(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        result = whc.detect_git_branch(tmp_path)
        assert result == "unknown"

    @patch("workflow_health_check.subprocess.run")
    def test_empty_stdout(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = whc.detect_git_branch(tmp_path)
        assert result == "unknown"


# ===================================================================
# TestDetectCycle
# ===================================================================

class TestDetectCycle:

    def test_no_cycle(self) -> None:
        nodes = ["A", "B", "C"]
        edges = {"A": ["B"], "B": ["C"], "C": []}
        assert whc.detect_cycle(nodes, edges) is None

    def test_simple_two_node_cycle(self) -> None:
        nodes = ["A", "B"]
        edges = {"A": ["B"], "B": ["A"]}
        cycle = whc.detect_cycle(nodes, edges)
        assert cycle is not None
        assert len(cycle) >= 2

    def test_three_node_cycle(self) -> None:
        nodes = ["A", "B", "C"]
        edges = {"A": ["B"], "B": ["C"], "C": ["A"]}
        cycle = whc.detect_cycle(nodes, edges)
        assert cycle is not None
        assert len(cycle) >= 3

    def test_disconnected_graph_no_cycle(self) -> None:
        nodes = ["A", "B", "C", "D"]
        edges = {"A": ["B"], "B": [], "C": ["D"], "D": []}
        assert whc.detect_cycle(nodes, edges) is None

    def test_empty_graph(self) -> None:
        assert whc.detect_cycle([], {}) is None


# ===================================================================
# TestMarkerRegex
# ===================================================================

class TestMarkerRegex:

    def test_matches_valid_marker(self) -> None:
        line = "<!-- workflow-contract: designing.worktree_handoff -->"
        m = whc.SKILL_MARKER_RE.search(line)
        assert m is not None

    def test_extracts_name(self) -> None:
        line = "<!-- workflow-contract: planning.execution_context_header -->"
        m = whc.SKILL_MARKER_RE.search(line)
        assert m is not None
        assert m.group(1) == "planning.execution_context_header"

    def test_no_match_regular_comment(self) -> None:
        line = "<!-- this is a regular HTML comment -->"
        assert whc.SKILL_MARKER_RE.search(line) is None

    def test_no_match_on_plain_text(self) -> None:
        line = "Some regular markdown text"
        assert whc.SKILL_MARKER_RE.search(line) is None


# ===================================================================
# TestCheckSkills
# ===================================================================

class TestCheckSkills:

    def test_all_markers_present(self, tmp_path: Path) -> None:
        for rel_path, contract in whc.SKILL_CONTRACTS.items():
            skill_file = tmp_path / rel_path
            skill_file.parent.mkdir(parents=True, exist_ok=True)
            markers = contract.get("required_markers", [])
            lines = [f"<!-- workflow-contract: {m} -->" for m in markers]
            skill_file.write_text("\n".join(lines), encoding="utf-8")

        report = whc.check_skills(tmp_path)
        assert report.errors == 0

    def test_missing_marker(self, tmp_path: Path) -> None:
        for rel_path, contract in whc.SKILL_CONTRACTS.items():
            skill_file = tmp_path / rel_path
            skill_file.parent.mkdir(parents=True, exist_ok=True)
            markers = contract.get("required_markers", [])
            # Write all markers except the first one.
            lines = [f"<!-- workflow-contract: {m} -->" for m in markers[1:]]
            skill_file.write_text("\n".join(lines), encoding="utf-8")

        report = whc.check_skills(tmp_path)
        assert report.errors >= len(whc.SKILL_CONTRACTS)

    def test_file_not_found(self, tmp_path: Path) -> None:
        # Skills root exists but none of the expected files do.
        report = whc.check_skills(tmp_path)
        assert report.errors >= 1
        has_not_exist = any(
            "does not exist" in f.message.lower() for f in report.findings
        )
        assert has_not_exist


# ===================================================================
# TestParseTasks
# ===================================================================

class TestParseTasks:

    def test_single_task(self) -> None:
        text = "### Task 1: Do something\n**Priority:** P0\n"
        tasks = whc.parse_tasks(text)
        assert len(tasks) == 1
        assert tasks[0][0] == "1"
        assert tasks[0][1] == "Do something"

    def test_multiple_tasks(self) -> None:
        text = (
            "### Task 1: First\nContent\n"
            "### Task 2: Second\nMore content\n"
        )
        tasks = whc.parse_tasks(text)
        assert len(tasks) == 2
        assert tasks[0][0] == "1"
        assert tasks[1][0] == "2"

    def test_no_tasks(self) -> None:
        text = "# Just a heading\nSome text\n"
        tasks = whc.parse_tasks(text)
        assert len(tasks) == 0

    def test_split_tasks(self) -> None:
        text = (
            "### Task 1.1: Part A\nContent A\n"
            "### Task 1.2: Part B\nContent B\n"
        )
        tasks = whc.parse_tasks(text)
        assert len(tasks) == 2
        assert tasks[0][0] == "1.1"
        assert tasks[1][0] == "1.2"


# ===================================================================
# TestExtractField
# ===================================================================

class TestExtractField:

    def test_present_field(self) -> None:
        block = ["**Priority:** P0", "**Area:** backend"]
        result = whc.extract_field(block, "Priority")
        assert result == "P0"

    def test_missing_field(self) -> None:
        block = ["**Area:** backend"]
        result = whc.extract_field(block, "Priority")
        assert result == ""

    def test_whitespace_handling(self) -> None:
        block = ["  **Priority:**    P1   "]
        result = whc.extract_field(block, "Priority")
        assert result == "P1"


# ===================================================================
# TestParseDepends
# ===================================================================

class TestParseDepends:

    def test_none_value(self) -> None:
        assert whc.parse_depends("none") == []

    def test_empty_string(self) -> None:
        assert whc.parse_depends("") == []

    def test_single_task(self) -> None:
        result = whc.parse_depends("Task 1")
        assert result == ["1"]

    def test_multiple_tasks(self) -> None:
        result = whc.parse_depends("Task 1, Task 2")
        assert result == ["1", "2"]

    def test_case_insensitive(self) -> None:
        result = whc.parse_depends("None")
        assert result == []


# ===================================================================
# TestCheckPlan
# ===================================================================

class TestCheckPlan:

    def test_valid_plan_no_errors(self, tmp_path: Path) -> None:
        p = tmp_path / "plan.md"
        p.write_text(_make_valid_plan(), encoding="utf-8")
        report = whc.check_plan(p)
        assert report.errors == 0

    def test_missing_headers(self, tmp_path: Path) -> None:
        text = (
            "# Plan\n"
            "### Task 1: First\n"
            "**Priority:** P0\n"
            "**Area:** backend\n"
            "**Depends On:** None\n"
            "**Acceptance Criteria:** Works\n"
            "**Review Requirements:** ok\n"
            "**Files:** a.py\n"
        )
        p = tmp_path / "plan.md"
        p.write_text(text, encoding="utf-8")
        report = whc.check_plan(p)
        # At least Goal, Architecture, Tech Stack, Execution Context missing.
        missing_header_errors = [
            f for f in report.findings
            if f.severity == "ERROR" and "missing required header" in f.message.lower()
        ]
        assert len(missing_header_errors) >= 4

    def test_invalid_priority(self, tmp_path: Path) -> None:
        text = _make_valid_plan().replace("**Priority:** P0", "**Priority:** P99")
        p = tmp_path / "plan.md"
        p.write_text(text, encoding="utf-8")
        report = whc.check_plan(p)
        has_priority_error = any(
            "invalid priority" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_priority_error

    def test_missing_task_fields(self, tmp_path: Path) -> None:
        text = (
            "**Goal:** G\n"
            "**Architecture:** A\n"
            "**Tech Stack:** T\n"
            "**Execution Context:** E\n"
            "\n"
            "### Task 1: Incomplete\n"
            "**Priority:** P0\n"
            "**Area:** backend\n"
            # Missing: Depends On, Acceptance Criteria, Review Requirements,
            #          Files
        )
        p = tmp_path / "plan.md"
        p.write_text(text, encoding="utf-8")
        report = whc.check_plan(p)
        assert report.errors >= 1

    def test_unknown_dependency(self, tmp_path: Path) -> None:
        text = _make_valid_plan().replace(
            "**Depends On:** Task 1",
            "**Depends On:** Task 99",
        )
        p = tmp_path / "plan.md"
        p.write_text(text, encoding="utf-8")
        report = whc.check_plan(p)
        has_unknown = any(
            "unknown task" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_unknown

    def test_self_dependency(self, tmp_path: Path) -> None:
        text = _make_valid_plan().replace(
            "**Depends On:** Task 1",
            "**Depends On:** Task 2",
        )
        p = tmp_path / "plan.md"
        p.write_text(text, encoding="utf-8")
        report = whc.check_plan(p)
        has_self = any(
            "depend on itself" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_self

    def test_dependency_cycle(self, tmp_path: Path) -> None:
        text = (
            "**Goal:** G\n**Architecture:** A\n**Tech Stack:** T\n"
            "**Execution Context:** E\n\n"
            "### Task 1: First\n"
            "**Priority:** P0\n**Area:** a\n**Depends On:** Task 2\n"
            "**Acceptance Criteria:** c\n**Review Requirements:** r\n**Files:** f.py\n\n"
            "### Task 2: Second\n"
            "**Priority:** P0\n**Area:** a\n**Depends On:** Task 1\n"
            "**Acceptance Criteria:** c\n**Review Requirements:** r\n**Files:** f.py\n"
        )
        p = tmp_path / "plan.md"
        p.write_text(text, encoding="utf-8")
        report = whc.check_plan(p)
        has_cycle = any(
            "cycle" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_cycle

    def test_file_not_found(self, tmp_path: Path) -> None:
        p = tmp_path / "no_such_plan.md"
        report = whc.check_plan(p)
        assert report.errors >= 1
        assert any(
            "does not exist" in f.message.lower() for f in report.findings
        )


# ===================================================================
# TestCheckIssues
# ===================================================================

class TestCheckIssues:

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_valid_jsonl_no_errors(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        # Create the ref target file so that ref path resolution passes.
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("# source", encoding="utf-8")

        meta = _make_meta(source="src/main.py")
        issue = _make_issue(refs=["src/main.py:1-10"])
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        assert report.errors == 0

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_empty_file(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        p = tmp_path / "empty.jsonl"
        p.write_text("", encoding="utf-8")
        report = whc.check_issues(p, tmp_path)
        assert report.errors >= 1
        assert any("empty" in f.message.lower() for f in report.findings)

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_missing_meta_type(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        meta = _make_meta()
        del meta["type"]
        issue = _make_issue()
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        has_meta_err = any(
            "type=meta" in f.message.lower() for f in report.findings if f.severity == "ERROR"
        )
        assert has_meta_err

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_missing_meta_fields(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        meta = {"type": "meta"}
        issue = _make_issue()
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        missing = [
            f for f in report.findings
            if f.severity == "ERROR" and "meta missing field" in f.message.lower()
        ]
        assert len(missing) >= 1

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_total_issues_mismatch(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("x", encoding="utf-8")

        meta = _make_meta(total_issues=5)
        issue = _make_issue()
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        has_mismatch = any(
            "total_issues" in f.message.lower() and "does not match" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_mismatch

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_duplicate_ids(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("x", encoding="utf-8")

        meta = _make_meta(total_issues=2)
        i1 = _make_issue(id="ISSUE-1")
        i2 = _make_issue(id="ISSUE-1")
        p = _write_jsonl(tmp_path, meta, [i1, i2])
        report = whc.check_issues(p, tmp_path)
        has_dup = any(
            "duplicate" in f.message.lower() for f in report.findings if f.severity == "ERROR"
        )
        assert has_dup

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_invalid_priority(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("x", encoding="utf-8")

        meta = _make_meta()
        issue = _make_issue(priority="P99")
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        has_prio = any(
            "invalid priority" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_prio

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_invalid_status_enum(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("x", encoding="utf-8")

        meta = _make_meta()
        issue = _make_issue(dev_state="invalid_state")
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        has_enum = any(
            "invalid dev_state" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_enum

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_blocked_not_boolean(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("x", encoding="utf-8")

        meta = _make_meta()
        issue = _make_issue(blocked="yes")
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        has_blocked = any(
            "blocked" in f.message.lower() and "boolean" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_blocked

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_committed_with_incomplete_states(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("x", encoding="utf-8")

        meta = _make_meta()
        issue = _make_issue(
            git_state="committed",
            dev_state="pending",
            review_state="pending",
        )
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        committed_errs = [
            f for f in report.findings
            if f.severity == "ERROR" and "committed" in f.message.lower() and "done" in f.message.lower()
        ]
        assert len(committed_errs) >= 1

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_committed_and_blocked(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("x", encoding="utf-8")

        meta = _make_meta()
        issue = _make_issue(
            git_state="committed",
            dev_state="done",
            review_state="done",
            blocked=True,
        )
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        has_blocked_committed = any(
            "committed" in f.message.lower() and "blocked" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_blocked_committed

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_dependency_cycle(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("x", encoding="utf-8")

        meta = _make_meta(total_issues=2)
        i1 = _make_issue(id="A", depends_on=["B"])
        i2 = _make_issue(id="B", depends_on=["A"])
        p = _write_jsonl(tmp_path, meta, [i1, i2])
        report = whc.check_issues(p, tmp_path)
        has_cycle = any(
            "cycle" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_cycle

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_unknown_dependency(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("x", encoding="utf-8")

        meta = _make_meta()
        issue = _make_issue(depends_on=["NONEXISTENT"])
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        has_unknown = any(
            "unknown" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_unknown

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_self_dependency(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("x", encoding="utf-8")

        meta = _make_meta()
        issue = _make_issue(depends_on=["ISSUE-1"])
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        has_self = any(
            "depend on itself" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_self

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_execution_context_missing_is_info_not_error(
        self, _mock_git: MagicMock, tmp_path: Path
    ) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("x", encoding="utf-8")

        meta = _make_meta()
        del meta["execution_context"]
        issue = _make_issue()
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        ec_findings = [
            f for f in report.findings if "execution_context" in f.message.lower()
        ]
        # All execution_context findings must be INFO, not ERROR.
        for finding in ec_findings:
            assert finding.severity == "INFO", (
                f"Expected INFO but got {finding.severity}: {finding.message}"
            )

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_execution_context_partial_is_info_not_error(
        self, _mock_git: MagicMock, tmp_path: Path
    ) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("x", encoding="utf-8")

        meta = _make_meta(
            execution_context={"worktree_path": "/project", "branch": "", "base_branch": ""}
        )
        issue = _make_issue()
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        ec_findings = [
            f for f in report.findings if "execution_context" in f.message.lower()
        ]
        for finding in ec_findings:
            assert finding.severity == "INFO", (
                f"Expected INFO but got {finding.severity}: {finding.message}"
            )

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_missing_issue_field(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        meta = _make_meta()
        issue = _make_issue()
        del issue["title"]
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        has_missing = any(
            "missing field" in f.message.lower() and "title" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_missing

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_invalid_json_line(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        p = tmp_path / "bad.jsonl"
        meta_line = json.dumps(_make_meta())
        p.write_text(meta_line + "\n{bad json}\n", encoding="utf-8")
        report = whc.check_issues(p, tmp_path)
        has_json_err = any(
            "invalid json" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_json_err

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_empty_refs_array(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        meta = _make_meta()
        issue = _make_issue(refs=[])
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        has_refs_err = any(
            "refs" in f.message.lower() and "non-empty" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_refs_err

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_invalid_ref_format(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        meta = _make_meta()
        issue = _make_issue(refs=["not-a-valid-ref"])
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        has_ref_err = any(
            "invalid ref format" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_ref_err

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_depends_on_not_array(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        meta = _make_meta()
        issue = _make_issue(depends_on="not-an-array")
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        has_arr_err = any(
            "depends_on" in f.message.lower() and "array" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_arr_err

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_no_issue_rows_after_meta(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        meta = _make_meta(total_issues=0)
        p = _write_jsonl(tmp_path, meta, [])
        report = whc.check_issues(p, tmp_path)
        has_no_rows = any(
            "no issue rows" in f.message.lower()
            for f in report.findings
            if f.severity == "ERROR"
        )
        assert has_no_rows

    def test_file_not_found(self, tmp_path: Path) -> None:
        p = tmp_path / "missing.jsonl"
        report = whc.check_issues(p, tmp_path)
        assert report.errors >= 1

    # --- Schema Version Tests ---

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_schema_version_missing_is_warn(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("# source", encoding="utf-8")

        meta = _make_meta(source="src/main.py")
        # Ensure no schema_version key
        meta.pop("schema_version", None)
        issue = _make_issue(refs=["src/main.py:1-10"])
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        sv_findings = [
            f for f in report.findings if "schema_version" in f.message.lower()
        ]
        assert len(sv_findings) >= 1
        assert all(f.severity == "WARN" for f in sv_findings)

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_schema_version_known_passes(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("# source", encoding="utf-8")

        meta = _make_meta(source="src/main.py", schema_version=2)
        issue = _make_issue(refs=["src/main.py:1-10"])
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        sv_findings = [
            f for f in report.findings if "schema_version" in f.message.lower()
        ]
        assert len(sv_findings) == 0

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_schema_version_unknown_is_error(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("# source", encoding="utf-8")

        meta = _make_meta(source="src/main.py", schema_version=999)
        issue = _make_issue(refs=["src/main.py:1-10"])
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        sv_errors = [
            f for f in report.findings
            if f.severity == "ERROR" and "schema_version" in f.message.lower()
        ]
        assert len(sv_errors) >= 1

    # --- Mid-Execution Append Tests ---

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_appended_issue_with_correct_total(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("# source", encoding="utf-8")

        meta = _make_meta(source="src/main.py", schema_version=2, total_issues=2)
        original = _make_issue(id="FEAT-010", refs=["src/main.py:1-10"])
        appended = _make_issue(
            id="FEAT-015",
            refs=["src/main.py:1-10"],
            notes="origin:mid_execution_append; reason:edge case; parent_issue:FEAT-010",
        )
        p = _write_jsonl(tmp_path, meta, [original, appended])
        report = whc.check_issues(p, tmp_path)
        # No errors expected when total_issues matches
        assert report.errors == 0
        # Should have INFO about appended issue
        append_infos = [
            f for f in report.findings
            if f.severity == "INFO" and "appended" in f.message.lower()
        ]
        assert len(append_infos) == 1

    # --- Archived File Tests ---

    def test_latest_file_skips_archived(self, tmp_path: Path) -> None:
        active = tmp_path / "2026-02-18_10-00-00-feat.jsonl"
        archived = tmp_path / "2026-02-17_10-00-00-old.archived.jsonl"
        active.write_text("{}", encoding="utf-8")
        archived.write_text("{}", encoding="utf-8")
        # Make archived have a newer mtime to verify it's filtered by name, not time
        os.utime(str(active), (1000, 1000))
        os.utime(str(archived), (2000, 2000))
        result = whc.latest_file(tmp_path, "*.jsonl")
        assert result is not None
        assert result.name == "2026-02-18_10-00-00-feat.jsonl"

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_archived_meta_triggers_warn(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("# source", encoding="utf-8")

        meta = _make_meta(source="src/main.py", schema_version=2, archived=True)
        issue = _make_issue(refs=["src/main.py:1-10"])
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        archived_warns = [
            f for f in report.findings
            if f.severity == "WARN" and "archived" in f.message.lower()
        ]
        assert len(archived_warns) >= 1

    @patch("workflow_health_check.detect_git_branch", return_value="main")
    def test_schema_version_2_valid(self, _mock_git: MagicMock, tmp_path: Path) -> None:
        ref_file = tmp_path / "src" / "main.py"
        ref_file.parent.mkdir(parents=True, exist_ok=True)
        ref_file.write_text("# source", encoding="utf-8")

        meta = _make_meta(source="src/main.py", schema_version=2)
        issue = _make_issue(refs=["src/main.py:1-10"])
        p = _write_jsonl(tmp_path, meta, [issue])
        report = whc.check_issues(p, tmp_path)
        assert report.errors == 0


# ===================================================================
# TestDecideExitCode
# ===================================================================

class TestDecideExitCode:

    def test_errors_fail_on_error_returns_1(self) -> None:
        assert whc.decide_exit_code(errors=1, warnings=0, fail_on="error") == 1

    def test_warnings_fail_on_warning_returns_2(self) -> None:
        assert whc.decide_exit_code(errors=0, warnings=3, fail_on="warning") == 2

    def test_errors_fail_on_never_returns_0(self) -> None:
        assert whc.decide_exit_code(errors=5, warnings=2, fail_on="never") == 0

    def test_clean_returns_0(self) -> None:
        assert whc.decide_exit_code(errors=0, warnings=0, fail_on="error") == 0

    def test_warnings_fail_on_error_returns_0(self) -> None:
        assert whc.decide_exit_code(errors=0, warnings=5, fail_on="error") == 0
