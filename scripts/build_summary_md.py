"""Generate reports/SUMMARY.md from all per-case reports + reports/summary.json.

The harness's `mavis-eval report` command writes a JSON aggregate. This script
turns that JSON and the per-case report files into a human-readable Markdown
summary suitable for pasting into the demo or sharing with reviewers.

Run from repo root:
    python3 scripts/build_summary_md.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"
SUMMARY_JSON = REPORTS_DIR / "summary.json"
SUMMARY_MD = REPORTS_DIR / "SUMMARY.md"


def load_per_case_reports() -> list[dict]:
    """Load per-case reports, skipping anything that isn't a real case report.

    mavis-eval's `report` command globs reports/*.json itself, which means if
    summary.json is left in the directory from a prior run, it gets ingested
    as if it were a case (with no case_id / difficulty) and shows up as a
    spurious "<missing>" row in every slice. Filtering by presence of case_id
    catches that and any other accidental JSON in the dir.
    """
    items = []
    for p in sorted(REPORTS_DIR.glob("*.json")):
        if p.name in {"summary.json"}:
            continue
        try:
            r = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        if not r.get("case_id"):
            continue
        items.append(r)
    return items


def render_slice_table(slices: dict, label: str) -> str:
    if not slices:
        return f"_(no {label} data)_\n"
    rows = ["| " + label + " | n | PASS | rate | Wilson 95% CI |", "|---|---|---|---|---|"]
    for key, stats in sorted(slices.items(), key=lambda kv: -kv[1].get("n", 0)):
        n = stats.get("n", 0)
        pc = stats.get("pass_count", 0)
        rate = stats.get("pass_rate", 0.0)
        ci = stats.get("wilson_95_ci") or [0, 0]
        rows.append(f"| {key} | {n} | {pc} | {rate:.0%} | [{ci[0]:.2f}, {ci[1]:.2f}] |")
    return "\n".join(rows) + "\n"


def top_failure(report: dict) -> str:
    assertions = report.get("assertions", {})
    for key in ("failed_gates", "failed_quality_assertions"):
        failures = assertions.get(key, [])
        if failures:
            return failures[0].get("message", "")[:80]
    for redline in assertions.get("safety_redlines", []):
        if not redline.get("passed", True):
            return redline.get("message", "")[:80]
    return ""


def main() -> int:
    if not SUMMARY_JSON.exists():
        print(f"ERROR: {SUMMARY_JSON} missing. Run `python3 -m mavis_eval report reports --out reports/summary.json` first.")
        return 1

    summary = json.loads(SUMMARY_JSON.read_text())
    reports = load_per_case_reports()

    total = len(reports)
    n_pass = sum(1 for r in reports if r.get("pass"))
    n_fail = total - n_pass
    pass_rate = n_pass / total if total else 0.0

    lines: list[str] = []
    lines.append("# Mavis-Eval Summary Report\n")
    lines.append(f"**{total} cases evaluated · {n_pass} PASS · {n_fail} FAIL · pass rate = {pass_rate:.1%}**\n")
    lines.append("Deterministic evaluation only (L1 gating + L2 quality). LLM judge (L3) is not part of these numbers.\n")

    lines.append("## Per-case results\n")
    lines.append("| case_id | difficulty | scenario | gating | quality | final | top failure |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in sorted(reports, key=lambda x: (not x.get("pass"), x.get("case_id", ""))):
        cid = r.get("case_id", "?")
        diff = r.get("difficulty", "?")
        scen = r.get("scenario", "?")
        gp = "✓" if r.get("gating_pass") else "✗"
        qp = "✓" if r.get("quality_pass", True) else "✗"
        fp = "✓ PASS" if r.get("pass") else "✗ FAIL"
        msg = top_failure(r)
        lines.append(f"| `{cid}` | {diff} | {scen} | {gp} | {qp} | {fp} | {msg} |")
    lines.append("")

    lines.append("## By difficulty\n")
    lines.append(render_slice_table(summary.get("by_difficulty", {}), "difficulty"))

    lines.append("## By scenario\n")
    lines.append(render_slice_table(summary.get("by_scenario", {}), "scenario"))

    lines.append("## By economic sector (GDPval slice)\n")
    lines.append(render_slice_table(summary.get("by_economic_sector", {}), "sector"))

    lines.append("## By occupation\n")
    lines.append(render_slice_table(summary.get("by_occupation", {}), "occupation"))

    SUMMARY_MD.write_text("\n".join(lines))
    print(f"Wrote {SUMMARY_MD}  ({SUMMARY_MD.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
