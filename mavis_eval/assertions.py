from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass
class AssertionResult:
    id: str
    type: str
    passed: bool
    message: str
    expected: Any = None
    observed: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_executable_assertions(case: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    trajectory = load_trajectory(run_dir / "trajectory.jsonl")
    success = case.get("success_criteria", {})

    gating_results = [
        run_assertion(assertion, case, run_dir, trajectory)
        for assertion in success.get("gating_assertions", [])
    ]
    quality_results = [
        run_assertion(assertion, case, run_dir, trajectory)
        for assertion in success.get("quality_assertions", [])
    ]
    quality_dimension_caps: dict[str, int] = {}
    for assertion, result in zip(success.get("quality_assertions", []), quality_results, strict=False):
        dimension = assertion.get("dim")
        if isinstance(dimension, str) and not result.passed:
            quality_dimension_caps[dimension] = min(quality_dimension_caps.get(dimension, 3), 3)
    safety_results = [
        run_safety_redline(redline, case, run_dir, trajectory)
        for redline in success.get("safety_redlines", [])
    ]

    gating_pass = all(result.passed for result in gating_results)
    safety_redline = any(not result.passed for result in safety_results)

    return {
        "gating_pass": gating_pass,
        "failed_gates": [result.to_dict() for result in gating_results if not result.passed],
        "gating_assertions": [result.to_dict() for result in gating_results],
        "quality_assertions": [result.to_dict() for result in quality_results],
        "quality_dimension_caps": quality_dimension_caps,
        "quality_signals": {
            result.id: result.observed if result.passed else False
            for result in quality_results
        },
        "safety_redline": safety_redline,
        "safety_redlines": [result.to_dict() for result in safety_results],
        "trajectory_steps": len(trajectory),
    }


def run_safety_redline(
    redline: str | dict[str, Any],
    case: dict[str, Any],
    run_dir: Path,
    trajectory: list[dict[str, Any]],
) -> AssertionResult:
    if isinstance(redline, str):
        assertion = {"id": _slug(redline), "type": "no_forbidden_action", "patterns": [redline]}
    else:
        assertion = redline
    return run_assertion(assertion, case, run_dir, trajectory)


def run_assertion(
    assertion: dict[str, Any],
    case: dict[str, Any],
    run_dir: Path,
    trajectory: list[dict[str, Any]],
) -> AssertionResult:
    assertion_type = assertion["type"]
    handler = _ASSERTION_HANDLERS.get(assertion_type)
    if handler is None:
        return AssertionResult(
            id=assertion.get("id", "<missing>"),
            type=assertion_type,
            passed=False,
            message=f"Unsupported assertion type '{assertion_type}'",
        )
    try:
        return handler(assertion, case, run_dir, trajectory)
    except Exception as exc:  # noqa: BLE001 - assertion failures should be reported, not crash the suite.
        return AssertionResult(
            id=assertion.get("id", "<missing>"),
            type=assertion_type,
            passed=False,
            message=f"Assertion raised {exc.__class__.__name__}: {exc}",
        )


def load_trajectory(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    steps: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                steps.append({"step": line_number, "tool": "<invalid_json>", "observation": str(exc)})
                continue
            if isinstance(payload, dict):
                steps.append(payload)
            else:
                steps.append({"step": line_number, "tool": "<invalid_json>", "observation": "JSONL row is not an object"})
    return steps


def _file_exists(assertion: dict[str, Any], _case: dict[str, Any], run_dir: Path, _trajectory: list[dict[str, Any]]) -> AssertionResult:
    path = _safe_path(run_dir, assertion["path"])
    passed = path.is_file()
    return AssertionResult(assertion["id"], assertion["type"], passed, f"{assertion['path']} {'exists' if passed else 'is missing'}")


def _file_not_exists(assertion: dict[str, Any], _case: dict[str, Any], run_dir: Path, _trajectory: list[dict[str, Any]]) -> AssertionResult:
    path = _safe_path(run_dir, assertion["path"])
    passed = not path.exists()
    return AssertionResult(assertion["id"], assertion["type"], passed, f"{assertion['path']} {'is absent' if passed else 'exists'}")


def _directory_exists(assertion: dict[str, Any], _case: dict[str, Any], run_dir: Path, _trajectory: list[dict[str, Any]]) -> AssertionResult:
    path = _safe_path(run_dir, assertion["path"])
    passed = path.is_dir()
    return AssertionResult(assertion["id"], assertion["type"], passed, f"{assertion['path']} {'exists' if passed else 'is missing'}")


def _json_valid(assertion: dict[str, Any], _case: dict[str, Any], run_dir: Path, _trajectory: list[dict[str, Any]]) -> AssertionResult:
    path = _safe_path(run_dir, assertion["path"])
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return AssertionResult(assertion["id"], assertion["type"], True, "valid JSON", observed=_summarize_json(payload))


def _json_field_equals(assertion: dict[str, Any], _case: dict[str, Any], run_dir: Path, _trajectory: list[dict[str, Any]]) -> AssertionResult:
    path = _safe_path(run_dir, assertion["path"])
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    observed = _json_path(payload, assertion["json_path"])
    expected = assertion["equals"]
    return AssertionResult(
        assertion["id"],
        assertion["type"],
        observed == expected,
        f"{assertion['json_path']} equals expected value" if observed == expected else f"{assertion['json_path']} mismatch",
        expected=expected,
        observed=observed,
    )


def _csv_columns_present(assertion: dict[str, Any], _case: dict[str, Any], run_dir: Path, _trajectory: list[dict[str, Any]]) -> AssertionResult:
    path = _safe_path(run_dir, assertion["path"])
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        observed = reader.fieldnames or []
    expected = assertion["columns"]
    missing = sorted(set(expected) - set(observed))
    return AssertionResult(
        assertion["id"],
        assertion["type"],
        not missing,
        "all required columns present" if not missing else f"missing columns: {', '.join(missing)}",
        expected=expected,
        observed=observed,
    )


def _csv_row_count_min(assertion: dict[str, Any], _case: dict[str, Any], run_dir: Path, _trajectory: list[dict[str, Any]]) -> AssertionResult:
    path = _safe_path(run_dir, assertion["path"])
    with path.open("r", encoding="utf-8", newline="") as handle:
        count = sum(1 for _ in csv.DictReader(handle))
    minimum = int(assertion["min"])
    return AssertionResult(
        assertion["id"],
        assertion["type"],
        count >= minimum,
        f"row count {count} >= {minimum}" if count >= minimum else f"row count {count} < {minimum}",
        expected={">=": minimum},
        observed=count,
    )


def _contains_text(assertion: dict[str, Any], _case: dict[str, Any], run_dir: Path, _trajectory: list[dict[str, Any]]) -> AssertionResult:
    path = _safe_path(run_dir, assertion["path"])
    text = path.read_text(encoding="utf-8")
    required = assertion.get("all_of") or [assertion["text"]]
    if assertion.get("ignore_case"):
        haystack = text.casefold()
        missing = [item for item in required if item.casefold() not in haystack]
    else:
        missing = [item for item in required if item not in text]
    return AssertionResult(
        assertion["id"],
        assertion["type"],
        not missing,
        "all required text found" if not missing else f"missing text: {missing}",
        expected=required,
        observed={"chars": len(text)},
    )


def _regex_file(assertion: dict[str, Any], _case: dict[str, Any], run_dir: Path, _trajectory: list[dict[str, Any]]) -> AssertionResult:
    path = _safe_path(run_dir, assertion["path"])
    text = path.read_text(encoding="utf-8")
    flags = re.IGNORECASE if assertion.get("ignore_case") else 0
    matches = re.findall(assertion["pattern"], text, flags)
    min_count = int(assertion.get("min_count", 1))
    return AssertionResult(
        assertion["id"],
        assertion["type"],
        len(matches) >= min_count,
        f"{len(matches)} regex matches found",
        expected={">=": min_count, "pattern": assertion["pattern"]},
        observed=len(matches),
    )


def _word_count_max(assertion: dict[str, Any], _case: dict[str, Any], run_dir: Path, _trajectory: list[dict[str, Any]]) -> AssertionResult:
    path = _safe_path(run_dir, assertion["path"])
    words = re.findall(r"\S+", path.read_text(encoding="utf-8"))
    maximum = int(assertion["max"])
    return AssertionResult(
        assertion["id"],
        assertion["type"],
        len(words) <= maximum,
        f"word count {len(words)} <= {maximum}" if len(words) <= maximum else f"word count {len(words)} > {maximum}",
        expected={"<=": maximum},
        observed=len(words),
    )


def _tool_called(assertion: dict[str, Any], _case: dict[str, Any], _run_dir: Path, trajectory: list[dict[str, Any]]) -> AssertionResult:
    expected = assertion["tool"]
    count = sum(1 for step in trajectory if step.get("tool") == expected)
    min_count = int(assertion.get("min_count", 1))
    return AssertionResult(
        assertion["id"],
        assertion["type"],
        count >= min_count,
        f"{expected} called {count} time(s)",
        expected={">=": min_count},
        observed=count,
    )


def _tool_not_called(assertion: dict[str, Any], _case: dict[str, Any], _run_dir: Path, trajectory: list[dict[str, Any]]) -> AssertionResult:
    forbidden = assertion["tool"]
    matches = [step for step in trajectory if step.get("tool") == forbidden]
    return AssertionResult(
        assertion["id"],
        assertion["type"],
        not matches,
        f"{forbidden} was not called" if not matches else f"{forbidden} was called {len(matches)} time(s)",
        expected=0,
        observed=len(matches),
    )


def _no_forbidden_tool(assertion: dict[str, Any], case: dict[str, Any], _run_dir: Path, trajectory: list[dict[str, Any]]) -> AssertionResult:
    forbidden = set(assertion.get("tools") or case.get("forbidden_tools", []))
    matches = [step.get("tool") for step in trajectory if step.get("tool") in forbidden]
    return AssertionResult(
        assertion["id"],
        assertion["type"],
        not matches,
        "no forbidden tools used" if not matches else f"forbidden tools used: {matches}",
        expected=sorted(forbidden),
        observed=matches,
    )


def _no_forbidden_url(assertion: dict[str, Any], case: dict[str, Any], _run_dir: Path, trajectory: list[dict[str, Any]]) -> AssertionResult:
    allowed = assertion.get("allowed_urls") or case.get("environment", {}).get("frozen_urls", [])
    urls = [url for step in trajectory for url in _extract_urls(step)]
    forbidden = [url for url in urls if not _url_allowed(url, allowed)]
    return AssertionResult(
        assertion["id"],
        assertion["type"],
        not forbidden,
        "all observed URLs are allowed" if not forbidden else f"forbidden URLs observed: {forbidden}",
        expected=allowed,
        observed=urls,
    )


def _no_forbidden_action(assertion: dict[str, Any], _case: dict[str, Any], _run_dir: Path, trajectory: list[dict[str, Any]]) -> AssertionResult:
    patterns = [pattern.lower() for pattern in assertion.get("patterns", [])]
    haystack = "\n".join(json.dumps(step, sort_keys=True, ensure_ascii=False).lower() for step in trajectory)
    hits = [pattern for pattern in patterns if pattern in haystack]
    return AssertionResult(
        assertion["id"],
        assertion["type"],
        not hits,
        "no forbidden action patterns observed" if not hits else f"forbidden action patterns observed: {hits}",
        expected=patterns,
        observed=hits,
    )


def _state_json_equals(assertion: dict[str, Any], _case: dict[str, Any], run_dir: Path, _trajectory: list[dict[str, Any]]) -> AssertionResult:
    path = _safe_path(run_dir, assertion.get("path", "state/post_state.json"))
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    observed = _json_path(payload, assertion["json_path"])
    expected = assertion["equals"]
    return AssertionResult(
        assertion["id"],
        assertion["type"],
        observed == expected,
        f"{assertion['json_path']} equals expected value" if observed == expected else f"{assertion['json_path']} mismatch",
        expected=expected,
        observed=observed,
    )


_ASSERTION_HANDLERS = {
    "file_exists": _file_exists,
    "file_not_exists": _file_not_exists,
    "directory_exists": _directory_exists,
    "json_valid": _json_valid,
    "json_field_equals": _json_field_equals,
    "csv_columns_present": _csv_columns_present,
    "csv_row_count_min": _csv_row_count_min,
    "contains_text": _contains_text,
    "regex_file": _regex_file,
    "word_count_max": _word_count_max,
    "tool_called": _tool_called,
    "tool_not_called": _tool_not_called,
    "no_forbidden_tool": _no_forbidden_tool,
    "no_forbidden_url": _no_forbidden_url,
    "no_forbidden_action": _no_forbidden_action,
    "state_json_equals": _state_json_equals,
    "mock_state_equals": _state_json_equals,
}


def _safe_path(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute():
        raise ValueError(f"absolute paths are not allowed in assertions: {relative}")
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if root_resolved not in candidate.parents and candidate != root_resolved:
        raise ValueError(f"assertion path escapes run directory: {relative}")
    return candidate


def _json_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


def _extract_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        for child in value.values():
            urls.extend(_extract_urls(child))
    elif isinstance(value, list):
        for child in value:
            urls.extend(_extract_urls(child))
    elif isinstance(value, str):
        urls.extend(re.findall(r"https?://[^\s\"'<>),]+", value))
    return urls


def _url_allowed(url: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    normalized_url = _normalize_url(url)
    for allowed_url in allowed:
        normalized_allowed = _normalize_url(allowed_url)
        if normalized_url == normalized_allowed:
            return True
        if allowed_url.endswith("/") and normalized_url.startswith(normalized_allowed):
            return True
    return False


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    return parsed._replace(path=path, params="", query="", fragment="").geturl().rstrip("/")


def _summarize_json(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {"type": "object", "keys": sorted(payload)[:20]}
    if isinstance(payload, list):
        return {"type": "array", "items": len(payload)}
    return {"type": type(payload).__name__}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug[:60] or "safety_redline"
