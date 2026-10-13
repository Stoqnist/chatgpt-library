"""P4 offline least-privilege failure controls."""
import copy
import unittest

from v2_poc.connector_preflight import TARGETS, classify, run_offline_demo


def observation(provider, role="owner"):
    return {"provider": provider, "role": role, "metadata_probe": "ok",
            "binding_verified": True, "scope_verified": True,
            "freshness_verified": True, "readback_capable": True,
            "conditional_write_capable": True,
            "persistent_idempotency_verified": True,
            "disposable_target_verified": True}


class ConnectorPreflightTests(unittest.TestCase):
    def test_read_probe_is_not_write_authority(self):
        for target, (owner, provider) in TARGETS.items():
            role = "editor" if provider == "library" else "owner"
            probe = observation(provider, role)
            with self.subTest(target=target):
                result = classify(target, probe, owner=owner)
                self.assertEqual(result["status"], "metadata_probe_only")
                self.assertFalse(result["execution_allowed"])
                write = classify(target, probe, owner=owner, requested_action="write")
                self.assertEqual(write["status"], "blocked")
                self.assertIn("live_execution_disabled", write["reasons"])

    def test_denied_stale_timeout_and_disconnected_fail_closed(self):
        for fault in ("permission_denied", "stale", "timeout", "unavailable", "not_found"):
            probe = observation("sheets")
            probe["metadata_probe"] = fault
            with self.subTest(fault=fault):
                result = classify("home_stock", probe, owner="home")
                self.assertEqual(result["status"], "blocked")
                self.assertIn("probe_" + fault, result["reasons"])

    def test_wrong_owner_and_unknown_scopes_fail_closed(self):
        probe = observation("calendar")
        self.assertIn("wrong_owner", classify("calendar_followup", probe, owner="health")["reasons"])
        probe["scope_verified"] = False
        self.assertIn("oauth_scope_unverified",
                      classify("calendar_followup", probe, owner="calendar")["reasons"])
        self.assertEqual(classify("invented", probe, owner="calendar")["status"], "blocked")

    def test_disposable_integration_gate_and_provider_limitations(self):
        probe = observation("sheets")
        for field in ("readback_capable", "conditional_write_capable",
                      "persistent_idempotency_verified", "disposable_target_verified"):
            mutated = copy.deepcopy(probe)
            mutated[field] = False
            self.assertIn("missing_" + field,
                          classify("home_stock", mutated, owner="home", requested_action="write")["reasons"])

    def test_malformed_or_sensitive_fields_are_rejected(self):
        probe = observation("library", "editor")
        probe["raw_health_record"] = "synthetic sensitive material"
        self.assertIn("invalid_evidence_schema",
                      classify("health_library", probe, owner="health")["reasons"])
        for field in ("role", "metadata_probe", "provider"):
            altered = observation("library", "editor")
            altered[field] = []
            self.assertEqual(classify("health_library", altered, owner="health")["status"], "blocked")

    def test_unhashable_untrusted_inputs_fail_closed(self):
        for invalid in ([], {}, {"not": "a string"}):
            with self.subTest(value=repr(invalid)):
                self.assertEqual(classify(invalid, observation("sheets"),
                                          owner="home")["status"], "blocked")
                invalid_action = classify("home_stock", observation("sheets"), owner="home",
                                          requested_action=invalid)
                self.assertIn("invalid_action", invalid_action["reasons"])
                self.assertEqual(invalid_action["requested_action"], "invalid")
                sample = observation("sheets")
                sample["role"] = invalid
                result = classify("home_stock", sample, owner="home",
                                  requested_action="write")
                self.assertEqual(result["status"], "blocked")
                self.assertIn("write_role_missing", result["reasons"])

    def test_offline_report_labels_unverified_access(self):
        report = run_offline_demo()
        self.assertEqual(report["actual_connector_calls"], 0)
        self.assertEqual(report["actual_write_attempts"], 0)
        self.assertFalse(report["provider_permissions_verified"])
        self.assertTrue(report["all_live_writes_blocked"])


if __name__ == "__main__":
    unittest.main()
