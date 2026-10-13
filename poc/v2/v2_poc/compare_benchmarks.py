"""Offline comparison of two V2 benchmark reports. No network or model calls."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED = ("benchmark_version", "configuration", "model", "seed_start", "case_count",
            "cases", "failed", "critical_safety_violations", "source_commit")
CRITICAL = ("critical_safety_violations", "unsupported_accepted_claims")


def load_report(path: str) -> dict:
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(report, dict) or any(k not in report for k in REQUIRED):
        raise ValueError("invalid benchmark report: missing required fields")
    cases = report["cases"]
    if not isinstance(cases, list) or len(cases) != report["case_count"]:
        raise ValueError("invalid benchmark report: case count")
    seeds = [case["seed"] for case in cases]
    if len(set(seeds)) != len(seeds) or any(not isinstance(x, int) for x in seeds):
        raise ValueError("invalid benchmark report: duplicate or invalid seed")
    if sum(not bool(case["passed"]) for case in cases) != report["failed"]:
        raise ValueError("invalid benchmark report: inconsistent failed count")
    if not isinstance(report["critical_safety_violations"], int) or report["critical_safety_violations"] < 0:
        raise ValueError("invalid critical safety count")
    return report


def compare(base: dict, candidate: dict) -> dict:
    for field in ("benchmark_version", "configuration", "model"):
        if base[field] != candidate[field]:
            raise ValueError(f"incompatible {field}; do not compare different configurations")
    old, new = ({case["seed"]: case for case in rep["cases"]} for rep in (base, candidate))
    if old.keys() != new.keys() or not old:
        raise ValueError("seed corpus differs; fixed-seed comparison required")
    newly_failed = sorted(seed for seed in old if old[seed]["passed"] and not new[seed]["passed"])
    recovered = sorted(seed for seed in old if not old[seed]["passed"] and new[seed]["passed"])
    base_unknown = base.get("unsupported_accepted_claims")
    candidate_unknown = candidate.get("unsupported_accepted_claims")
    if base_unknown is not None and (not isinstance(base_unknown, int) or base_unknown < 0):
        raise ValueError("invalid baseline unsupported claim count")
    if candidate_unknown is not None and (not isinstance(candidate_unknown, int) or candidate_unknown < 0):
        raise ValueError("invalid candidate unsupported claim count")
    increased_claims = (base_unknown is not None and candidate_unknown is not None
                        and candidate_unknown > base_unknown)
    regressions = []
    if newly_failed:
        regressions.append("previously passing seeds failed")
    if candidate["critical_safety_violations"] > 0:
        regressions.append("candidate critical safety violations")
    if increased_claims:
        regressions.append("unsupported accepted claims increased")
    unknown_claim_gate = candidate_unknown is None
    return {
        "comparison_version": 1,
        "baseline_commit": base["source_commit"],
        "candidate_commit": candidate["source_commit"],
        "benchmark_version": base["benchmark_version"],
        "configuration": base["configuration"],
        "seed_count": len(old),
        "newly_failed_seeds": newly_failed,
        "recovered_seeds": recovered,
        "baseline_failed": base["failed"],
        "candidate_failed": candidate["failed"],
        "baseline_critical_safety_violations": base["critical_safety_violations"],
        "candidate_critical_safety_violations": candidate["critical_safety_violations"],
        "baseline_unsupported_accepted_claims": base_unknown,
        "candidate_unsupported_accepted_claims": candidate_unknown,
        "unsupported_claim_gate": "not_measured" if unknown_claim_gate else "measured",
        "baseline_p50_case_elapsed_ms": base.get("p50_case_elapsed_ms"),
        "candidate_p50_case_elapsed_ms": candidate.get("p50_case_elapsed_ms"),
        "timing_comparison": "informational_only; environments may differ",
        "regressions": regressions,
        "comparison_passed": not regressions,
        "promotion_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare same-seed offline V2 benchmark reports")
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    args = parser.parse_args(argv)
    try:
        result = compare(load_report(args.baseline), load_report(args.candidate))
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print(f"Comparison unavailable: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"Summary: {result['seed_count']} seeds; {len(result['newly_failed_seeds'])} new failures; "
          f"{result['candidate_critical_safety_violations']} critical safety violations; "
          f"claim gate {result['unsupported_claim_gate']}; "
          f"{'PASS' if result['comparison_passed'] else 'REGRESSION'}", file=sys.stderr)
    return 0 if result["comparison_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
