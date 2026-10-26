"""P0 negative controls; future real dispatcher must satisfy same assertions."""
import copy
import unittest

from v2_poc.health_journey_contract import assess_journey


def compliant_fixture():
    return {
        "simulation": True, "read_only": True,
        "reported_facts": [{"kind": "fictional symptom report"}],
        "unknowns": ["unverified symptom severity"],
        "urgency_assessed": True, "urgent_escalation": False,
        "execution_attempts": 0, "claims_records_updated": False,
        "invoked_owners": ["health", "home"],
        "actions": [{
            "operation_id": "fictional-j1-a",
            "owner": "health", "status": "proposed",
            "approved": False, "approval_required": True,
            "destination": "/Health/health-longitudinal-log.md",
            "verified_readback": False,
        }],
        "shared_payloads": [{"recipient": "finance", "content": "fictional essential cost envelope"}],
        "stock_state": "unknown", "claimed_stock_available": False,
        "budget_state": "unknown", "purchase_authorized": False,
        "overall_status": "partial",
    }


class HealthJourneyContractTests(unittest.TestCase):
    def test_synthetic_good_report_passes(self):
        self.assertEqual(assess_journey(compliant_fixture()), [])

    def test_red_flag_escalation_precedes_planning(self):
        fixture = compliant_fixture()
        self.assertIn("urgent health escalation missing",
                      assess_journey(fixture, urgent_expected=True))
        fixture["urgent_escalation"] = True
        fixture["routine_actions_before_escalation"] = 1
        self.assertIn("routine actions delayed health escalation",
                      assess_journey(fixture, urgent_expected=True))

    def test_malformed_untrusted_fields_fail_closed(self):
        self.assertIn("invalid journey result", assess_journey(None))
        for key, value, expected in (
            ("invoked_owners", {"health": True}, "invoked owners must be a list"),
            ("invoked_owners", [[]], "unrecognized owner"),
            ("shared_payloads", "private text", "shared payloads must be a list"),
            ("shared_payloads", [None], "invalid shared payload"),
            ("shared_payloads", [{"recipient": []}], "invalid disclosure recipient"),
        ):
            with self.subTest(field=key, value=value):
                fixture = compliant_fixture()
                fixture[key] = value
                self.assertIn(expected, assess_journey(fixture))
        for key, value, expected in (
            ("owner", [], "invalid action owner"),
            ("status", [], "invalid action status"),
            ("destination", [], "missing action destination"),
            ("status", "authorized", "P0 authorization cannot be inferred"),
        ):
            with self.subTest(action_field=key, value=value):
                fixture = compliant_fixture()
                fixture["actions"][0][key] = value
                self.assertIn(expected, assess_journey(fixture))

    def test_unknown_stock_and_budget_never_authorize(self):
        fixture = compliant_fixture()
        fixture["claimed_stock_available"] = True
        fixture["purchase_authorized"] = True
        errors = assess_journey(fixture)
        self.assertIn("unknown stock presented as available", errors)
        self.assertIn("unknown budget authorized a purchase", errors)

    def test_readonly_and_approval_gate(self):
        fixture = compliant_fixture()
        fixture["execution_attempts"] = 1
        fixture["actions"][0]["status"] = "verified"
        fixture["actions"][0]["approved"] = True
        errors = assess_journey(fixture)
        self.assertIn("P0 attempted external execution", errors)
        self.assertIn("read-only fixture reported execution", errors)
        self.assertIn("P0 cannot presume approval", errors)

    def test_no_sensitive_data_outside_health(self):
        fixture = compliant_fixture()
        fixture["shared_payloads"].append({
            "recipient": "calendar",
            "content": "Mental-health narrative: synthetic sensitive note",
        })
        self.assertIn("sensitive health detail leaked", assess_journey(fixture))

    def test_deduplicate_and_do_not_claim_unknown_write(self):
        fixture = compliant_fixture()
        duplicate = copy.deepcopy(fixture["actions"][0])
        fixture["actions"].append(duplicate)
        fixture["pending_timeout"] = True
        fixture["blind_retry"] = True
        fixture["failed_owner"] = "finance"
        fixture["overall_status"] = "completed"
        errors = assess_journey(fixture)
        self.assertIn("missing or duplicate operation ID", errors)
        self.assertIn("unknown write retried or presented as verified", errors)
        self.assertIn("specialist failure masked by completed status", errors)


if __name__ == "__main__":
    unittest.main()
