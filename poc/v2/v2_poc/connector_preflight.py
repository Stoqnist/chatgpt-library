"""P4 connector capability gate: offline evidence classifier, NOT a live adapter.

No connected-app imports, network I/O, private resource identifiers or mutation
tools. Fixture observations are not evidence of actual account permissions.
A separate, approved private integration trial is required before any write.
"""
from __future__ import annotations

import argparse
import json
import os
from copy import deepcopy

CONTRACT_VERSION = "p4-connector-contract-4"
# Public provider/domain map only. Real file IDs, sheet IDs, calendar IDs and
# account-specific destinations must be supplied privately and never logged.
TARGETS = {
    "health_library": ("health", "library"),
    "mental_health_library": ("health", "library"),
    "finance_library": ("finance", "library"),
    "purchase_library": ("purchase", "library"),
    "home_stock": ("home", "sheets"),
    "calendar_followup": ("calendar", "calendar"),
}
PROBE_STATES = frozenset({"ok", "permission_denied", "unavailable", "not_found",
                          "timeout", "stale", "not_attempted"})
ROLES = {
    "library": {"editor", "viewer"},
    "sheets": {"reader", "writer", "owner", "unknown"},
    "calendar": {"reader", "writer", "owner", "freeBusyReader", "unknown"},
}
READ_ROLES = {
    "library": {"viewer", "editor"},
    "sheets": {"reader", "writer", "owner"},
    "calendar": {"reader", "writer", "owner"},
}
# Operation-specific Calendar reads, not a general permission engine.
CALENDAR_READ_OPERATIONS = {
    "freebusy": ({"freeBusyReader", "reader", "writer", "owner"}, {"freeBusyReader"}),
    "calendar_list": ({"freeBusyReader", "reader", "writer", "owner"}, {"freeBusyReader"}),
    "event_details": ({"reader", "writer", "owner"}, {"reader"}),
}
WRITE_ROLES = {
    "library": {"editor"}, "sheets": {"writer", "owner"},
    "calendar": {"writer", "owner"},
}
# Advisory minimums for a read-only probe, not proof of effective OAuth grants.
# Elevated ACL roles require a narrower connection or a separately reviewed
# exception; neither can enable execution through this classifier.
MINIMUM_READ_ROLES = {
    "library": {"viewer"}, "sheets": {"reader"}, "calendar": {"reader"},
}
# Synthetic grant posture is independent of the resource ACL role. "Verified"
# booleans and sample roles MUST NOT be populated from metadata-only discovery.
OAUTH_SCOPE_POSTURES = frozenset({"minimal_read", "excess", "unknown"})
# Key names are fixed, non-sensitive, and intentionally exclude identifiers or
# record content. Unknown keys fail closed; never include raw observations in CI.
EVIDENCE_FIELDS = frozenset({
    "provider", "role", "metadata_probe", "binding_verified",
    "scope_verified", "oauth_scope_posture", "freshness_verified", "readback_capable",
    "conditional_write_capable", "persistent_idempotency_verified",
    "disposable_target_verified",
})


def classify(target, observation, *, owner, requested_action="read", read_operation=None):
    """Return a safe advisory classification; never grant execution authority."""
    if not isinstance(target, str) or target not in TARGETS:
        return {"target": "unrecognized", "status": "blocked",
                "reasons": ["unknown_target"], "execution_allowed": False}
    expected_owner, provider = TARGETS[target]
    reasons = []
    valid_action = isinstance(requested_action, str) and requested_action in {"read", "write"}
    if not valid_action:
        reasons.append("invalid_action")
    # Only Calendar needs a sub-operation: free/busy is less privileged than
    # event details. Other providers retain their existing narrow contract.
    valid_read_operation = read_operation is None or (
        provider == "calendar" and requested_action == "read"
        and isinstance(read_operation, str)
        and read_operation in CALENDAR_READ_OPERATIONS
    )
    if not valid_read_operation:
        reasons.append("invalid_read_operation")
    if owner != expected_owner:
        reasons.append("wrong_owner")
    if not isinstance(observation, dict) or set(observation) != EVIDENCE_FIELDS:
        return {"target": target, "status": "blocked",
                "reasons": sorted(set(reasons + ["invalid_evidence_schema"])),
                "execution_allowed": False}
    if observation["provider"] != provider:
        reasons.append("provider_mismatch")
    state = observation["metadata_probe"]
    if not isinstance(state, str) or state not in PROBE_STATES:
        reasons.append("invalid_probe_result")
    elif state != "ok":
        reasons.append("probe_" + state)
    role = observation["role"]
    acceptable_roles = READ_ROLES[provider]
    least_roles = MINIMUM_READ_ROLES[provider]
    if provider == "calendar" and valid_read_operation and read_operation is not None:
        acceptable_roles, least_roles = CALENDAR_READ_OPERATIONS[read_operation]
    if not isinstance(role, str) or role not in ROLES[provider]:
        reasons.append("invalid_role")
    elif role not in acceptable_roles:
        reasons.append("read_role_missing")
    elif requested_action == "read" and role not in least_roles:
        reasons.append("excess_read_privilege")
    for key in ("binding_verified", "scope_verified", "freshness_verified",
                "readback_capable", "conditional_write_capable",
                "persistent_idempotency_verified", "disposable_target_verified"):
        if type(observation[key]) is not bool:
            reasons.append("invalid_" + key)
    if observation["binding_verified"] is not True:
        reasons.append("binding_unverified")
    if observation["scope_verified"] is not True:
        reasons.append("oauth_scope_unverified")
    posture = observation["oauth_scope_posture"]
    if not isinstance(posture, str) or posture not in OAUTH_SCOPE_POSTURES:
        reasons.append("invalid_oauth_scope_posture")
    elif posture == "excess":
        reasons.append("oauth_scope_excess")
    elif posture == "unknown":
        reasons.append("oauth_scope_minimality_unverified")
    elif observation["scope_verified"] is not True:
        reasons.append("inconsistent_oauth_scope_evidence")
    if observation["freshness_verified"] is not True:
        reasons.append("freshness_unverified")
    # Even successful read metadata cannot establish a write gate.
    if requested_action == "write":
        if not isinstance(role, str) or role not in WRITE_ROLES[provider]:
            reasons.append("write_role_missing")
        for key in ("readback_capable", "conditional_write_capable",
                    "persistent_idempotency_verified", "disposable_target_verified"):
            if observation[key] is not True:
                reasons.append("missing_" + key)
        reasons.append("separate_private_trial_and_approval_required")
        reasons.append("live_execution_disabled")
    return {
        "target": target,
        "status": ("blocked" if reasons else "metadata_probe_only"),
        "reasons": sorted(set(reasons)),
        "execution_allowed": False,
        "provider": provider,
        "owner": expected_owner,
        "requested_action": requested_action if valid_action else "invalid",
        "read_operation": read_operation if valid_read_operation and read_operation is not None else (
            "invalid" if not valid_read_operation else "unspecified"),
    }


def run_offline_demo():
    """Small fictional probe corpus: 0 API/tool calls by construction."""
    baseline = {
        "provider": "library", "role": "editor", "metadata_probe": "ok",
        "binding_verified": True, "scope_verified": False,
        "oauth_scope_posture": "unknown",
        "freshness_verified": True, "readback_capable": False,
        "conditional_write_capable": False,
        "persistent_idempotency_verified": False,
        "disposable_target_verified": False,
    }
    probes = {}
    for name, (owner, provider) in TARGETS.items():
        observation = deepcopy(baseline)
        observation["provider"] = provider
        observation["role"] = "editor" if provider == "library" else "reader"
        probes[name] = {
            "read": classify(name, observation, owner=owner),
            "write": classify(name, observation, owner=owner, requested_action="write"),
        }
    return {
        "report_version": "p4-offline-feasibility-1",
        "contract_version": CONTRACT_VERSION,
        "source_commit": os.getenv("GITHUB_SHA") or "local-unverified",
        "evidence_source": "fictional_synthetic_observations",
        "actual_connector_calls": 0, "actual_write_attempts": 0,
        "live_execution_enabled": False,
        "observations": probes,
        "all_live_writes_blocked": all(
            not p["write"]["execution_allowed"] and p["write"]["status"] == "blocked"
            for p in probes.values()),
        "provider_permissions_verified": False,
        "integration_trial_completed": False,
        "promotion_authorized": False,
    }


def main(argv=None):
    argparse.ArgumentParser(description="Offline P4 feasibility contract only").parse_args(argv)
    report = run_offline_demo()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_live_writes_blocked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
