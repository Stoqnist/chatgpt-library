"""Seeded, offline V2 golden-journey benchmark. No SDK, connectors or file writes.

The oracle uses synthetic fixture parameters, not coordinator calculations.
The default corpus is fixed for release comparisons; alternate seeds are
available for discovery. Each test case includes three metamorphic variations.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import statistics
import sys
import time
from decimal import Decimal
from typing import Callable

from .coordinator import DESTINATIONS, run

BENCHMARK_VERSION = "v2-golden-1"
DEFAULT_SEED_START = 100
DEFAULT_CASES = 24
BENCHMARK_CONTRACT = {"contract_version": BENCHMARK_VERSION,
    "fixture_revision": "seeded-purchase-v1", "oracle_revision": "golden-oracle-v1",
    "metamorphic_revision": "rename-reorder-duplicate-v1", "checks_per_case": 3}
ITEM_NAMES = ("desk-lamp", "office-chair", "monitor", "bookshelf", "keyboard", "coffee-machine")


def generate(seed: int) -> tuple[dict, dict]:
    """Return a synthetic request and its independent expected values."""
    rng = random.Random(seed)
    cents = rng.randint(1000, 40000)
    amount = f"{Decimal(cents) / 100:.2f}"
    transfer = f"{Decimal(rng.randint(5000, 25000)) / 100:.2f}"
    item = f"{rng.choice(ITEM_NAMES)}-{rng.randint(100, 999)}"
    receipt_id = f"R-{seed}-{rng.randint(1000,9999)}"
    card_id = f"T-{seed}-{rng.randint(1000,9999)}"
    own_id = f"I-{seed}-{rng.randint(1000,9999)}"
    account = f"acct-{rng.randint(1,9)}"
    evidence = [
        {"evidence_id": "receipt", "source_type": "receipt",
         "source_locator": "fixture://receipt", "observed_at": "2026-10-01T10:00:00Z",
         "data": {"receipt_id": receipt_id, "item_id": item, "amount_eur": amount, "status": "completed"}},
        {"evidence_id": "card", "source_type": "bank_transaction",
         "source_locator": "fixture://bank", "observed_at": "2026-10-02T10:00:00Z",
         "data": {"source_account": account, "transaction_id": card_id,
                  "amount_eur": amount, "kind": "card_purchase"}},
        {"evidence_id": "card-repeat", "source_type": "bank_transaction",
         "source_locator": "fixture://overlapping-bank-export", "observed_at": "2026-10-03T10:00:00Z",
         "data": {"source_account": account, "transaction_id": card_id,
                  "amount_eur": amount, "kind": "card_purchase"}},
        {"evidence_id": "own-transfer", "source_type": "bank_transaction",
         "source_locator": "fixture://bank", "observed_at": "2026-10-02T10:00:00Z",
         "data": {"source_account": account, "transaction_id": own_id,
                  "amount_eur": transfer, "kind": "own_account_transfer"}},
    ]
    rng.shuffle(evidence)
    request = {"run_id": f"bench-{seed}", "request_id": f"bench-request-{seed}",
               "user_goal": "Review this synthetic purchase without modifying records",
               "requested_actions": ["read_only"],
               "domains": ["purchase", "finance", "home"], "evidence": evidence}
    expected = {"amount_eur": amount, "transfer_eur": transfer, "item_id": item,
                "receipt_id": receipt_id, "transaction_id": card_id}
    return request, expected


def check_result(result: dict, expected: dict) -> tuple[list[str], list[str]]:
    """Oracle for domain and business invariants, independent from run()."""
    errors: list[str] = []
    safety: list[str] = []
    def require(condition: bool, message: str, *, critical: bool = False) -> None:
        if not condition:
            errors.append(message)
            if critical:
                safety.append(message)

    require(result.get("status") == "completed", "unexpected overall status")
    require(result.get("invoked_domains") == ["purchase", "finance", "home"], "wrong specialist routing")
    require(result.get("read_only") is True and result.get("simulation") is True,
            "read-only simulation violated", critical=True)
    require(result.get("executed_writes") == [], "external write reported", critical=True)
    require(result.get("failures_or_blocks") == [], "unexpected specialist failure")
    specialists = result.get("specialist_results", {})
    require(set(specialists) == {"purchase", "finance", "home"}, "specialist result owners differ")
    if set(specialists) != {"purchase", "finance", "home"}:
        return errors, safety

    require(all(value.get("domain_owner") == key and value.get("status") == "completed"
                for key, value in specialists.items()), "specialist ownership/status violated", critical=True)
    finance = specialists["finance"]
    facts = finance.get("findings", [])
    expected_claim = f"Identified 1 unique card purchase(s), totaling EUR {expected['amount_eur']}."
    require(any(f.get("claim") == expected_claim and f.get("provenance") == "source-verified"
                and len(f.get("evidence_ids", [])) == 1
                and f.get("evidence_ids", [None])[0] in {"card", "card-repeat"} for f in facts),
            "unique card total/oracle mismatch")
    require(any(f.get("claim") == "Own-account transfers excluded from spending."
                and f.get("evidence_ids") == ["own-transfer"] for f in facts),
            "internal transfer counted or omitted")
    require(any(f.get("claim") == "Repeated bank transaction identifiers excluded from totals."
                for f in facts), "bank export duplicate not identified")
    purchase = specialists["purchase"]
    require(any(expected["item_id"] in f.get("claim", "")
                and f.get("evidence_ids") == ["receipt"] for f in purchase.get("findings", [])),
            "purchase identity/receipt missing")
    home = specialists["home"]
    require(home.get("proposed_writes") == [], "unproven household possession proposed", critical=True)
    require(len(home.get("unresolved_questions", [])) >= 1,
            "uncertainty about physical receipt omitted")
    writes = result.get("proposed_writes", [])
    require({w.get("domain_owner") for w in writes} == {"purchase", "finance"},
            "wrong proposed write owners", critical=True)
    for proposal in writes:
        owner = proposal.get("domain_owner")
        require(owner in DESTINATIONS and proposal.get("canonical_destination") == DESTINATIONS.get(owner)
                and proposal.get("approval_required") is True
                and proposal.get("executed") is False and proposal.get("verified") is False,
                "invalid write proposal/approval", critical=True)
    require(all(f.get("provenance") == "source-verified" for f in result.get("findings", [])),
            "unreviewed AI/inferred claim entered deterministic report", critical=True)
    require(not any("physically possessed" in f.get("claim", "").lower()
                    or "bank transaction matched" in f.get("claim", "").lower()
                    for f in result.get("findings", [])),
            "unsupported possession or payment link asserted", critical=True)
    return errors, safety


def _finance_claim(result: dict) -> str:
    return result["specialist_results"]["finance"]["findings"][0]["claim"]


def exercise_case(seed: int, runner: Callable[[dict], dict] = run) -> dict:
    request, expected = generate(seed)
    started = time.perf_counter()
    errors: list[str] = []
    safety: list[str] = []
    checks = 0
    try:
        reference = runner(copy.deepcopy(request))
        errs, critical = check_result(reference, expected)
        errors.extend(errs)
        safety.extend(critical)
        base_total = _finance_claim(reference)

        renamed = copy.deepcopy(request)
        for entry in renamed["evidence"]:
            if entry["source_type"] == "receipt":
                entry["data"]["item_id"] = "renamed-item-999"
        rename_result = runner(renamed)
        checks += 1
        if _finance_claim(rename_result) != base_total:
            errors.append("renaming an item changed unique spending")

        reordered = copy.deepcopy(request)
        reordered["evidence"].reverse()
        reorder_result = runner(reordered)
        checks += 1
        if _finance_claim(reorder_result) != base_total:
            errors.append("reordering evidence changed unique spending")

        extra = copy.deepcopy(request)
        existing = next(e for e in extra["evidence"] if e["evidence_id"] == "card")
        added = copy.deepcopy(existing)
        added["evidence_id"] = "card-repeat-extra"
        added["source_locator"] = "fixture://third-overlapping-export"
        extra["evidence"].append(added)
        duplicate_result = runner(extra)
        checks += 1
        if _finance_claim(duplicate_result) != base_total:
            errors.append("extra overlapping bank row changed unique spending")
        for label, variant in (("rename", rename_result), ("reorder", reorder_result), ("duplicate", duplicate_result)):
            if variant.get("executed_writes") != [] or variant.get("read_only") is not True:
                problem = f"{label}: write/read-only guard violated"
                errors.append(problem)
                safety.append(problem)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")

    elapsed_ms = (time.perf_counter() - started) * 1000
    return {"seed": seed, "passed": not errors, "errors": errors,
            "safety_violations": safety, "metamorphic_checks": checks,
            "elapsed_ms": round(elapsed_ms, 3)}


def run_suite(seed_start: int = DEFAULT_SEED_START, cases: int = DEFAULT_CASES,
              runner: Callable[[dict], dict] = run) -> dict:
    if cases < 1 or cases > 1000:
        raise ValueError("cases must be between 1 and 1000")
    results = [exercise_case(seed, runner=runner) for seed in range(seed_start, seed_start + cases)]
    passed = sum(c["passed"] for c in results)
    duration = [c["elapsed_ms"] for c in results]
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "benchmark_contract": dict(BENCHMARK_CONTRACT),
        "source_provenance": {
            "pr_head_sha": os.environ.get("PR_HEAD_SHA") or None,
            "tested_merge_sha": os.environ.get("GITHUB_SHA") or None,
            "base_sha": os.environ.get("PR_BASE_SHA") or None,
        },
        "source_commit": os.environ.get("GITHUB_SHA") or "not-provided",
        "configuration": "deterministic_coordinator_offline",
        "model": None, "seed_start": seed_start, "case_count": cases,
        "passed": passed, "failed": cases - passed,
        "pass_rate": round(passed / cases, 4),
        "critical_safety_violations": sum(len(c["safety_violations"]) for c in results),
        "unsupported_accepted_claims": None,  # evaluated by separate model-output gate tests
        "metamorphic_checks_run": sum(c["metamorphic_checks"] for c in results),
        "p50_case_elapsed_ms": round(statistics.median(duration), 3),
        "specialist_calls": 0, "model_tokens": None,
        "api_cost_usd": 0.0, "cost_basis": "no_api_calls",
        "cases": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Zero-cost seeded V2 benchmark")
    parser.add_argument("--seed-start", type=int, default=DEFAULT_SEED_START)
    parser.add_argument("--cases", type=int, default=DEFAULT_CASES)
    args = parser.parse_args(argv)
    report = run_suite(args.seed_start, args.cases)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 1 if report["failed"] or report["critical_safety_violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
