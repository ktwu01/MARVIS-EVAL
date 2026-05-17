"""Drive the local `mavis` CLI against a Mavis-Eval case.

Responsibilities:

1. Discover the `mavis` CLI on the host.
2. Materialize the run directory layout the harness expects
   (`runs/<case_id>/{output,state}` plus any case-relative input dirs).
3. Stage `input_assets` declared on the case into `runs/<case_id>/` (if
   a fixture root is provided).
4. Build the agent prompt from the case so Mavis sees deliverable paths,
   constraints, and forbidden tools.
5. Launch a session pointed at `runs/<case_id>/` as its workspace, poll
   until `status.type == "finished"`, then pull `mavis session messages`.
6. Normalize Mavis tool calls into the harness `trajectory.jsonl` schema
   (`{step, tool, args, observation, tool_call_id, timestamp_ms,
   source_session}`), excluding hidden reasoning / `thinking_content`.
7. Run the deterministic evaluator and (optionally) write the report.

The runner uses `run_dir` itself as the Mavis workspace. That keeps the
harness contract simple: every case-relative path the evaluator looks
for (`output/answer.md`, `state/post_state.json`, `contracts/`) is also
the same path Mavis writes to from its workspace.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..evaluator import evaluate_case, write_json
from ..schema import load_case_documents


DEFAULT_CLI_CANDIDATES: tuple[str, ...] = (
    os.environ.get("MAVIS_CLI", ""),
    str(Path.home() / ".mavis" / "bin" / "mavis"),
    "mavis",
)

DEFAULT_AGENT = "mavis"
DEFAULT_POLL_INTERVAL_S = 2.0
DEFAULT_TIMEOUT_S = 900.0
FINISHED_STATUSES = {"finished", "completed", "done"}
FAILED_STATUSES = {"failed", "error", "aborted", "cancelled", "canceled"}


@dataclass
class RunnerConfig:
    case_file: Path
    case_id: str
    runs_root: Path = Path("runs")
    reports_root: Path = Path("reports")
    fixtures_root: Path | None = None  # if set, copy <fixtures_root>/<case_id>/* into workspace/
    cli_path: str | None = None
    agent: str = DEFAULT_AGENT
    model: str | None = None
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S
    timeout_s: float = DEFAULT_TIMEOUT_S
    extra_prompt_suffix: str = ""
    deterministic_only: bool = True


@dataclass
class RunResult:
    case_id: str
    session_id: str
    run_dir: Path
    report_path: Path
    report: dict[str, Any]
    trajectory_steps: int
    duration_s: float
    cli_path: str
    failures: list[str] = field(default_factory=list)


def discover_cli(explicit: str | None = None) -> str:
    candidates: Iterable[str] = (explicit or "", *DEFAULT_CLI_CANDIDATES)
    for candidate in candidates:
        if not candidate:
            continue
        if "/" in candidate or "\\" in candidate:
            if Path(candidate).is_file() and os.access(candidate, os.X_OK):
                return candidate
            continue
        found = shutil.which(candidate)
        if found:
            return found
    raise RuntimeError(
        "could not find the 'mavis' CLI; set MAVIS_CLI or pass cli_path explicitly"
    )


def load_case(case_file: Path, case_id: str) -> dict[str, Any]:
    docs = load_case_documents(case_file)
    for case, _source in docs:
        if case.get("case_id") == case_id:
            return case
    raise KeyError(f"case_id '{case_id}' not found in {case_file}")


def prepare_run_dir(runs_root: Path, case_id: str) -> Path:
    run_dir = runs_root / case_id
    (run_dir / "output").mkdir(parents=True, exist_ok=True)
    (run_dir / "state").mkdir(parents=True, exist_ok=True)
    return run_dir


def stage_fixtures(case: dict[str, Any], run_dir: Path, fixtures_root: Path | None) -> list[str]:
    """Copy fixture files into the run directory.

    `input_assets[*].path` is treated as a path relative to
    `<fixtures_root>/<case_id>/` (source) and `run_dir/` (destination).
    Directories are copied recursively. Empty directories are created so
    that, e.g., the recordings/ case finds an empty folder rather than
    missing one.

    Returns the list of staged relative paths (for the prompt).
    """
    staged: list[str] = []
    workspace = run_dir

    initial_state = case.get("initial_state", {}) or {}
    declared_inputs = initial_state.get("input_files", []) or []

    for rel in declared_inputs:
        if not isinstance(rel, str) or not rel:
            continue
        target = workspace / rel
        if rel.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
            staged.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)

    for asset in case.get("input_assets", []) or []:
        rel = asset.get("path") if isinstance(asset, dict) else None
        if not isinstance(rel, str) or not rel:
            continue
        target = workspace / rel
        if fixtures_root is None:
            if asset.get("type") == "directory":
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
            continue
        src = fixtures_root / case["case_id"] / rel
        if src.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src, target)
            staged.append(rel)
        elif src.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            staged.append(rel)
        else:
            if asset.get("type") == "directory":
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)

    # Sweep: copy anything else from fixtures/<case_id>/ that wasn't
    # already staged via input_assets. Lets cases ship supporting files
    # (e.g., extra frozen archive HTML, repo_tree.txt) without listing
    # each one in input_assets.
    if fixtures_root is not None:
        case_root = fixtures_root / case["case_id"]
        if case_root.is_dir():
            for src in case_root.rglob("*"):
                if not src.is_file():
                    continue
                rel = src.relative_to(case_root).as_posix()
                if rel in staged:
                    continue
                target = workspace / rel
                if target.exists():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
                staged.append(rel)
    return staged


def build_prompt(case: dict[str, Any], run_dir: Path, extra_suffix: str = "") -> str:
    """Compose the launch prompt.

    The prompt embeds: user instruction, deliverable paths (absolute,
    inside `run_dir/output` etc.), allowed/forbidden tools, forbidden
    actions, and the workspace root. The workspace IS the run_dir, so
    Mavis's relative writes land where the evaluator reads them.
    """
    workspace = run_dir.resolve()
    output_root = (run_dir / "output").resolve()

    final_paths = case.get("evaluation", {}).get("final_artifact_paths", []) or []
    deliverable_lines = []
    for rel in final_paths:
        if not isinstance(rel, str):
            continue
        abs_path = (run_dir / rel).resolve()
        deliverable_lines.append(f"- {rel} -> {abs_path}")

    input_lines = []
    frozen_urls = case.get("environment", {}).get("frozen_urls", []) or []
    url_assets = [
        asset for asset in case.get("input_assets", []) or []
        if isinstance(asset, dict) and asset.get("type") == "url"
    ]
    for asset in case.get("input_assets", []) or []:
        if not isinstance(asset, dict):
            continue
        rel = asset.get("path")
        if not isinstance(rel, str):
            continue
        abs_input = (workspace / rel).resolve()
        input_lines.append(f"- {rel} -> {abs_input}")

    citation_lines = []
    if frozen_urls:
        # Best-effort mapping: pair frozen_urls with url_assets in order, then
        # for any frozen_url without a paired asset, derive a local archive
        # path from the URL's filename so the agent can still read it.
        seen_paths: set[str] = set()
        for idx, url in enumerate(frozen_urls):
            if idx < len(url_assets):
                rel = url_assets[idx].get("path")
            else:
                tail = url.rsplit("/", 1)[-1]
                tail = tail.split("?", 1)[0] or "page.html"
                if not tail.endswith(".html") and not tail.endswith(".htm"):
                    tail += ".html"
                rel = f"archive/{tail}"
            if not isinstance(rel, str) or rel in seen_paths:
                continue
            seen_paths.add(rel)
            citation_lines.append(f"- local {rel} archives {url}")

    forbidden_tools = case.get("forbidden_tools", []) or []
    forbidden_actions = case.get("forbidden_actions", []) or []
    allowed_tools = case.get("allowed_tools", []) or []

    parts = [
        f"Case: {case.get('case_id')} ({case.get('title', '')})",
        "",
        "User task:",
        case["user_instruction"].strip(),
        "",
        f"Workspace root (already exists): {workspace}",
        f"Deliverables MUST be written to absolute paths under: {output_root}",
    ]
    if input_lines:
        parts.append("Input fixtures (read from these absolute paths):")
        parts.extend(input_lines)
        parts.append("")
    if citation_lines:
        parts.append(
            "These local files are frozen archives of the URLs listed below. "
            "Cite the canonical archive URLs in your deliverable (not the local paths):"
        )
        parts.extend(citation_lines)
        parts.append("")
    if deliverable_lines:
        parts.append("Required deliverable files (relative -> absolute):")
        parts.extend(deliverable_lines)
    if allowed_tools:
        parts.append("")
        parts.append("Allowed tool classes: " + ", ".join(allowed_tools))
    if forbidden_tools:
        parts.append("Forbidden tools (do not call): " + ", ".join(forbidden_tools))
    if forbidden_actions:
        parts.append("Forbidden actions:")
        for a in forbidden_actions:
            parts.append(f"  - {a}")
    parts.append("")
    parts.append(
        "Operate only inside the workspace. Do not access the network unless "
        "an allowed tool requires it. Produce the deliverable file(s) exactly "
        "at the absolute paths listed above."
    )
    if extra_suffix:
        parts.append("")
        parts.append(extra_suffix.strip())
    return "\n".join(parts)


def launch_session(
    cli_path: str,
    *,
    agent: str,
    workspace: Path,
    prompt: str,
    title: str,
    model: str | None = None,
) -> str:
    cmd = [
        cli_path,
        "session",
        "new",
        agent,
        "--from",
        "root",
        "--workspace",
        str(workspace),
        "--prompt",
        prompt,
        "--title",
        title,
    ]
    if model:
        cmd.extend(["--model", model])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"mavis session new failed (rc={proc.returncode}): "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
    # The CLI prints a human header line, then a JSON object. Parse the
    # last JSON object out of stdout.
    payload = _parse_last_json(proc.stdout)
    session_id = payload.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError(f"could not parse sessionId from: {proc.stdout!r}")
    return session_id


def wait_for_session(
    cli_path: str,
    session_id: str,
    *,
    timeout_s: float,
    poll_interval_s: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        info = _session_info(cli_path, session_id)
        status = info.get("session", {}).get("status", {}) or {}
        status_type = status.get("type")
        last_status = status
        if status_type in FINISHED_STATUSES:
            return info
        if status_type in FAILED_STATUSES:
            raise RuntimeError(f"session {session_id} ended with status {status_type}: {status}")
        time.sleep(poll_interval_s)
    raise TimeoutError(
        f"session {session_id} did not finish within {timeout_s}s; last status={last_status}"
    )


def fetch_messages(cli_path: str, session_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [cli_path, "session", "messages", session_id, "--limit", str(limit)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"mavis session messages failed: stderr={proc.stderr!r}"
        )
    payload = _parse_last_json(proc.stdout)
    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        raise RuntimeError(f"unexpected messages shape: {payload!r}")
    return messages


def normalize_trajectory(messages: list[dict[str, Any]], *, session_id: str) -> list[dict[str, Any]]:
    """Flatten Mavis messages into the harness trajectory.jsonl schema.

    Only `tool_calls` are emitted. `thinking_content` and free-form
    assistant prose are intentionally excluded so the trajectory cannot
    leak hidden reasoning into the judge payload.
    """
    steps: list[dict[str, Any]] = []
    step = 0
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for call in msg.get("tool_calls", []) or []:
            step += 1
            raw_args = call.get("tool_call_args")
            args: Any
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {"raw": raw_args}
            else:
                args = raw_args
            steps.append(
                {
                    "step": step,
                    "tool": call.get("tool_name", "<unknown>"),
                    "args": args,
                    "observation": call.get("tool_call_result_data", ""),
                    "tool_call_id": call.get("tool_call_id"),
                    "timestamp_ms": msg.get("timestamp"),
                    "source_session": session_id,
                }
            )
    return steps


def write_trajectory(steps: list[dict[str, Any]], run_dir: Path) -> Path:
    path = run_dir / "trajectory.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for step in steps:
            handle.write(json.dumps(step, ensure_ascii=False) + "\n")
    return path


def run_case(config: RunnerConfig) -> RunResult:
    cli = discover_cli(config.cli_path)
    case = load_case(config.case_file, config.case_id)
    run_dir = prepare_run_dir(config.runs_root, config.case_id)
    stage_fixtures(case, run_dir, config.fixtures_root)
    prompt = build_prompt(case, run_dir, config.extra_prompt_suffix)
    workspace = run_dir.resolve()
    started = time.monotonic()
    session_id = launch_session(
        cli,
        agent=config.agent,
        workspace=workspace,
        prompt=prompt,
        title=f"mavis-eval: {config.case_id}",
        model=config.model,
    )
    failures: list[str] = []
    try:
        wait_for_session(
            cli,
            session_id,
            timeout_s=config.timeout_s,
            poll_interval_s=config.poll_interval_s,
        )
    except (TimeoutError, RuntimeError) as exc:
        failures.append(f"session_wait: {exc}")
    messages = fetch_messages(cli, session_id)
    steps = normalize_trajectory(messages, session_id=session_id)
    write_trajectory(steps, run_dir)
    duration = time.monotonic() - started

    report = evaluate_case(
        case,
        run_dir,
        judge_result=None,
        deterministic_only=config.deterministic_only,
    )
    report_path = config.reports_root / f"{config.case_id}.json"
    write_json(report_path, report)

    return RunResult(
        case_id=config.case_id,
        session_id=session_id,
        run_dir=run_dir,
        report_path=report_path,
        report=report,
        trajectory_steps=len(steps),
        duration_s=duration,
        cli_path=cli,
        failures=failures,
    )


def _session_info(cli_path: str, session_id: str) -> dict[str, Any]:
    proc = subprocess.run(
        [cli_path, "session", "info", session_id],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"mavis session info failed: stderr={proc.stderr!r}")
    return _parse_last_json(proc.stdout)


def _parse_last_json(text: str) -> dict[str, Any]:
    """Return the last top-level JSON object found in `text`.

    The CLI sometimes prints a human header line before the JSON
    payload (e.g. `Root session created: ...`), so we scan from the
    end for the start of a `{` block and try to parse forward.
    """
    text = text.strip()
    if not text:
        raise RuntimeError("empty CLI output")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.rfind("{")
    while start != -1:
        try:
            return json.loads(text[start:])
        except json.JSONDecodeError:
            start = text.rfind("{", 0, start)
    raise RuntimeError(f"no JSON object found in output: {text!r}")


__all__ = [
    "RunnerConfig",
    "RunResult",
    "build_prompt",
    "discover_cli",
    "fetch_messages",
    "launch_session",
    "load_case",
    "normalize_trajectory",
    "prepare_run_dir",
    "run_case",
    "stage_fixtures",
    "wait_for_session",
    "write_trajectory",
]
