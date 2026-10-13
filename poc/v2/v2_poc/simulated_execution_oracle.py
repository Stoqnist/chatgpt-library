"""Independent observable P3 acceptance evidence; no production safety claim."""
from .simulated_execution import fingerprint


def evaluate_execution(operations, approvals, initial, store, result, source_commit):
    failures = []
    events = store.events
    outcomes = result.get("outcomes", [])
    attempts = [e for e in events if e["kind"] == "write_attempt"]
    applied = [e for e in events if e["kind"] == "write_applied"]
    for op in operations:
        key = (op["request_id"], op["operation_id"])
        matching = [e for e in applied if (e["request_id"], e["operation_id"]) == key]
        if len(matching) > 1:
            failures.append("duplicate applied operation")
        if approvals.status(op) != "approve" and matching:
            failures.append("unapproved mutation")
        if matching and not any(e["kind"] == "readback" and
                                (e["request_id"], e["operation_id"]) == key for e in events):
            failures.append("missing readback")
    # Every requested operation must have exactly one consolidated outcome.
    expected_keys = [(op["request_id"], op["operation_id"]) for op in operations]
    reported_keys = [(o.get("request_id"), o.get("operation_id"))
                     for o in outcomes if isinstance(o, dict)]
    if (len(reported_keys) != len(outcomes) or len(reported_keys) != len(expected_keys)
            or sorted(reported_keys) != sorted(expected_keys)):
        failures.append("missing or duplicate action outcome")
    for output in outcomes:
        if not isinstance(output, dict):
            failures.append("invalid action outcome")
            continue
        op = next((x for x in operations if x["request_id"] == output["request_id"] and
                   x["operation_id"] == output["operation_id"]), None)
        if op is None:
            failures.append("unknown reported operation")
            continue
        key = (op["request_id"], op["operation_id"])
        if (output.get("owner") != op["owner"] or
                output.get("destination") != op["destination"]):
            failures.append("reported owner/destination mismatch")
        if output.get("status") == "verified":
            marker = store._applied.get(key)
            record = store.state[op["destination"]]
            if (not marker or marker["fingerprint"] != fingerprint(op) or
                    record != {"revision": marker["revision"], "value": marker["value"]} or
                    not any(e["kind"] == "readback" and
                            (e["request_id"], e["operation_id"]) == key for e in events)):
                failures.append("unsupported verified claim")
        if output.get("status") in {"unknown", "failed", "blocked", "denied"} and result.get("status") == "verified":
            failures.append("partial failure masked")
    if result.get("external_actions") != 0 or result.get("simulation") is not True:
        failures.append("real execution falsely claimed")
    if not applied and initial != store.state:
        failures.append("unobserved state change")
    return {"report_version": "p3-observation-1", "source_commit": source_commit,
            "mode": "disposable-mock-only", "observed_events": events,
            "initial_state": initial, "final_state": store.state,
            "result": result, "attempt_count": len(attempts),
            "applied_count": len(applied), "failures": failures,
            "passed": not failures, "promotion_authorized": False,
            "real_provider_calls": 0, "api_cost_usd": 0}
