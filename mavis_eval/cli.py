from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evaluator import build_judge_payload, evaluate_case, load_json, write_json
from .reporting import compare_reports, load_reports, summarize_reports
from .schema import load_case_documents, validate_case, validate_cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mavis-eval")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate case JSON files")
    validate_parser.add_argument("paths", nargs="+", type=Path)

    list_parser = subparsers.add_parser("list-cases", help="List case IDs from case JSON files")
    list_parser.add_argument("paths", nargs="+", type=Path)

    eval_parser = subparsers.add_parser("evaluate", help="Evaluate one run directory for one case")
    eval_parser.add_argument("case", type=Path)
    eval_parser.add_argument("--case-id", help="Case ID when the case file contains an array")
    eval_parser.add_argument("--run-dir", required=True, type=Path)
    eval_parser.add_argument("--judge-result", type=Path)
    eval_parser.add_argument("--deterministic-only", action="store_true")
    eval_parser.add_argument("--out", type=Path)

    judge_parser = subparsers.add_parser("judge-payload", help="Build JSON evidence package for a judge agent")
    judge_parser.add_argument("case", type=Path)
    judge_parser.add_argument("--case-id", help="Case ID when the case file contains an array")
    judge_parser.add_argument("--run-dir", required=True, type=Path)
    judge_parser.add_argument("--out", required=True, type=Path)

    report_parser = subparsers.add_parser("report", help="Aggregate run reports")
    report_parser.add_argument("reports", nargs="+", type=Path)
    report_parser.add_argument("--out", type=Path)

    compare_parser = subparsers.add_parser("compare", help="Compare prior and new report sets")
    compare_parser.add_argument("--prior", required=True, nargs="+", type=Path)
    compare_parser.add_argument("--new", required=True, nargs="+", type=Path)
    compare_parser.add_argument("--out", type=Path)

    run_parser = subparsers.add_parser(
        "run-mavis",
        help="Launch local Mavis CLI against a case and evaluate deterministically.",
    )
    run_parser.add_argument("case", type=Path)
    run_parser.add_argument("--case-id", required=True)
    run_parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    run_parser.add_argument("--reports-root", type=Path, default=Path("reports"))
    run_parser.add_argument("--fixtures-root", type=Path, default=None)
    run_parser.add_argument("--cli-path", default=None)
    run_parser.add_argument("--agent", default="mavis")
    run_parser.add_argument("--model", default=None)
    run_parser.add_argument("--timeout-s", type=float, default=900.0)
    run_parser.add_argument("--poll-interval-s", type=float, default=2.0)
    run_parser.add_argument("--prompt-suffix", default="")

    args = parser.parse_args(argv)

    if args.command == "validate":
        return _validate(args.paths)
    if args.command == "list-cases":
        return _list_cases(args.paths)
    if args.command == "evaluate":
        return _evaluate(args)
    if args.command == "judge-payload":
        return _judge_payload(args)
    if args.command == "report":
        return _report(args)
    if args.command == "compare":
        return _compare(args)
    if args.command == "run-mavis":
        return _run_mavis(args)
    parser.error(f"unknown command {args.command}")
    return 2


def _validate(paths: list[Path]) -> int:
    issues = validate_cases(paths)
    if issues:
        for issue in issues:
            print(issue.render(), file=sys.stderr)
        return 1
    print(f"Validated {len(paths)} path(s) successfully.")
    return 0


def _list_cases(paths: list[Path]) -> int:
    for path in paths:
        for file in _case_files(path):
            for case, source in load_case_documents(file):
                print(f"{case.get('case_id', '<missing>')}\t{case.get('difficulty', '')}\t{case.get('scenario', '')}\t{source}")
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    case = _select_case(args.case, args.case_id)
    issues = validate_case(case, str(args.case))
    if issues:
        for issue in issues:
            print(issue.render(), file=sys.stderr)
        return 1
    judge_result = load_json(args.judge_result) if args.judge_result else None
    report = evaluate_case(case, args.run_dir, judge_result=judge_result, deterministic_only=args.deterministic_only)
    if args.out:
        write_json(args.out, report)
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["final_decision_available"] else 1


def _judge_payload(args: argparse.Namespace) -> int:
    case = _select_case(args.case, args.case_id)
    issues = validate_case(case, str(args.case))
    if issues:
        for issue in issues:
            print(issue.render(), file=sys.stderr)
        return 1
    payload = build_judge_payload(case, args.run_dir)
    write_json(args.out, payload)
    return 0


def _report(args: argparse.Namespace) -> int:
    summary = summarize_reports(load_reports(args.reports))
    if args.out:
        write_json(args.out, summary)
    else:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _run_mavis(args: argparse.Namespace) -> int:
    from .adapters.mavis_runner import RunnerConfig, run_case

    config = RunnerConfig(
        case_file=args.case,
        case_id=args.case_id,
        runs_root=args.runs_root,
        reports_root=args.reports_root,
        fixtures_root=args.fixtures_root,
        cli_path=args.cli_path,
        agent=args.agent,
        model=args.model,
        timeout_s=args.timeout_s,
        poll_interval_s=args.poll_interval_s,
        extra_prompt_suffix=args.prompt_suffix,
        deterministic_only=True,
    )
    result = run_case(config)
    summary = {
        "case_id": result.case_id,
        "session_id": result.session_id,
        "run_dir": str(result.run_dir),
        "report_path": str(result.report_path),
        "duration_s": round(result.duration_s, 2),
        "trajectory_steps": result.trajectory_steps,
        "cli_path": result.cli_path,
        "pass": result.report.get("pass"),
        "gating_pass": result.report.get("gating_pass"),
        "safety_redline": result.report.get("safety_redline"),
        "failures": result.failures,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if result.report.get("pass") else 1


def _compare(args: argparse.Namespace) -> int:
    comparison = compare_reports(load_reports(args.prior), load_reports(args.new))
    if args.out:
        write_json(args.out, comparison)
    else:
        print(json.dumps(comparison, indent=2, sort_keys=True))
    return 0


def _select_case(path: Path, case_id: str | None) -> dict:
    docs = load_case_documents(path)
    if len(docs) == 1 and case_id is None:
        return docs[0][0]
    if case_id is None:
        raise SystemExit(f"{path} contains multiple cases; pass --case-id")
    for case, _source in docs:
        if case.get("case_id") == case_id:
            return case
    raise SystemExit(f"case_id '{case_id}' not found in {path}")


def _case_files(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.rglob("*.json"))
    return [path]
