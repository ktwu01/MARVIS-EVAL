#!/usr/bin/env python3
"""Run every seed case through the local Mavis adapter and summarize."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CASE_FILE = REPO / "cases" / "examples" / "smoke_seed_cases.json"
FIXTURES = REPO / "fixtures"


def load_case_ids() -> list[str]:
    with CASE_FILE.open() as h:
        cases = json.load(h)
    return [c["case_id"] for c in cases]


def run_one(case_id: str, timeout_s: float) -> dict:
    run_dir = REPO / "runs" / case_id
    report = REPO / "reports" / f"{case_id}.json"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    if report.exists():
        report.unlink()
    started = time.monotonic()
    cmd = [
        sys.executable, "-m", "mavis_eval", "run-mavis",
        str(CASE_FILE), "--case-id", case_id,
        "--fixtures-root", str(FIXTURES),
        "--timeout-s", str(timeout_s),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
    elapsed = time.monotonic() - started
    parsed: dict = {}
    text = proc.stdout.strip()
    if text:
        start = text.rfind("{")
        while start != -1:
            try:
                parsed = json.loads(text[start:])
                break
            except json.JSONDecodeError:
                start = text.rfind("{", 0, start)
    return {
        "case_id": case_id,
        "elapsed_s": round(elapsed, 1),
        "rc": proc.returncode,
        "pass": parsed.get("pass"),
        "gating_pass": parsed.get("gating_pass"),
        "safety_redline": parsed.get("safety_redline"),
        "steps": parsed.get("trajectory_steps"),
        "session": parsed.get("session_id"),
        "failures": parsed.get("failures", []),
        "stderr_tail": proc.stderr[-400:] if proc.returncode and not parsed else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_ids", nargs="*")
    parser.add_argument("--timeout-s", type=float, default=480)
    args = parser.parse_args()
    ids = args.case_ids or load_case_ids()
    rows: list[dict] = []
    for cid in ids:
        print(f"\n=== {cid} ===", flush=True)
        row = run_one(cid, args.timeout_s)
        rows.append(row)
        print(json.dumps(row, indent=2), flush=True)
    print("\n\n===== SUMMARY =====")
    for row in rows:
        flag = "PASS" if row["pass"] else ("GATE" if row["gating_pass"] else "FAIL")
        print(f"{flag}  {row['case_id']:30s} steps={row['steps']!s:>4s} t={row['elapsed_s']:>6.1f}s")
    passes = sum(1 for r in rows if r["pass"])
    print(f"\npassed={passes}/{len(rows)}")
    return 0 if passes == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
