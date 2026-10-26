"""Offline P1 acceptance tests with independent observed trace assertions."""
import copy
import unittest
from pathlib import Path

from v2_poc.health_j1 import FixtureBoundary, load_fixture, run_j1
from v2_poc.health_j1_oracle import evaluate_j1


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "health_j1.json"


class J1JourneyTests(unittest.TestCase):
    def setUp(self):
        self.scenario = load_fixture(FIXTURE)

    def run_case(self, scenario):
        boundary = FixtureBoundary(scenario)
        result = run_j1(scenario, boundary)
        return result, evaluate_j1(scenario, result, boundary), boundary

    def test_multiturn_changed_circumstances_withdraws_actions(self):
        result, report, boundary = self.run_case(self.scenario)
        self.assertEqual(report["failures"], [])
        self.assertTrue(report["passed"])
        self.assertEqual([(x["turn"], x["owner"], x["kind"]) for x in boundary.events],
                         [(1, "health", "assessment"),
                          (2, "health", "assessment"),
                          (2, "home", "read"),
                          (2, "finance", "read"),
                          (2, "purchase", "read"),
                          (2, "purchase", "proposal"),
                          (2, "calendar", "proposal"),
                          (3, "health", "assessment"),
                          (3, "health", "escalation")])
        self.assertEqual([a["status"] for a in result["actions"]],
                         ["blocked", "blocked"])
        self.assertIn("withdrawn", result["answers"]["answer-3"])

    def test_health_only_and_conditional_routing(self):
        for edits, owners in [
            ({"supplies": False, "calendar": False}, ["health"]),
            ({"stock": {"state": "sufficient", "fresh": True, "connected": True},
              "calendar": False}, ["health", "home"]),
            ({"stock": {"state": "short", "fresh": False, "connected": True},
              "calendar": False}, ["health", "home"]),
            ({"budget": {"state": "insufficient", "fresh": True, "connected": True},
              "calendar": False}, ["health", "home", "finance"]),
            ({"budget": {"state": "unknown", "fresh": False, "connected": False},
              "calendar": False}, ["health", "home", "finance"]),
            ({"suitable": False, "calendar": False}, ["health"]),
        ]:
            scenario = copy.deepcopy(self.scenario)
            scenario["turns"] = [dict(scenario["turns"][1], turn=1, **edits)]
            with self.subTest(edits=edits):
                result, report, boundary = self.run_case(scenario)
                self.assertEqual(report["failures"], [])
                self.assertEqual([e["owner"] for e in boundary.events
                                  if e["kind"] in ("assessment", "read")], owners)
                self.assertNotIn("ordered or paid", result["answers"]["answer-1"]
                                 if "purchase" not in owners else "")

    def test_mutations_fail_independent_observation_oracle(self):
        for mutation, expected in [
            ("drop_escalation", "urgent escalation missing"),
            ("wrong_routing", "incorrect routing or event ordering"),
            ("false_state_change", "read-only state changed"),
            ("false_completion", "false execution status"),
            ("stale_action", "stale proposal not withdrawn"),
            ("missing_answer", "missing actual generated answers"),
        ]:
            boundary = FixtureBoundary(self.scenario)
            result = run_j1(self.scenario, boundary)
            if mutation == "drop_escalation":
                boundary._log._events.pop()
            elif mutation == "wrong_routing":
                boundary._log._events[3]["owner"] = "purchase"
            elif mutation == "false_state_change":
                boundary._turns[0]["stock"]["state"] = "short"
            elif mutation == "false_completion":
                result["status"] = "completed"
            elif mutation == "stale_action":
                result["actions"][0]["status"] = "proposed"
            elif mutation == "missing_answer":
                result["answers"].pop("answer-3")
            with self.subTest(mutation=mutation):
                report = evaluate_j1(self.scenario, result, boundary)
                self.assertIn(expected, report["failures"])

    def test_reported_action_cannot_spoof_observed_owner_or_destination(self):
        for key, spoof in (("owner", "finance"),
                           ("destination", "/Finance/purchase-plan.md")):
            boundary = FixtureBoundary(self.scenario)
            result = run_j1(self.scenario, boundary)
            result["actions"][0][key] = spoof
            with self.subTest(key=key):
                report = evaluate_j1(self.scenario, result, boundary)
                self.assertIn("action owner/destination disagrees with observed proposal",
                              report["failures"])

    def test_duplicate_reported_action_cannot_hide_behind_set_equality(self):
        boundary = FixtureBoundary(self.scenario)
        result = run_j1(self.scenario, boundary)
        result["actions"].append(copy.deepcopy(result["actions"][0]))
        report = evaluate_j1(self.scenario, result, boundary)
        self.assertIn("answer action list disagrees with observed proposals", report["failures"])

    def test_report_never_claims_semantic_or_clinical_validation(self):
        _, report, _ = self.run_case(self.scenario)
        self.assertEqual(report["mode"], "scripted_mock_only")
        self.assertEqual(report["semantic_answer_quality"], "insufficient_evidence")
        self.assertEqual(report["clinical_validity"], "not_evaluated")
        self.assertFalse(report["promotion_authorized"])
        self.assertEqual(report["api_cost_usd"], 0)
        self.assertTrue(all(j["score"] is None for j in report["judge_report"]["judgments"]))


if __name__ == "__main__":
    unittest.main()
