"""Validate and compare offline benchmark reports; no network or model calls."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED = (
    "benchmark_version", "benchmark_contract", "configuration", "model",
    "seed_start", "case_count", "cases", "passed", "failed",
    "critical_safety_violations", "metamorphic_checks_run", "source_commit",
    "source_provenance", "unsupported_accepted_claims",
)
CONTRACT_FIELDS = ("contract_version", "fixture_revision", "oracle_revision",
                   "metamorphic_revision", "checks_per_case")
SHA = re.compile(r"[a-fA-F0-9]{40}\Z")


def _count(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid {label}: expected nonnegative integer")
    return value


def validate_report(report: dict) -> None:
    """Fail closed on contradictory, incomplete or incomparable result evidence."""
    if not isinstance(report, dict) or any(key not in report for key in REQUIRED):
        raise ValueError("invalid benchmark report: missing required fields")
    contract = report["benchmark_contract"]
    if not isinstance(contract, dict) or any(
        key not in contract for key in CONTRACT_FIELDS
    ):
        raise ValueError("invalid benchmark contract metadata")
    if any(not isinstance(contract[key], str) or not contract[key].strip()
           for key in CONTRACT_FIELDS[:-1]):
        raise ValueError("invalid contract revision")
    checks_per_case = _count(contract["checks_per_case"], "checks_per_case")
    if not checks_per_case:
        raise ValueError("checks_per_case must be positive")
    if contract["contract_version"] != report["benchmark_version"]:
        raise ValueError("benchmark version and contract version differ")

    count = _count(report["case_count"], "case_count")
    start = _count(report["seed_start"], "seed_start")
    if count < 1 or count > 1000:
        raise ValueError("invalid case count")
    cases = report["cases"]
    if not isinstance(cases, list) or len(cases) != count:
        raise ValueError("invalid benchmark report: case count")
    seeds = []
    passed = safety_total = metamorphic_total = 0
    for case in cases:
        if not isinstance(case, dict) or type(case.get("seed")) is not int:
            raise ValueError("invalid case seed")
        seeds.append(case["seed"])
        if type(case.get("passed")) is not bool:
            raise ValueError("case passed must be boolean")
        errors, violations = case.get("errors"), case.get("safety_violations")
        if not all(isinstance(x, list) and all(isinstance(s, str) and s for s in x)
                   for x in (errors, violations)):
            raise ValueError("invalid case error or safety arrays")
        if case["passed"] and (errors or violations):
            raise ValueError("passed case contains unresolved errors or safety violations")
        if not case["passed"] and not errors:
            raise ValueError("failed case lacks failure evidence")
        if any(v not in errors for v in violations):
            raise ValueError("safety violation missing from case errors")
        checks = _count(case.get("metamorphic_checks"), "case metamorphic_checks")
        if checks != checks_per_case:
            raise ValueError("incomplete metamorphic coverage for case")
        metamorphic_total += checks
        safety_total += len(violations)
        passed += int(case["passed"])
    if sorted(seeds) != list(range(start, start + count)):
        raise ValueError("seed corpus inconsistent with seed_start/case_count")
    if passed != _count(report["passed"], "passed") or count - passed != _count(report["failed"], "failed"):
        raise ValueError("invalid benchmark report: inconsistent pass/fail totals")
    if safety_total != _count(report["critical_safety_violations"], "critical_safety_violations"):
        raise ValueError("critical safety count contradicts per-case evidence")
    if metamorphic_total != _count(report["metamorphic_checks_run"], "metamorphic_checks_run"):
        raise ValueError("metamorphic count contradicts per-case evidence")

    claims = report["unsupported_accepted_claims"]
    if claims is not None:
        _count(claims, "unsupported_accepted_claims")
    provenance = report["source_provenance"]
    if not isinstance(provenance, dict) or any(
        key not in provenance for key in ("pr_head_sha", "tested_merge_sha", "base_sha")
    ):
        raise ValueError("invalid source provenance")
    for key in ("pr_head_sha", "tested_merge_sha", "base_sha"):
        sha = provenance[key]
        if sha is not None and (not isinstance(sha, str) or not SHA.fullmatch(sha)):
            raise ValueError(f"invalid source provenance: {key}")
    tested = provenance["tested_merge_sha"]
    if tested is not None and report["source_commit"] != tested:
        raise ValueError("source_commit contradicts tested merge SHA")


def load_report(path: str) -> dict:
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_report(report)
    return report


def compare(base: dict, candidate: dict) -> dict:
    validate_report(base)
    validate_report(candidate)
    for field in ("benchmark_version", "benchmark_contract", "configuration", "model"):
        if base[field] != candidate[field]:
            raise ValueError(f"incompatible {field}; do not compare different benchmark contracts")
    old, new = ({case["seed"]: case for case in rep["cases"]} for rep in (base, candidate))
    if old.keys() != new.keys() or not old:
        raise ValueError("seed corpus differs; fixed-seed comparison required")
    newly_failed = sorted(seed for seed in old if old[seed]["passed"] and not new[seed]["passed"])
    recovered = sorted(seed for seed in old if not old[seed]["passed"] and new[seed]["passed"])
    base_claims = base["unsupported_accepted_claims"]
    candidate_claims = candidate["unsupported_accepted_claims"]
    regressions = []
    if newly_failed or candidate["failed"]:
        regressions.append("candidate golden-journey failures")
    if candidate["critical_safety_violations"]:
        regressions.append("candidate critical safety violations")
    # A known violation is unacceptable even when the historical baseline did not measure it.
    if candidate_claims is not None and candidate_claims > 0:
        regressions.append("candidate unsupported accepted claims")
    if candidate_claims is None:
        claim_gate = "not_measured"
    elif base_claims is None:
        claim_gate = "candidate_measured_baseline_unknown"
    else:
        claim_gate = "measured"
    return {
        "comparison_version": 2,
        "baseline_commit": base["source_commit"],
        "candidate_commit": candidate["source_commit"],
        "baseline_provenance": base["source_provenance"],
        "candidate_provenance": candidate["source_provenance"],
        "benchmark_version": base["benchmark_version"],
        "benchmark_contract": base["benchmark_contract"],
        "configuration": base["configuration"],
        "seed_count": len(old),
        "metamorphic_checks": candidate["metamorphic_checks_run"],
        "newly_failed_seeds": newly_failed,
        "recovered_seeds": recovered,
        "baseline_failed": base["failed"],
        "candidate_failed": candidate["failed"],
        "baseline_critical_safety_violations": base["critical_safety_violations"],
        "candidate_critical_safety_violations": candidate["critical_safety_violations"],
        "baseline_unsupported_accepted_claims": base_claims,
        "candidate_unsupported_accepted_claims": candidate_claims,
        "unsupported_claim_gate": claim_gate,
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
