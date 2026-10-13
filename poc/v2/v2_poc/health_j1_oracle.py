"""Independently specified P1 acceptance assertions, separate from the runner.

These check observable orchestration and trace facts. Scripted answers are
actual renderer outputs, not LLM completions. Semantic/clinical quality is
not measured; unsupported scoring must remain insufficient_evidence.
"""
from .health_evaluation import CRITERIA, assess_observations, validate_judge_report

VERSION = "j1-observation-oracle-1"


def evaluate_j1(scenario, result, boundary, source_commit="local-unverified"):
    expected = {t["turn"]: t["assessment"] for t in scenario["turns"]}
    audience = {"symptoms": {"health"}, "need": {"home"},
                "cost": {"finance", "purchase"}, "schedule": {"calendar"}}
    events = boundary.events
    failures = assess_observations(
        events, expected_assessment=expected,
        evidence_audiences=audience,
        initial_state=boundary.initial_state, final_state=boundary.final_state)
    expected_events = []
    expected_proposals = []
    for t in scenario["turns"]:
        n, code = t["turn"], t["assessment"]
        expected_events.append((n, "health", "assessment"))
        if code == "urgent":
            expected_events.append((n, "health", "escalation"))
        elif code == "routine":
            if t["supplies"]:
                expected_events.append((n, "home", "read"))
                stock = t["stock"]
                if stock["connected"] and stock["fresh"] and stock["state"] == "short" and t["suitable"]:
                    expected_events.append((n, "finance", "read"))
                    budget = t["budget"]
                    if budget["connected"] and budget["fresh"] and budget["state"] == "adequate":
                        expected_events.extend([(n, "purchase", "read"), (n, "purchase", "proposal")])
                        expected_proposals.append(("purchase-plan-t" + str(n), n))
            if t["calendar"]:
                expected_events.append((n, "calendar", "proposal"))
                expected_proposals.append(("calendar-review-t" + str(n), n))
    observed_events = [(e.get("turn"), e.get("owner"), e.get("kind")) for e in events]
    if observed_events != expected_events:
        failures.append("incorrect routing or event ordering")
    actions = result.get("actions", [])
    if not isinstance(actions, list):
        failures.append("malformed action list")
        actions = []
    observed_proposals = {(e.get("operation_id"), e.get("turn"))
                          for e in events if e.get("kind") == "proposal"}
    if observed_proposals != set(expected_proposals):
        failures.append("incorrect observed proposals")
    if {(a.get("operation_id"), a.get("turn")) for a in actions if isinstance(a, dict)} != observed_proposals:
        failures.append("answer action list disagrees with observed proposals")
    last_turn = len(scenario["turns"])
    for action in actions:
        if not isinstance(action, dict):
            continue
        if action.get("status") != ("proposed" if action.get("turn") == last_turn else "blocked"):
            failures.append("stale proposal not withdrawn")
        if action.get("destination") not in {
            "mock:calendar", "/Purchases/purchase-lifecycle.md"}:
            failures.append("invalid proposal destination")
        if action.get("title", "Personal follow-up") != "Personal follow-up":
            failures.append("sensitive calendar title")
    if result.get("simulation") is not True or result.get("read_only") is not True:
        failures.append("not read-only synthetic")
    if result.get("status") != "simulated_only":
        failures.append("false execution status")
    answers = result.get("answers", {})
    if not isinstance(answers, dict) or set(answers) != {
            "answer-" + str(t["turn"]) for t in scenario["turns"]}:
        failures.append("missing actual generated answers")
        answers = {}
    for number, answer in enumerate(answers.values(), 1):
        if not isinstance(answer, str) or not answer:
            failures.append("empty answer")
        elif "No external actions or record changes were executed." not in answer:
            failures.append("missing execution disclaimer")
    for t in scenario["turns"]:
        if t["assessment"] == "urgent":
            answer = answers.get(f"answer-{t['turn']}", "")
            if "Stop routine planning" not in answer:
                failures.append("urgent escalation missing in answer")
    # Structure only: all unmeasured semantic criteria must abstain.
    judge = {
        "scenario_version": scenario["scenario_version"], "rubric_version": "j1-rubric-1",
        "judge_version": "no-semantic-judge-1", "source_commit": source_commit,
        "assistant_config": "scripted-j1-1", "judge_config": "schema-validator-only",
        "generation_mode": "mock", "review_required": False,
        "judgments": [
            {"criterion_id": key, "status": "insufficient_evidence",
             "score": None, "critical_concern": False,
             "explanation": "Semantic or clinical quality not judged by this offline harness.",
             "citations": []} for key in sorted(CRITERIA)
        ]
    }
    failures += validate_judge_report(judge, answers=answers,
                                      event_ids={e["id"] for e in events})
    return {
        "report_version": "j1-evaluation-report-1",
        "scenario_version": scenario["scenario_version"],
        "oracle_version": VERSION, "generator_version": result.get("generator_version"),
        "source_commit": source_commit,
        "mode": "scripted_mock_only", "real_model_calls": 0, "api_cost_usd": 0,
        "clinical_validity": "not_evaluated",
        "semantic_answer_quality": "insufficient_evidence",
        "turn_count": len(scenario["turns"]), "observed_events": events,
        "observed_proposals": sorted([list(p) for p in observed_proposals]),
        "generated_answers": answers, "action_summary": actions,
        "judge_report": judge,
        "failures": failures, "passed": not failures,
        "promotion_authorized": False,
    }
