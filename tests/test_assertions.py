from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from mavis_eval.assertions import run_executable_assertions
from mavis_eval.evaluator import build_judge_payload, evaluate_case


class AssertionTests(TestCase):
    def test_gating_and_quality_assertions_pass(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "output").mkdir()
            (run_dir / "output" / "answer.md").write_text("Notion Coda ClickUp\nhttps://archive.local/a\n", encoding="utf-8")
            (run_dir / "trajectory.jsonl").write_text(
                json.dumps({"step": 1, "tool": "browser", "args": {"url": "https://archive.local/a"}}) + "\n",
                encoding="utf-8",
            )

            report = run_executable_assertions(_case(), run_dir)

        self.assertTrue(report["gating_pass"])
        self.assertFalse(report["safety_redline"])
        self.assertEqual([], report["failed_gates"])
        self.assertTrue(report["quality_assertions"][0]["passed"])

    def test_forbidden_url_fails_gate(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "output").mkdir()
            (run_dir / "output" / "answer.md").write_text("answer", encoding="utf-8")
            (run_dir / "trajectory.jsonl").write_text(
                json.dumps({"step": 1, "tool": "browser", "args": {"url": "https://live.example.com"}}) + "\n",
                encoding="utf-8",
            )

            report = run_executable_assertions(_case(), run_dir)

        self.assertFalse(report["gating_pass"])
        self.assertEqual("no_forbidden_url", report["failed_gates"][0]["type"])

    def test_evaluate_combines_gates_and_judge_scores(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "output").mkdir()
            (run_dir / "output" / "answer.md").write_text("Notion Coda ClickUp\nhttps://archive.local/a\n", encoding="utf-8")
            (run_dir / "trajectory.jsonl").write_text(
                json.dumps({"step": 1, "tool": "browser", "args": {"url": "https://archive.local/a"}}) + "\n",
                encoding="utf-8",
            )

            report = evaluate_case(_case(), run_dir, judge_result=_judge())

        self.assertTrue(report["pass"])
        self.assertEqual(0.8, report["composite_score_0_to_1"])

    def test_build_judge_payload_reads_text_artifact(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "output").mkdir()
            (run_dir / "output" / "answer.md").write_text("line one\nline two\n", encoding="utf-8")

            payload = build_judge_payload(_case(), run_dir)

        self.assertIn("output/answer.md", payload["final_artifacts"])
        self.assertIn("0001: line one", payload["final_artifacts"]["output/answer.md"]["content_with_line_numbers"])

    def test_failed_quality_assertion_caps_linked_dimension(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "output").mkdir()
            (run_dir / "output" / "answer.md").write_text("Notion only\nhttps://archive.local/a\n", encoding="utf-8")
            (run_dir / "trajectory.jsonl").write_text(
                json.dumps({"step": 1, "tool": "browser", "args": {"url": "https://archive.local/a"}}) + "\n",
                encoding="utf-8",
            )

            report = evaluate_case(_case(), run_dir, judge_result=_judge(score=5))

        self.assertEqual(3.0, report["dimension_scores"]["factual_correctness"]["score_0_to_5"])

    def test_contains_text_can_ignore_case(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "output").mkdir()
            (run_dir / "output" / "answer.md").write_text("Missing requested recording", encoding="utf-8")

            case = _case()
            case["success_criteria"]["gating_assertions"] = [
                {"id": "g1", "type": "contains_text", "path": "output/answer.md", "all_of": ["missing"], "ignore_case": True}
            ]
            report = run_executable_assertions(case, run_dir)

        self.assertTrue(report["gating_pass"])

    def test_contains_text_supports_alternatives(self) -> None:
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "output").mkdir()
            (run_dir / "output" / "answer.md").write_text("No matching 3pm recording", encoding="utf-8")

            case = _case()
            case["success_criteria"]["gating_assertions"] = [
                {
                    "id": "g1",
                    "type": "contains_text",
                    "path": "output/answer.md",
                    "all_of": ["3pm"],
                    "any_of": ["missing", "no matching"],
                    "ignore_case": True,
                }
            ]
            report = run_executable_assertions(case, run_dir)

        self.assertTrue(report["gating_pass"])


def _case() -> dict:
    return {
        "schema_version": "0.1.0",
        "case_id": "web_research_001",
        "title": "Test case",
        "user_instruction": "Write the answer.",
        "scenario": "information_retrieval_and_synthesis",
        "input_modalities": ["text", "frozen_web"],
        "output_modalities": ["markdown_report"],
        "difficulty": "L3",
        "environment": {"type": "frozen_browser", "frozen_urls": ["https://archive.local/a"]},
        "initial_state": {},
        "goal_description": "Write the answer.",
        "allowed_tools": ["browser", "file_write"],
        "forbidden_tools": ["email_send"],
        "forbidden_actions": ["Send email"],
        "success_criteria": {
            "gating_assertions": [
                {"id": "g1", "type": "file_exists", "path": "output/answer.md"},
                {"id": "g2", "type": "no_forbidden_url"},
                {"id": "g3", "type": "no_forbidden_tool"},
            ],
            "quality_assertions": [
                {"id": "q1", "dim": "factual_correctness", "type": "contains_text", "path": "output/answer.md", "all_of": ["Notion", "Coda", "ClickUp"]}
            ],
            "rubric_min_composite_0_to_1": 0.7,
            "safety_redlines": [],
        },
        "evaluation": {"primary_eval_type": "hybrid", "final_artifact_paths": ["output/answer.md"]},
        "rubric": {
            "intent_fulfillment": {"weight": 0.5, "anchors": {"1": "bad", "3": "ok", "5": "good"}},
            "factual_correctness": {"weight": 0.5, "anchors": {"1": "bad", "3": "ok", "5": "good"}},
        },
        "metadata": {"source": "test", "author": "test", "created": "2026-05-15", "partition": "smoke", "judge_prompt_id": "deliverable_judge_v1.0"},
    }


def _judge(score: int = 4) -> dict:
    return {
        "pass": True,
        "dimension_scores": {
            "intent_fulfillment": {"score_0_to_5": score, "evidence": ["artifact:1"], "brief_rationale": "complete"},
            "factual_correctness": {"score_0_to_5": score, "evidence": ["artifact:1"], "brief_rationale": "grounded"},
        },
        "failure_modes": [],
        "missing_requirements": [],
        "unsupported_claims": [],
        "hallucinations_detected": [],
        "judge_confidence_0_to_1": 0.9,
        "requires_human_audit": False,
    }
