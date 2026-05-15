from __future__ import annotations

from pathlib import Path
from unittest import TestCase

from mavis_eval.schema import validate_cases


class SchemaValidationTests(TestCase):
    def test_seed_cases_validate(self) -> None:
        issues = validate_cases([Path("cases/examples")])
        self.assertEqual([], [issue.render() for issue in issues])
