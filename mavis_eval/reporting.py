from __future__ import annotations

import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_reports(paths: list[Path]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in paths:
        if path.is_dir():
            files = sorted(path.rglob("*.json"))
        else:
            files = [path]
        for file in files:
            with file.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, list):
                reports.extend(item for item in payload if isinstance(item, dict))
            elif isinstance(payload, dict):
                reports.append(payload)
    return reports


def summarize_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "n": len(reports),
        "overall": _summarize_slice(reports),
        "by_partition": _grouped(reports, "partition"),
        "by_scenario": _grouped(reports, "scenario"),
        "by_difficulty": _grouped(reports, "difficulty"),
        "by_economic_sector": _grouped_nested(reports, ("professional_context", "economic_sector")),
        "by_occupation": _grouped_nested(reports, ("professional_context", "occupation")),
        "pairwise": _summarize_pairwise(reports),
        "failure_modes": dict(Counter(mode for report in reports for mode in report.get("failure_modes", []))),
        "safety_redline_count": sum(1 for report in reports if report.get("safety_redline")),
        "requires_human_audit_count": sum(1 for report in reports if report.get("requires_human_audit")),
    }


def compare_reports(prior: list[dict[str, Any]], new: list[dict[str, Any]], *, iterations: int = 5000) -> dict[str, Any]:
    prior_by_case = {report["case_id"]: report for report in prior if "case_id" in report}
    new_by_case = {report["case_id"]: report for report in new if "case_id" in report}
    common_ids = sorted(set(prior_by_case) & set(new_by_case))
    pairs = [(bool(prior_by_case[case_id].get("pass")), bool(new_by_case[case_id].get("pass"))) for case_id in common_ids]

    if not pairs:
        return {"common_cases": 0, "error": "no overlapping case_id values"}

    prior_rate = sum(1 for prior_pass, _ in pairs if prior_pass) / len(pairs)
    new_rate = sum(1 for _, new_pass in pairs if new_pass) / len(pairs)
    diff = new_rate - prior_rate
    ci_low, ci_high = _bootstrap_diff_ci(pairs, iterations=iterations)
    b = sum(1 for prior_pass, new_pass in pairs if not prior_pass and new_pass)
    c = sum(1 for prior_pass, new_pass in pairs if prior_pass and not new_pass)

    return {
        "common_cases": len(pairs),
        "prior_pass_rate": round(prior_rate, 4),
        "new_pass_rate": round(new_rate, 4),
        "pass_rate_delta_new_minus_prior": round(diff, 4),
        "bootstrap_95_ci": [round(ci_low, 4), round(ci_high, 4)],
        "mcnemar": {
            "prior_fail_new_pass": b,
            "prior_pass_new_fail": c,
            "two_sided_exact_p": _mcnemar_exact_p(b, c),
        },
        "block_gold_regression_rule": ci_high < -0.02,
    }


def _grouped(reports: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for report in reports:
        groups[str(report.get(field, "<missing>"))].append(report)
    return {key: _summarize_slice(value) for key, value in sorted(groups.items())}


def _grouped_nested(reports: list[dict[str, Any]], path: tuple[str, str]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outer, inner = path
    for report in reports:
        value = report.get(outer, {})
        key = value.get(inner, "<missing>") if isinstance(value, dict) else "<missing>"
        groups[str(key)].append(report)
    return {key: _summarize_slice(value) for key, value in sorted(groups.items())}


def _summarize_pairwise(reports: list[dict[str, Any]]) -> dict[str, Any]:
    winners: list[str] = []
    for report in reports:
        winner = report.get("pairwise_winner")
        if winner is None and isinstance(report.get("pairwise"), dict):
            winner = report["pairwise"].get("winner")
        if isinstance(winner, str):
            winners.append(winner)
    counts = Counter(winners)
    n = sum(counts.values())
    return {
        "n": n,
        "winner_counts": dict(counts),
        "a_win_rate": round(counts.get("A", 0) / n, 4) if n else None,
        "b_win_rate": round(counts.get("B", 0) / n, 4) if n else None,
        "tie_rate": round((counts.get("tie", 0) + counts.get("tie_fail", 0)) / n, 4) if n else None,
    }


def _summarize_slice(reports: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(reports)
    if n == 0:
        return {"n": 0, "pass_rate": 0.0, "wilson_95_ci": [0.0, 0.0]}
    passes = sum(1 for report in reports if report.get("pass"))
    scores = [
        float(report["composite_score_0_to_1"])
        for report in reports
        if isinstance(report.get("composite_score_0_to_1"), int | float)
    ]
    return {
        "n": n,
        "pass_count": passes,
        "pass_rate": round(passes / n, 4),
        "wilson_95_ci": [round(value, 4) for value in _wilson_interval(passes, n)],
        "mean_composite_score": round(sum(scores) / len(scores), 4) if scores else None,
    }


def _wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    phat = successes / n
    denominator = 1 + z**2 / n
    center = (phat + z**2 / (2 * n)) / denominator
    margin = z * math.sqrt((phat * (1 - phat) + z**2 / (4 * n)) / n) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


def _bootstrap_diff_ci(pairs: list[tuple[bool, bool]], *, iterations: int) -> tuple[float, float]:
    rng = random.Random(20260515)
    diffs: list[float] = []
    n = len(pairs)
    for _ in range(iterations):
        sample = [pairs[rng.randrange(n)] for _ in range(n)]
        prior_rate = sum(1 for prior_pass, _ in sample if prior_pass) / n
        new_rate = sum(1 for _, new_pass in sample if new_pass) / n
        diffs.append(new_rate - prior_rate)
    diffs.sort()
    return diffs[int(0.025 * iterations)], diffs[int(0.975 * iterations)]


def _mcnemar_exact_p(b: int, c: int) -> float | None:
    n = b + c
    if n == 0:
        return None
    k = min(b, c)
    tail = sum(math.comb(n, i) * (0.5**n) for i in range(k + 1))
    return round(min(1.0, 2 * tail), 6)
