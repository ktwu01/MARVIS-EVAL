from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCENARIOS = {
    "information_retrieval_and_synthesis",
    "long_document_understanding",
    "tabular_data_analysis",
    "visual_extraction_and_grounding",
    "audio_video_understanding",
    "content_generation",
    "planning_and_decision_support",
    "web_gui_operation",
    "desktop_file_operation",
    "multi_app_orchestration",
    "live_assistance",
    "technical_assistant",
    "os_state_change",
    "failure_recovery",
    "media_gui_operation",
}

DIFFICULTIES = {"L1", "L2", "L3", "L4", "L5"}

PARTITIONS = {
    "smoke",
    "gold",
    "full",
    "hidden",
    "live",
    "canary",
    "mobile_v0.2",
    "workspace_v0.2",
    "examples",
}

EVAL_TYPES = {
    "system_state_assertion",
    "rule_based",
    "exact_match",
    "fuzzy_match",
    "vlm_judge",
    "hybrid",
    "deterministic",
    "judge",
}

REQUIRED_CASE_FIELDS = {
    "schema_version",
    "case_id",
    "title",
    "user_instruction",
    "scenario",
    "input_modalities",
    "output_modalities",
    "difficulty",
    "environment",
    "initial_state",
    "goal_description",
    "allowed_tools",
    "forbidden_actions",
    "success_criteria",
    "evaluation",
    "rubric",
    "metadata",
}

ASSERTION_REQUIRED_FIELDS = {"id", "type"}
GDPVAL_REQUIRED_PARTITIONS = {"gold", "full", "hidden"}
GDPVAL_REQUIRED_FIELDS = {
    "professional_context",
    "reference_assets",
    "target_deliverables",
    "rubric_items",
    "human_quality",
}


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str

    def render(self) -> str:
        return f"{self.path}: {self.message}"


def load_case_documents(path: Path) -> list[tuple[dict[str, Any], str]]:
    """Load one case object or a list of case objects from a JSON file."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, dict):
        return [(payload, str(path))]
    if isinstance(payload, list):
        docs: list[tuple[dict[str, Any], str]] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ValueError(f"{path}[{index}] must be a JSON object")
            docs.append((item, f"{path}[{index}]"))
        return docs
    raise ValueError(f"{path} must contain a JSON object or array of objects")


def iter_case_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.json")))
        elif path.suffix == ".json":
            files.append(path)
    return files


def validate_cases(paths: list[Path]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for path in iter_case_files(paths):
        try:
            docs = load_case_documents(path)
        except Exception as exc:  # noqa: BLE001 - validation should report every bad file.
            issues.append(ValidationIssue(str(path), f"invalid JSON: {exc}"))
            continue
        for case, source in docs:
            issues.extend(validate_case(case, source))
    return issues


def validate_case(case: dict[str, Any], source: str = "<case>") -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    missing = sorted(REQUIRED_CASE_FIELDS - set(case))
    for field in missing:
        issues.append(ValidationIssue(source, f"missing required field '{field}'"))

    if missing:
        return issues

    _expect_string(case, "schema_version", issues, source)
    _expect_string(case, "case_id", issues, source)
    _expect_string(case, "title", issues, source)
    _expect_string(case, "user_instruction", issues, source)
    _expect_string(case, "goal_description", issues, source)

    case_id = case.get("case_id")
    if isinstance(case_id, str) and not re.fullmatch(r"[a-z][a-z0-9_]*_[0-9]{3}", case_id):
        issues.append(ValidationIssue(f"{source}.case_id", "must look like '<snake_case>_001'"))

    scenario = case.get("scenario")
    if scenario not in SCENARIOS:
        issues.append(ValidationIssue(f"{source}.scenario", f"unknown scenario '{scenario}'"))

    difficulty = case.get("difficulty")
    if difficulty not in DIFFICULTIES:
        issues.append(ValidationIssue(f"{source}.difficulty", f"unknown difficulty '{difficulty}'"))

    for field in ("input_modalities", "output_modalities", "allowed_tools", "forbidden_actions"):
        _expect_list_of_strings(case, field, issues, source, min_len=1)

    if "forbidden_tools" in case:
        _expect_list_of_strings(case, "forbidden_tools", issues, source, min_len=0)
    if "professional_context" in case and not isinstance(case["professional_context"], dict):
        issues.append(ValidationIssue(f"{source}.professional_context", "must be an object when present"))
    for field in ("reference_assets", "target_deliverables"):
        if field in case:
            issues.extend(_validate_artifact_list(case[field], f"{source}.{field}"))
    if "rubric_items" in case:
        issues.extend(_validate_rubric_items(case["rubric_items"], f"{source}.rubric_items"))
    if "human_quality" in case and not isinstance(case["human_quality"], dict):
        issues.append(ValidationIssue(f"{source}.human_quality", "must be an object when present"))
    if "pre_submission_checks" in case and not isinstance(case["pre_submission_checks"], list):
        issues.append(ValidationIssue(f"{source}.pre_submission_checks", "must be an array when present"))
    if "comparison_policy" in case and not isinstance(case["comparison_policy"], dict):
        issues.append(ValidationIssue(f"{source}.comparison_policy", "must be an object when present"))

    environment = case.get("environment")
    if not isinstance(environment, dict):
        issues.append(ValidationIssue(f"{source}.environment", "must be an object"))
    elif not isinstance(environment.get("type"), str) or not environment.get("type"):
        issues.append(ValidationIssue(f"{source}.environment.type", "must be a non-empty string"))

    if not isinstance(case.get("initial_state"), dict):
        issues.append(ValidationIssue(f"{source}.initial_state", "must be an object"))

    issues.extend(_validate_success_criteria(case["success_criteria"], f"{source}.success_criteria"))
    issues.extend(_validate_evaluation(case["evaluation"], f"{source}.evaluation"))
    issues.extend(_validate_rubric(case["rubric"], f"{source}.rubric"))
    issues.extend(_validate_metadata(case["metadata"], f"{source}.metadata"))
    issues.extend(_validate_partition_requirements(case, source))

    return issues


def _validate_success_criteria(value: Any, source: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(value, dict):
        return [ValidationIssue(source, "must be an object")]

    assertions = value.get("gating_assertions")
    if not isinstance(assertions, list) or not assertions:
        issues.append(ValidationIssue(f"{source}.gating_assertions", "must be a non-empty array"))
    else:
        for index, assertion in enumerate(assertions):
            issues.extend(_validate_assertion(assertion, f"{source}.gating_assertions[{index}]"))

    quality = value.get("quality_assertions", [])
    if not isinstance(quality, list):
        issues.append(ValidationIssue(f"{source}.quality_assertions", "must be an array when present"))
    else:
        for index, assertion in enumerate(quality):
            issues.extend(_validate_assertion(assertion, f"{source}.quality_assertions[{index}]"))

    redlines = value.get("safety_redlines", [])
    if not isinstance(redlines, list):
        issues.append(ValidationIssue(f"{source}.safety_redlines", "must be an array when present"))
    else:
        for index, assertion in enumerate(redlines):
            if isinstance(assertion, dict):
                issues.extend(_validate_assertion(assertion, f"{source}.safety_redlines[{index}]"))
            elif not isinstance(assertion, str):
                issues.append(ValidationIssue(f"{source}.safety_redlines[{index}]", "must be a string or assertion object"))

    threshold = value.get("rubric_min_composite_0_to_1")
    if not isinstance(threshold, int | float) or not 0 <= float(threshold) <= 1:
        issues.append(ValidationIssue(f"{source}.rubric_min_composite_0_to_1", "must be a number in [0, 1]"))

    return issues


def _validate_assertion(value: Any, source: str) -> list[ValidationIssue]:
    if not isinstance(value, dict):
        return [ValidationIssue(source, "must be an object")]

    issues: list[ValidationIssue] = []
    missing = sorted(ASSERTION_REQUIRED_FIELDS - set(value))
    for field in missing:
        issues.append(ValidationIssue(source, f"missing assertion field '{field}'"))
    if "id" in value and not isinstance(value["id"], str):
        issues.append(ValidationIssue(f"{source}.id", "must be a string"))
    if "type" in value and not isinstance(value["type"], str):
        issues.append(ValidationIssue(f"{source}.type", "must be a string"))
    return issues


def _validate_artifact_list(value: Any, source: str) -> list[ValidationIssue]:
    if not isinstance(value, list):
        return [ValidationIssue(source, "must be an array when present")]
    issues: list[ValidationIssue] = []
    for index, artifact in enumerate(value):
        path = f"{source}[{index}]"
        if not isinstance(artifact, dict):
            issues.append(ValidationIssue(path, "must be an object"))
            continue
        for field in ("id", "type"):
            if not isinstance(artifact.get(field), str) or not artifact.get(field):
                issues.append(ValidationIssue(f"{path}.{field}", "must be a non-empty string"))
        if "path" not in artifact and "uri" not in artifact:
            issues.append(ValidationIssue(path, "must include path or uri"))
    return issues


def _validate_rubric_items(value: Any, source: str) -> list[ValidationIssue]:
    if not isinstance(value, list):
        return [ValidationIssue(source, "must be an array when present")]
    issues: list[ValidationIssue] = []
    for index, item in enumerate(value):
        path = f"{source}[{index}]"
        if not isinstance(item, dict):
            issues.append(ValidationIssue(path, "must be an object"))
            continue
        if not isinstance(item.get("id"), str) or not item.get("id"):
            issues.append(ValidationIssue(f"{path}.id", "must be a non-empty string"))
        if not isinstance(item.get("criterion"), str) or not item.get("criterion"):
            issues.append(ValidationIssue(f"{path}.criterion", "must be a non-empty string"))
        points = item.get("points")
        if not isinstance(points, int | float) or float(points) <= 0:
            issues.append(ValidationIssue(f"{path}.points", "must be a positive number"))
    return issues


def _validate_evaluation(value: Any, source: str) -> list[ValidationIssue]:
    if not isinstance(value, dict):
        return [ValidationIssue(source, "must be an object")]
    eval_type = value.get("primary_eval_type")
    if eval_type not in EVAL_TYPES:
        return [ValidationIssue(f"{source}.primary_eval_type", f"unknown eval type '{eval_type}'")]
    return []


def _validate_partition_requirements(case: dict[str, Any], source: str) -> list[ValidationIssue]:
    partition = case.get("metadata", {}).get("partition")
    if partition not in GDPVAL_REQUIRED_PARTITIONS:
        return []
    issues: list[ValidationIssue] = []
    for field in sorted(GDPVAL_REQUIRED_FIELDS - set(case)):
        issues.append(ValidationIssue(source, f"missing GDPVAL-derived field '{field}' for {partition} partition"))
    return issues


def _validate_rubric(value: Any, source: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(value, dict) or not value:
        return [ValidationIssue(source, "must be a non-empty object")]

    weight_total = 0.0
    for name, dimension in value.items():
        dim_path = f"{source}.{name}"
        if not isinstance(dimension, dict):
            issues.append(ValidationIssue(dim_path, "must be an object"))
            continue
        weight = dimension.get("weight")
        if not isinstance(weight, int | float) or float(weight) <= 0:
            issues.append(ValidationIssue(f"{dim_path}.weight", "must be a positive number"))
        else:
            weight_total += float(weight)

        anchors = dimension.get("anchors")
        if not isinstance(anchors, dict):
            issues.append(ValidationIssue(f"{dim_path}.anchors", "must be an object with 1/3/5 anchors"))
        else:
            for anchor in ("1", "3", "5"):
                if not isinstance(anchors.get(anchor), str) or not anchors.get(anchor):
                    issues.append(ValidationIssue(f"{dim_path}.anchors.{anchor}", "must be a non-empty string"))

    if abs(weight_total - 1.0) > 0.01:
        issues.append(ValidationIssue(source, f"weights must sum to 1.0, got {weight_total:.3f}"))
    return issues


def _validate_metadata(value: Any, source: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(value, dict):
        return [ValidationIssue(source, "must be an object")]
    partition = value.get("partition")
    if partition not in PARTITIONS:
        issues.append(ValidationIssue(f"{source}.partition", f"unknown partition '{partition}'"))
    for field in ("source", "author", "created", "judge_prompt_id"):
        if not isinstance(value.get(field), str) or not value.get(field):
            issues.append(ValidationIssue(f"{source}.{field}", "must be a non-empty string"))
    reviewers = value.get("reviewers", [])
    if reviewers is not None and not isinstance(reviewers, list):
        issues.append(ValidationIssue(f"{source}.reviewers", "must be an array when present"))
    return issues


def _expect_string(case: dict[str, Any], field: str, issues: list[ValidationIssue], source: str) -> None:
    if not isinstance(case.get(field), str) or not case.get(field).strip():
        issues.append(ValidationIssue(f"{source}.{field}", "must be a non-empty string"))


def _expect_list_of_strings(
    case: dict[str, Any],
    field: str,
    issues: list[ValidationIssue],
    source: str,
    *,
    min_len: int,
) -> None:
    value = case.get(field)
    if not isinstance(value, list) or len(value) < min_len:
        issues.append(ValidationIssue(f"{source}.{field}", f"must be an array with at least {min_len} item(s)"))
        return
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            issues.append(ValidationIssue(f"{source}.{field}[{index}]", "must be a non-empty string"))
