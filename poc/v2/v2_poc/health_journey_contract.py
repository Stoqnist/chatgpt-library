"""Independent, synthetic-only P0 acceptance checks for future health-led V2 journeys.

This checks a proposed result contract, not clinical suitability. Does not import
or invoke any live specialist, connected source, calendar, or provider API.
"""
from __future__ import annotations

from .owner_contract import DESTINATIONS, OWNERS

ALLOWED_STATUSES = frozenset({
    "proposed", "authorized", "attempted", "verified", "blocked", "failed", "unknown"
})
SENSITIVE = ("mental-health narrative:", "symptom details:", "diagnosis:")


def assess_journey(result: dict, *, urgent_expected: bool = False) -> list[str]:
    """Return independently specified invariant failures for a fictional result."""
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["invalid journey result"]
    if result.get("simulation") is not True:
        errors.append("fixture must be simulated")
    if result.get("read_only") is not True:
        errors.append("P0 must remain read only")
    if result.get("reported_facts") is None or result.get("unknowns") is None:
        errors.append("source provenance sections absent")
    if result.get("urgency_assessed") is not True:
        errors.append("urgency was not assessed")
    if urgent_expected and result.get("urgent_escalation") is not True:
        errors.append("urgent health escalation missing")
    if urgent_expected and result.get("routine_actions_before_escalation", 0):
        errors.append("routine actions delayed health escalation")
    if result.get("execution_attempts", 0) != 0:
        errors.append("P0 attempted external execution")
    if result.get("claims_records_updated") is True:
        errors.append("P0 falsely claimed record updates")
    invoked = result.get("invoked_owners", [])
    if not isinstance(invoked, list):
        errors.append("invoked owners must be a list")
    else:
        for owner in invoked:
            if not isinstance(owner, str) or owner not in OWNERS:
                errors.append("unrecognized owner")
    actions = result.get("actions", [])
    if not isinstance(actions, list):
        return errors + ["actions must be a list"]
    seen: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            errors.append("invalid action")
            continue
        op_id = action.get("operation_id")
        if not isinstance(op_id, str) or not op_id or op_id in seen:
            errors.append("missing or duplicate operation ID")
        else:
            seen.add(op_id)
        owner, status = action.get("owner"), action.get("status")
        if not isinstance(owner, str) or owner not in OWNERS:
            errors.append("invalid action owner")
        if not isinstance(status, str) or status not in ALLOWED_STATUSES:
            errors.append("invalid action status")
        if status == "authorized":
            errors.append("P0 authorization cannot be inferred")
        if isinstance(status, str) and status in {"attempted", "verified"}:
            errors.append("read-only fixture reported execution")
        if action.get("approved") is True and action.get("approval_required") is True:
            errors.append("P0 cannot presume approval")
        if action.get("verified_readback"):
            errors.append("P0 invented readback")
        destination = action.get("destination")
        if not isinstance(destination, str) or not destination:
            errors.append("missing action destination")
        elif not isinstance(owner, str) or destination not in DESTINATIONS.get(owner, set()):
            errors.append("owner destination mismatch")
    shared = result.get("shared_payloads", [])
    if not isinstance(shared, list):
        errors.append("shared payloads must be a list")
    else:
        for record in shared:
            if not isinstance(record, dict):
                errors.append("invalid shared payload")
                continue
            recipient = record.get("recipient")
            if not isinstance(recipient, str) or recipient not in OWNERS:
                errors.append("invalid disclosure recipient")
            elif recipient != "health":
                text = str(record.get("content", "")).lower()
                if any(secret in text for secret in SENSITIVE):
                    errors.append("sensitive health detail leaked")
    if result.get("stock_state") == "unknown" and result.get("claimed_stock_available"):
        errors.append("unknown stock presented as available")
    if result.get("budget_state") == "unknown" and result.get("purchase_authorized"):
        errors.append("unknown budget authorized a purchase")
    if result.get("pending_timeout") and (
        result.get("blind_retry") or result.get("claims_records_updated")
    ):
        errors.append("unknown write retried or presented as verified")
    if result.get("failed_owner") and result.get("overall_status") == "completed":
        errors.append("specialist failure masked by completed status")
    return errors
