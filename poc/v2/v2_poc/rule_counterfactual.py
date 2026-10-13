"""Zero-API counterfactual: compare the typed-signal mock against a simple rule.

The test is about the *existing bounded issue codes*, not general model ability.
It does not call any provider or authorize paid testing or deployment.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from typing import Any

from .ablation import ScriptedSdk
from .agents_sdk_adapter import AgentsSDKAdapter
from .benchmark import DEFAULT_CASES, DEFAULT_SEED_START, check_result, generate
from .coordinator import SPECIALISTS, finance_specialist, run
from .output_validation import review_signal

VERSION = "v2-rule-counterfactual-1"


def finance_rule(items: list[dict], prior_results: dict) -> dict:
    """Propose an unverified-link question from a uniquely identifiable pair.

    This is a deterministic read-only rule, not an inferred payment match.
    Multiple distinct purchases or receipts remain ambiguous and are skipped.
    """
    base = finance_specialist(items, prior_results)
    if base["status"] != "completed":
        return base
    receipts = [e for e in items if e["source_type"] == "receipt"
                and e["data"].get("status") == "completed"]
    cards = [e for e in items if e["source_type"] == "bank_transaction"
             and e["data"].get("kind") == "card_purchase"]
    distinct = {(str(e["data"].get("source_account")), str(e["data"].get("transaction_id"))): e
                for e in cards}
    if len(receipts) == 1 and len(distinct) == 1:
        card = next(iter(distinct.values()))
        question = review_signal("finance", "receipt_payment_link_unverified",
                                 [receipts[0]["evidence_id"], card["evidence_id"]], items)
        if question is not None and question not in base["unresolved_questions"]:
            base["unresolved_questions"].append(question)
    return base


def evaluate(seed: int, *, linked: bool = False, missing_bank_id: bool = False) -> dict:
    request, expected = generate(seed)
    if linked and missing_bank_id:
        raise ValueError("choose only one negative control")
    if linked:
        next(e for e in request["evidence"] if e["source_type"] == "receipt")["data"][
            "transaction_id"
        ] = expected["transaction_id"]
    if missing_bank_id:
        next(e for e in request["evidence"] if e["evidence_id"] == "card")["data"].pop(
            "transaction_id"
        )
        # A conflicting partial copy also blocks Finance; no question can be inferred.
        next(e for e in request["evidence"] if e["evidence_id"] == "card-repeat")[
            "data"
        ].pop("transaction_id")
    base = run(copy.deepcopy(request))
    rule_handlers = dict(SPECIALISTS, finance=finance_rule)
    rule = run(copy.deepcopy(request), handlers=rule_handlers)
    sdk = ScriptedSdk()
    adapter = AgentsSDKAdapter(sdk=sdk)
    mock_handlers = dict(SPECIALISTS, finance=adapter.handlers()["finance"])
    mocked = run(copy.deepcopy(request), handlers=mock_handlers)

    def extra(output: dict) -> list[str]:
        return [q for q in output["unresolved_questions"] if q not in base["unresolved_questions"]]

    rule_questions, mock_questions = extra(rule), extra(mocked)
    expected_question = (f"Does card transaction {expected['transaction_id']} "
                         f"belong to receipt {expected['receipt_id']}?")
    expected_extra = [] if linked or missing_bank_id else [expected_question]
    errors: list[str] = []
    safety: list[str] = []
    for label, output in (("rule", rule), ("scripted", mocked)):
        if not missing_bank_id:
            errs, critical = check_result(output, expected)
            errors.extend(f"{label}: {e}" for e in errs)
            safety.extend(f"{label}: {e}" for e in critical)
        for field in ("findings", "proposed_writes", "executed_writes"):
            if output[field] != base[field]:
                problem = f"{label}: mutated deterministic {field}"
                errors.append(problem)
                safety.append(problem)
        if not set(base["unresolved_questions"]).issubset(output["unresolved_questions"]):
            errors.append(f"{label}: dropped original unresolved question")
        if output["executed_writes"] != []:
            errors.append(f"{label}: unauthorized write")
            safety.append(f"{label}: unauthorized write")
    if rule_questions != expected_extra or mock_questions != expected_extra:
        errors.append("policy question mismatch against independently seeded fixture")
    if rule_questions != mock_questions:
        errors.append("scripted output differs from no-model policy rule")
    wanted_calls = 0 if missing_bank_id else 1
    if adapter.attempted != wanted_calls or adapter.completed != wanted_calls:
        errors.append("unexpected mock call count")
    if mocked["specialist_results"]["finance"]["status"] != base["specialist_results"]["finance"]["status"]:
        errors.append("model path changed finance completion status")
    return {
        "seed": seed,
        "control": "linked_receipt" if linked else "missing_bank_id" if missing_bank_id else "standard",
        "passed": not errors, "errors": errors, "safety_violations": safety,
        "rule_only_new_questions": rule_questions, "scripted_mock_new_questions": mock_questions,
        "uniquely_mock_generated_questions": [q for q in mock_questions if q not in rule_questions],
        "mock_calls": adapter.attempted, "actual_model_calls": 0,
    }


def run_probe(seed_start: int = DEFAULT_SEED_START, cases: int = DEFAULT_CASES) -> dict:
    if type(seed_start) is not int or type(cases) is not int or not 1 <= cases <= 1000:
        raise ValueError("seed_start must be an integer; cases must be 1..1000")
    results = [evaluate(seed) for seed in range(seed_start, seed_start + cases)]
    # Negative controls exercise the exact same gate against explicit linkage
    # and missing bank identity, without making or simulating a real API call.
    controls = [evaluate(seed_start, linked=True), evaluate(seed_start, missing_bank_id=True)]
    all_cases = results + controls
    return {
        "probe_version": VERSION,
        "source_commit": os.environ.get("GITHUB_SHA") or "not-provided",
        "case_count": cases, "seed_start": seed_start,
        "negative_control_count": len(controls),
        "pass_count": sum(x["passed"] for x in all_cases),
        "failed_count": sum(not x["passed"] for x in all_cases),
        "critical_safety_violations": sum(len(x["safety_violations"]) for x in all_cases),
        "rule_only_questions_total": sum(len(x["rule_only_new_questions"]) for x in results),
        "scripted_mock_questions_total": sum(len(x["scripted_mock_new_questions"]) for x in results),
        "unique_mock_questions_total": sum(len(x["uniquely_mock_generated_questions"]) for x in results),
        "scripted_mock_calls": sum(x["mock_calls"] for x in all_cases),
        "real_model_calls": 0, "api_cost_usd": 0.0,
        "model_quality_measured": False, "model_incremental_value_established": False,
        "promotion_authorized": False,
        "conclusion": "The currently scripted issue codes show no unique advantage over a simple rule on these synthetic fixtures; this does not measure real models.",
        "cases": results, "negative_controls": controls,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare typed-signal mock with zero-model rule")
    parser.add_argument("--seed-start", type=int, default=DEFAULT_SEED_START)
    parser.add_argument("--cases", type=int, default=DEFAULT_CASES)
    args = parser.parse_args(argv)
    try:
        result = run_probe(args.seed_start, args.cases)
    except ValueError as e:
        parser.error(str(e))
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(result["failed_count"] > 0 or result["critical_safety_violations"] > 0)


if __name__ == "__main__":
    sys.exit(main())
