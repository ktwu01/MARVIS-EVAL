from __future__ import annotations

from pathlib import Path
from unittest import TestCase

from mavis_eval.schema import validate_case, validate_cases


class SchemaValidationTests(TestCase):
    def test_seed_cases_validate(self) -> None:
        issues = validate_cases([Path("cases/examples")])
        self.assertEqual([], [issue.render() for issue in issues])

    def test_gold_cases_require_gdpval_fields(self) -> None:
        case = {
            "schema_version": "0.1.0",
            "case_id": "gold_case_001",
            "title": "Gold case",
            "user_instruction": "Create the deliverable.",
            "scenario": "content_generation",
            "input_modalities": ["text"],
            "output_modalities": ["pdf"],
            "difficulty": "L3",
            "environment": {"type": "local_workspace"},
            "initial_state": {},
            "goal_description": "Create the deliverable.",
            "allowed_tools": ["file_write"],
            "forbidden_actions": ["Send externally"],
            "success_criteria": {
                "gating_assertions": [{"id": "g1", "type": "file_exists", "path": "output/report.pdf"}],
                "rubric_min_composite_0_to_1": 0.7,
            },
            "evaluation": {"primary_eval_type": "hybrid"},
            "rubric": {
                "intent_fulfillment": {"weight": 1.0, "anchors": {"1": "bad", "3": "ok", "5": "good"}},
            },
            "metadata": {"source": "test", "author": "test", "created": "2026-05-17", "partition": "gold", "judge_prompt_id": "deliverable_judge_v1.0"},
        }

        rendered = [issue.render() for issue in validate_case(case)]

        self.assertIn("<case>: missing GDPVAL-derived field 'professional_context' for gold partition", rendered)
