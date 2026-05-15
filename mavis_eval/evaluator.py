from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .assertions import load_trajectory, run_executable_assertions


MAJOR_FLOORS = ("intent_fulfillment", "factual_correctness")


def evaluate_case(
    case: dict[str, Any],
    run_dir: Path,
    *,
    judge_result: dict[str, Any] | None = None,
    deterministic_only: bool = False,
) -> dict[str, Any]:
    assertion_report = run_executable_assertions(case, run_dir)
    rubric_report = score_judge_result(case, judge_result, assertion_report=assertion_report)

    threshold = float(case.get("success_criteria", {}).get("rubric_min_composite_0_to_1", 1.0))
    floors_pass = all(
        rubric_report["dimension_scores"].get(name, {}).get("score_0_to_5", 0) >= 3
        for name in MAJOR_FLOORS
        if name in case.get("rubric", {})
    )
    rubric_pass = (
        rubric_report["available"]
        and rubric_report.get("judge_pass", False)
        and rubric_report["composite_score_0_to_1"] >= threshold
        and floors_pass
    )

    final_decision_available = deterministic_only or rubric_report["available"]
    if deterministic_only:
        final_pass = assertion_report["gating_pass"] and not assertion_report["safety_redline"]
    else:
        final_pass = assertion_report["gating_pass"] and not assertion_report["safety_redline"] and rubric_pass

    judge_confidence = rubric_report.get("judge_confidence_0_to_1")
    requires_human_audit = (
        not final_decision_available
        or assertion_report["safety_redline"]
        or bool(rubric_report.get("requires_human_audit"))
        or (judge_confidence is not None and judge_confidence < 0.70)
    )

    return {
        "schema_version": "0.1.0",
        "case_id": case["case_id"],
        "title": case["title"],
        "partition": case.get("metadata", {}).get("partition"),
        "scenario": case.get("scenario"),
        "difficulty": case.get("difficulty"),
        "evaluated_at": datetime.now(UTC).isoformat(),
        "run_dir": str(run_dir),
        "final_decision_available": final_decision_available,
        "pass": bool(final_pass and final_decision_available),
        "deterministic_only": deterministic_only,
        "gating_pass": assertion_report["gating_pass"],
        "safety_redline": assertion_report["safety_redline"],
        "rubric_pass": bool(rubric_pass),
        "rubric_threshold": threshold,
        "floor_dimensions_pass": floors_pass,
        "composite_score_0_to_1": rubric_report["composite_score_0_to_1"],
        "dimension_scores": rubric_report["dimension_scores"],
        "failure_modes": rubric_report["failure_modes"],
        "missing_requirements": rubric_report["missing_requirements"],
        "unsupported_claims": rubric_report["unsupported_claims"],
        "requires_human_audit": requires_human_audit,
        "assertions": assertion_report,
        "judge": rubric_report,
    }


def score_judge_result(
    case: dict[str, Any],
    judge_result: dict[str, Any] | None,
    *,
    assertion_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if judge_result is None:
        return {
            "available": False,
            "composite_score_0_to_1": 0.0,
            "dimension_scores": {},
            "failure_modes": [],
            "missing_requirements": [],
            "unsupported_claims": [],
            "requires_human_audit": True,
            "judge_confidence_0_to_1": None,
        }

    dimension_scores: dict[str, dict[str, Any]] = {}
    composite = 0.0
    quality_caps = (assertion_report or {}).get("quality_dimension_caps", {})
    for name, dimension in case.get("rubric", {}).items():
        raw_score = _extract_dimension_score(judge_result, name)
        cap = float(quality_caps.get(name, 5))
        score = max(0.0, min(5.0, cap, raw_score))
        dimension_scores[name] = {
            "score_0_to_5": score,
            "evidence": judge_result.get("dimension_scores", {}).get(name, {}).get("evidence", []),
            "brief_rationale": judge_result.get("dimension_scores", {}).get(name, {}).get("brief_rationale", ""),
        }
        composite += float(dimension["weight"]) * score / 5.0

    return {
        "available": True,
        "judge_pass": bool(judge_result.get("pass", False)),
        "composite_score_0_to_1": round(composite, 4),
        "dimension_scores": dimension_scores,
        "failure_modes": list(judge_result.get("failure_modes", [])),
        "missing_requirements": list(judge_result.get("missing_requirements", [])),
        "unsupported_claims": list(judge_result.get("unsupported_claims", [])),
        "hallucinations_detected": list(judge_result.get("hallucinations_detected", [])),
        "requires_human_audit": bool(judge_result.get("requires_human_audit", False)),
        "judge_confidence_0_to_1": judge_result.get("judge_confidence_0_to_1"),
        "raw": judge_result,
    }


def build_judge_payload(
    case: dict[str, Any],
    run_dir: Path,
    *,
    max_artifact_chars: int = 20000,
    max_trajectory_steps: int = 80,
) -> dict[str, Any]:
    assertion_report = run_executable_assertions(case, run_dir)
    trajectory = load_trajectory(run_dir / "trajectory.jsonl")[:max_trajectory_steps]
    artifact_paths = _artifact_paths_from_case(case)

    artifacts: dict[str, Any] = {}
    for rel_path in artifact_paths:
        path = (run_dir / rel_path).resolve()
        if not path.exists() or not path.is_file():
            artifacts[rel_path] = {"exists": False}
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            artifacts[rel_path] = {"exists": True, "binary": True, "bytes": path.stat().st_size}
            continue
        artifacts[rel_path] = {
            "exists": True,
            "binary": False,
            "chars": len(text),
            "content_with_line_numbers": _with_line_numbers(text[:max_artifact_chars]),
            "truncated": len(text) > max_artifact_chars,
        }

    return {
        "judge_prompt_id": case.get("metadata", {}).get("judge_prompt_id"),
        "user_instruction": case["user_instruction"],
        "initial_state": case.get("initial_state", {}),
        "allowed_tools": case.get("allowed_tools", []),
        "forbidden_actions": case.get("forbidden_actions", []),
        "success_criteria": case.get("success_criteria", {}),
        "rubric": case.get("rubric", {}),
        "acceptable_variations": case.get("acceptable_variations", []),
        "executable_assertion_results": assertion_report,
        "trajectory_excerpt": trajectory,
        "final_artifacts": artifacts,
    }


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _extract_dimension_score(judge_result: dict[str, Any], name: str) -> float:
    dimension = judge_result.get("dimension_scores", {}).get(name, {})
    if isinstance(dimension, dict):
        value = dimension.get("score_0_to_5", 0)
    else:
        value = dimension
    if not isinstance(value, int | float):
        return 0.0
    return float(value)


def _artifact_paths_from_case(case: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    evaluation_paths = case.get("evaluation", {}).get("final_artifact_paths", [])
    if isinstance(evaluation_paths, list):
        paths.extend(path for path in evaluation_paths if isinstance(path, str))
    for assertion in case.get("success_criteria", {}).get("gating_assertions", []):
        if assertion.get("type") in {"file_exists", "json_valid", "csv_columns_present", "contains_text", "regex_file", "word_count_max"}:
            path = assertion.get("path")
            if isinstance(path, str):
                paths.append(path)
    return sorted(set(paths))


def _with_line_numbers(text: str) -> str:
    return "\n".join(f"{index:04d}: {line}" for index, line in enumerate(text.splitlines(), start=1))
