"""Offline 0/1/3 specialist ablation using scripted SDK responses only.

No actual AI model is called. This measures routing overhead, evidence-gate
behavior and additional policy-authored questions, NOT model quality or billing.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import statistics
import sys
import time
from types import SimpleNamespace

from .agents_sdk_adapter import AIAssessment, AIReviewSignal, AgentsSDKAdapter
from .benchmark import BENCHMARK_VERSION, DEFAULT_CASES, DEFAULT_SEED_START, check_result, generate
from .coordinator import DOMAINS, SPECIALISTS, run

VERSION = "v2-scripted-ablation-1"
VARIANTS = {
    "deterministic": (),
    "one_finance_mock": ("finance",),
    "three_specialist_mock": DOMAINS,
}


class ScriptedSdk:
    """Minimal, fully offline SDK interface; deterministic responses by domain."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.Runner = SimpleNamespace(run_sync=self.run_sync)

    @staticmethod
    def Agent(**kwargs):
        return SimpleNamespace(**kwargs)

    @staticmethod
    def RunConfig(**kwargs):
        return SimpleNamespace(**kwargs)

    def run_sync(self, agent, prompt, *, max_turns, run_config):
        if max_turns != 1 or not run_config.tracing_disabled or agent.tools or agent.handoffs:
            raise AssertionError("SDK call was not bounded and tool-free")
        payload = json.loads(prompt)
        evidence = payload["evidence"]
        if any(not e["source_locator"].startswith("fixture://") for e in evidence):
            raise AssertionError("nonfictional source entered scripted adapter")
        domain = agent.name.removeprefix("V2 ").removesuffix(" specialist")
        if domain not in DOMAINS:
            raise AssertionError("unexpected domain")
        if domain != "finance" and any(e["source_type"] == "bank_transaction" for e in evidence):
            raise AssertionError("bank evidence leaked outside finance")
        if domain == "home" and payload["prior_purchase_result"]["domain_owner"] != "purchase":
            raise AssertionError("Home dependency was not preserved")
        if domain != "home" and payload["prior_purchase_result"] is not None:
            raise AssertionError("unnecessary prior-domain information shared")
        self.calls.append({"domain": domain, "evidence_ids": [e["evidence_id"] for e in evidence]})
        receipts = [e for e in evidence if e["source_type"] == "receipt"]
        cards = [e for e in evidence if e["source_type"] == "bank_transaction"
                 and e["data"].get("kind") == "card_purchase"]
        signals = []
        if domain in {"purchase", "home"} and receipts:
            signals = [AIReviewSignal(code="delivery_unconfirmed",
                                      evidence_ids=[receipts[0]["evidence_id"]])]
        elif domain == "finance" and receipts and cards:
            signals = [AIReviewSignal(code="receipt_payment_link_unverified",
                                      evidence_ids=[receipts[0]["evidence_id"], cards[0]["evidence_id"]])]
        return SimpleNamespace(final_output=AIAssessment(signals=signals))


def evaluate_case(seed: int, variant: str, *, sdk_factory=ScriptedSdk) -> dict:
    """Evaluate same fixture, independent oracle and synthetic model boundary."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown ablation variant: {variant}")
    request, expected = generate(seed)
    started = time.perf_counter()
    sdk = sdk_factory()
    enabled = VARIANTS[variant]
    errors: list[str] = []
    critical: list[str] = []
    new_questions: list[str] = []
    attempted = completed = 0
    try:
        deterministic = run(copy.deepcopy(request))
        if enabled:
            adapter = AgentsSDKAdapter(sdk=sdk)
            handlers = dict(SPECIALISTS)
            for domain in enabled:
                handlers[domain] = adapter.handlers()[domain]
            candidate = run(copy.deepcopy(request), handlers=handlers)
            attempted, completed = adapter.attempted, adapter.completed
        else:
            candidate = run(copy.deepcopy(request))
        checks, safety = check_result(candidate, expected)
        errors.extend(checks)
        critical.extend(safety)
        if candidate["findings"] != deterministic["findings"] or candidate["proposed_writes"] != deterministic["proposed_writes"]:
            errors.append("model path altered deterministic facts or write proposals")
            critical.append("model path altered deterministic facts or write proposals")
        if candidate["executed_writes"] != []:
            errors.append("external write observed")
            critical.append("external write observed")
        new_questions = [q for q in candidate["unresolved_questions"]
                         if q not in deterministic["unresolved_questions"]]
        expected_question = (f"Does card transaction {expected['transaction_id']} "
                             f"belong to receipt {expected['receipt_id']}?")
        expected_new = [expected_question] if "finance" in enabled else []
        if new_questions != expected_new:
            errors.append("added questions differ from independent fixture expectation")
        if attempted != len(enabled) or completed != len(enabled) or len(sdk.calls) != len(enabled):
            errors.append("mocked specialist call counts mismatch")
        if set(x["domain"] for x in sdk.calls) != set(enabled):
            errors.append("wrong mocked specialist routing")
        for domain in enabled:
            review = candidate["specialist_results"][domain].get("model_review", {})
            if review.get("free_text_claims_accepted") != 0 or review.get("rejected_model_items") != 0:
                errors.append("scripted model output not fully evidence-gated")
                critical.append("scripted model output not fully evidence-gated")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    return {
        "seed": seed, "passed": not errors, "errors": errors,
        "safety_violations": critical, "mock_calls_attempted": attempted,
        "mock_calls_completed": completed,
        "additional_policy_questions": len(new_questions),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def run_ablation(seed_start: int = DEFAULT_SEED_START, cases: int = DEFAULT_CASES) -> dict:
    if cases < 1 or cases > 1000 or type(seed_start) is not int:
        raise ValueError("cases must be 1..1000 and seed_start must be an integer")
    variants: dict[str, dict] = {}
    for name in VARIANTS:
        results = [evaluate_case(seed, name) for seed in range(seed_start, seed_start + cases)]
        variants[name] = {
            "cases": results,
            "passed": sum(x["passed"] for x in results),
            "failed": sum(not x["passed"] for x in results),
            "critical_safety_violations": sum(len(x["safety_violations"]) for x in results),
            "mock_calls_attempted": sum(x["mock_calls_attempted"] for x in results),
            "mock_calls_completed": sum(x["mock_calls_completed"] for x in results),
            "additional_policy_questions": sum(x["additional_policy_questions"] for x in results),
            "p50_fixture_elapsed_ms": round(statistics.median(x["elapsed_ms"] for x in results), 3),
        }
    return {
        "ablation_version": VERSION,
        "golden_benchmark_version": BENCHMARK_VERSION,
        "source_provenance": {
            "pr_head_sha": os.environ.get("PR_HEAD_SHA") or None,
            "tested_merge_sha": os.environ.get("GITHUB_SHA") or None,
            "base_sha": os.environ.get("PR_BASE_SHA") or None,
        },
        "seed_start": seed_start, "case_count": cases,
        "scenario": "scripted_typed_signals_for_fixture_only",
        "sdk_mode": "offline_fake_sdk",
        "real_model_calls": 0, "api_cost_usd": 0.0,
        "provider_model_latency_ms": None,
        "provider_model_token_usage": None,
        "estimated_real_model_cost_usd": None,
        "real_model_quality_established": False,
        "promotion_authorized": False,
        "variants": variants,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline scripted 0/1/3 specialist ablation")
    parser.add_argument("--seed-start", type=int, default=DEFAULT_SEED_START)
    parser.add_argument("--cases", type=int, default=DEFAULT_CASES)
    args = parser.parse_args(argv)
    try:
        report = run_ablation(args.seed_start, args.cases)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return int(any(v["failed"] or v["critical_safety_violations"]
                   for v in report["variants"].values()))


if __name__ == "__main__":
    sys.exit(main())
