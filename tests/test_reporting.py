from __future__ import annotations

from unittest import TestCase

from mavis_eval.reporting import compare_reports, summarize_reports


class ReportingTests(TestCase):
    def test_summarize_reports(self) -> None:
        summary = summarize_reports(
            [
                {
                    "case_id": "a_001",
                    "pass": True,
                    "partition": "smoke",
                    "scenario": "web_gui_operation",
                    "difficulty": "L1",
                    "professional_context": {"economic_sector": "Retail Trade", "occupation": "Operations Manager"},
                    "composite_score_0_to_1": 0.8,
                    "pairwise_winner": "A",
                },
                {
                    "case_id": "b_001",
                    "pass": False,
                    "partition": "smoke",
                    "scenario": "web_gui_operation",
                    "difficulty": "L2",
                    "professional_context": {"economic_sector": "Retail Trade", "occupation": "Operations Manager"},
                    "composite_score_0_to_1": 0.4,
                    "failure_modes": ["F11_incomplete_delivery"],
                    "pairwise_winner": "tie",
                },
            ]
        )

        self.assertEqual(2, summary["n"])
        self.assertEqual(0.5, summary["overall"]["pass_rate"])
        self.assertEqual(2, summary["by_economic_sector"]["Retail Trade"]["n"])
        self.assertEqual({"A": 1, "tie": 1}, summary["pairwise"]["winner_counts"])
        self.assertEqual({"F11_incomplete_delivery": 1}, summary["failure_modes"])

    def test_compare_reports(self) -> None:
        comparison = compare_reports(
            [{"case_id": "a_001", "pass": True}, {"case_id": "b_001", "pass": True}],
            [{"case_id": "a_001", "pass": True}, {"case_id": "b_001", "pass": False}],
            iterations=100,
        )

        self.assertEqual(2, comparison["common_cases"])
        self.assertEqual(-0.5, comparison["pass_rate_delta_new_minus_prior"])
