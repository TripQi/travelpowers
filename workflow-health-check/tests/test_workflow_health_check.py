import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "workflow_health_check.py"
SPEC = importlib.util.spec_from_file_location("workflow_health_check", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load checker module from {MODULE_PATH}")
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


class WorkflowHealthCheckTests(unittest.TestCase):
    def test_check_skills_passes_with_all_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_root = Path(tmp_dir)
            for rel_path, contract in CHECKER.SKILL_CONTRACTS.items():
                file_path = skills_root / rel_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                markers = contract["required_markers"]
                body = "# Skill\n\n" + "\n".join(
                    f"<!-- workflow-contract:{marker} -->" for marker in markers
                )
                file_path.write_text(body + "\n", encoding="utf-8")

            report = CHECKER.check_skills(skills_root)
            self.assertEqual(report.errors, 0, report.findings)

    def test_check_skills_fails_when_marker_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            skills_root = Path(tmp_dir)
            first_rel_path = next(iter(CHECKER.SKILL_CONTRACTS))
            missing_marker = CHECKER.SKILL_CONTRACTS[first_rel_path]["required_markers"][0]

            for rel_path, contract in CHECKER.SKILL_CONTRACTS.items():
                file_path = skills_root / rel_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                markers = list(contract["required_markers"])
                if rel_path == first_rel_path:
                    markers = [marker for marker in markers if marker != missing_marker]
                body = "# Skill\n\n" + "\n".join(
                    f"<!-- workflow-contract:{marker} -->" for marker in markers
                )
                file_path.write_text(body + "\n", encoding="utf-8")

            report = CHECKER.check_skills(skills_root)
            self.assertGreater(report.errors, 0)
            self.assertTrue(
                any(
                    finding.severity == "ERROR" and missing_marker in finding.message
                    for finding in report.findings
                )
            )

    def test_issues_missing_execution_context_uses_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            plan_path = project_root / "docs" / "plans" / "demo.md"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text("# Demo Plan\n", encoding="utf-8")

            issues_path = project_root / "docs" / "issues" / "demo.jsonl"
            issues_path.parent.mkdir(parents=True, exist_ok=True)

            meta = {
                "type": "meta",
                "plan": "Demo",
                "goal": "Goal",
                "tech_stack": "Python",
                "source": "docs/plans/demo.md",
                "total_issues": 1,
                "schema_version": 2,
            }
            issue = {
                "id": "DEMO-010",
                "priority": "P0",
                "phase": 1,
                "area": "backend",
                "title": "Demo issue",
                "description": "Test fallback",
                "depends_on": [],
                "acceptance_criteria": "criteria",
                "test_approach": "pytest -q",
                "review_requirements": "check dev flow; check regression flow",
                "dev_state": "pending",
                "review_state": "pending",
                "git_state": "uncommitted",
                "blocked": False,
                "owner": "",
                "refs": ["docs/plans/demo.md:1-1"],
                "notes": "",
            }
            issues_path.write_text(
                json.dumps(meta) + "\n" + json.dumps(issue) + "\n",
                encoding="utf-8",
            )

            report = CHECKER.check_issues(issues_path, project_root)
            self.assertEqual(report.errors, 0, report.findings)
            self.assertTrue(
                any(
                    finding.severity == "INFO" and "execution_context" in finding.message
                    for finding in report.findings
                )
            )

    def test_committed_issue_requires_done_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            plan_path = project_root / "docs" / "plans" / "demo.md"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text("# Demo Plan\n", encoding="utf-8")

            issues_path = project_root / "docs" / "issues" / "demo.jsonl"
            issues_path.parent.mkdir(parents=True, exist_ok=True)

            meta = {
                "type": "meta",
                "plan": "Demo",
                "goal": "Goal",
                "tech_stack": "Python",
                "execution_context": {
                    "worktree_path": str(project_root),
                    "branch": "feature/demo",
                    "base_branch": "main",
                },
                "source": "docs/plans/demo.md",
                "total_issues": 1,
                "schema_version": 2,
            }
            issue = {
                "id": "DEMO-020",
                "priority": "P1",
                "phase": 2,
                "area": "backend",
                "title": "Invalid committed state",
                "description": "Should fail",
                "depends_on": [],
                "acceptance_criteria": "criteria",
                "test_approach": "pytest -q",
                "review_requirements": "check dev flow; check regression flow",
                "dev_state": "pending",
                "review_state": "done",
                "git_state": "committed",
                "blocked": False,
                "owner": "",
                "refs": ["docs/plans/demo.md:1-1"],
                "notes": "",
            }
            issues_path.write_text(
                json.dumps(meta) + "\n" + json.dumps(issue) + "\n",
                encoding="utf-8",
            )

            report = CHECKER.check_issues(issues_path, project_root)
            self.assertGreater(report.errors, 0)
            self.assertTrue(
                any(
                    finding.severity == "ERROR"
                    and "Committed issue must have `dev_state=done`" in finding.message
                    for finding in report.findings
                )
            )

    def test_full_mode_without_files_is_non_blocking_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            parser = CHECKER.build_parser()
            args = parser.parse_args(
                [
                    "--mode",
                    "full",
                    "--project-root",
                    str(project_root),
                    "--fail-on",
                    "error",
                ]
            )
            self.assertEqual(CHECKER.run(args), 0)


if __name__ == "__main__":
    unittest.main()
