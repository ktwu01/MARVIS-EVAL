"""Export real Mavis sessions from ~/.mavis/sqlite.db into runs/<case_id>/.

Background:
- We ran 13 real Mavis sessions on 2026-05-16 01:15-01:53 against the 13
  doc/data cases. The workspace dirs under runs/<case_id>/workspace/ were
  later cleaned up, but every message, tool call, and observation is still
  in Mavis's local sqlite.
- This script reads each session's messages, normalizes them into the
  harness's trajectory.jsonl schema (via the existing
  mavis_eval.adapters.mavis_runner.normalize_trajectory function), and
  replays any file-write tool calls into runs/<case_id>/output/ so that
  mavis-eval evaluate can pick them up.

Run from repo root:
    python3 scripts/export_from_mavis_db.py

It is read-only against ~/.mavis/sqlite.db; the daemon does not need to be
healthy for this to work.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mavis_eval.adapters.mavis_runner import normalize_trajectory, write_trajectory

MAVIS_DB = Path.home() / ".mavis" / "sqlite.db"
RUNS_DIR = REPO_ROOT / "runs"


def find_case_sessions(conn: sqlite3.Connection) -> dict[str, str]:
    """Return {case_id: session_id} for the latest finished session per case.

    Sessions whose workspace_dir contains 'runs/<case_id>' are matched.
    The latest by created_at wins when a case has multiple sessions.
    """
    rows = conn.execute(
        """
        SELECT session_id, workspace_dir, created_at, status
        FROM sessions
        WHERE workspace_dir LIKE '%/MARVIS-EVAL/runs/%'
          AND status = 'finished'
        ORDER BY created_at DESC
        """
    ).fetchall()

    case_to_session: dict[str, str] = {}
    pattern = re.compile(r"/runs/([^/]+?)(?:/workspace)?$")
    for session_id, workspace_dir, _created, _status in rows:
        m = pattern.search(workspace_dir or "")
        if not m:
            continue
        case_id = m.group(1)
        if case_id not in case_to_session:
            case_to_session[case_id] = session_id
    return case_to_session


def load_messages(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT data FROM session_messages WHERE session_id = ? ORDER BY timestamp",
        (session_id,),
    ).fetchall()
    return [json.loads(r[0]) for r in rows]


def replay_file_writes(steps: list[dict], case_run_dir: Path, case_id: str) -> list[str]:
    """Walk the normalized trajectory and write any agent-produced files into runs/<case>/.

    Heuristic: any tool whose name matches /write|edit|create/ and whose args carry
    a filePath / file_path / path argument that points inside runs/<case>/ gets its
    content replayed.

    Returns a list of relative paths written.
    """
    written: list[str] = []
    target_marker = f"/runs/{case_id}/"

    for step in steps:
        tool = (step.get("tool") or "").lower()
        if not any(verb in tool for verb in ("write", "edit", "create")):
            continue
        args = step.get("args") or {}
        if not isinstance(args, dict):
            continue
        file_path = args.get("filePath") or args.get("file_path") or args.get("path")
        if not file_path or target_marker not in file_path:
            continue

        rel = file_path.split(target_marker, 1)[1]
        if rel.startswith("workspace/"):
            rel = rel[len("workspace/"):]
        target = case_run_dir / rel

        content = (
            args.get("content")
            or args.get("text")
            or args.get("body")
            or args.get("newText")
        )
        if content is None:
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(str(content), encoding="utf-8")
        written.append(rel)

    return written


def main() -> int:
    if not MAVIS_DB.exists():
        print(f"ERROR: {MAVIS_DB} not found.", file=sys.stderr)
        return 1

    conn = sqlite3.connect(f"file:{MAVIS_DB}?mode=ro", uri=True)
    try:
        case_to_session = find_case_sessions(conn)
    except sqlite3.Error as exc:
        print(f"sqlite error: {exc}", file=sys.stderr)
        return 1

    if not case_to_session:
        print("No matching sessions found under MARVIS-EVAL/runs/.", file=sys.stderr)
        return 1

    print(f"Found {len(case_to_session)} case-bound sessions in sqlite.")

    for case_id, session_id in sorted(case_to_session.items()):
        case_run_dir = RUNS_DIR / case_id
        case_run_dir.mkdir(parents=True, exist_ok=True)

        messages = load_messages(conn, session_id)
        steps = normalize_trajectory(messages, session_id=session_id)
        write_trajectory(steps, case_run_dir)

        written_files = replay_file_writes(steps, case_run_dir, case_id)

        print(
            f"  {case_id:38} session={session_id[:24]}...  "
            f"steps={len(steps):3}  files={len(written_files)}"
        )

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
