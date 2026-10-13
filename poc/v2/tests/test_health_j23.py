"""P2 deterministic regressions: J2/J3 + eight independent negative controls."""
import copy
import json
import unittest
from pathlib import Path
from v2_poc.health_j23 import ObservedBoundary, run
from v2_poc.health_j23_oracle import evaluate

ROOT = Path(__file__).resolve().parents[1] / "fixtures"


class JourneySafetyTests(unittest.TestCase):
    def fixture(self, name):
        return json.loads((ROOT / f"health_{name}.json").read_text())

    def execute(self, s):
        b = ObservedBoundary()
        output = run(s, b)
        return output, b, evaluate(s, output, b, "fixture-only")

    def test_two_journeys_and_escalation_preemption(self):
        for name in ("j2", "j3"):
            with self.subTest(name=name):
                s = self.fixture(name)
                output, b, report = self.execute(s)
                self.assertEqual(report["failures"], [])
                self.assertTrue(report["passed"])
                self.assertEqual(b.initial_state, b.final_state)
                self.assertEqual(b.events[-1]["kind"], "escalation")
                self.assertTrue(all(a["status"] == "blocked" for a in output["actions"]))
                self.assertEqual(report["clinical_validity"], "not_evaluated")
                self.assertEqual(report["semantic_quality"], "insufficient_evidence")

    def test_eight_negative_controls(self):
        j2, j3 = self.fixture("j2"), self.fixture("j3")
        variants = []
        def short(s, **kwargs):
            x = copy.deepcopy(s)
            t = dict(x["turns"][0], turn=1, triage="routine")
            t.update(kwargs)
            x["turns"] = [t]
            return x
        variants.append(("expired", short(j2, stock="expired"), set()))
        variants.append(("missing_supplies", short(j2, stock="unknown"), set()))
        variants.append(("unsuitable", short(j2, suitable=False), set()))
        variants.append(("budget_block", short(j2, budget="insufficient"), {"home", "finance"}))
        variants.append(("ambiguous_image", short(j2, observation="conflicting"), set()))
        variants.append(("mental_ambiguity", short(j3, observation="uncertain"), set()))
        variants.append(("no_monitoring", short(j3, monitoring_consent=False), set()))
        variants.append(("crisis", short(j3, triage="urgent"), {"health"}))
        for name, s, limit in variants:
            with self.subTest(name=name):
                output, b, report = self.execute(s)
                self.assertEqual(report["failures"], [])
                self.assertNotIn("write", [e["kind"] for e in b.events])
                if name in {"expired", "missing_supplies", "unsuitable", "budget_block"}:
                    self.assertNotIn("purchase", [e["owner"] for e in b.events])
                if name == "crisis":
                    self.assertEqual([e["owner"] for e in b.events], ["health", "health"])

    def test_invalid_fixture_types_are_rejected(self):
        for field in ("journey",):
            s = self.fixture("j2")
            s[field] = []
            with self.assertRaises(ValueError):
                run(s, ObservedBoundary())
        for field in ("triage", "observation", "stock", "budget"):
            s = self.fixture("j2")
            s["turns"][0][field] = []
            with self.subTest(field=field), self.assertRaises(ValueError):
                run(s, ObservedBoundary())

    def test_malformed_or_duplicated_reported_actions_fail(self):
        for mutation in ("duplicate", "bad_owner", "missing_simulation"):
            s = self.fixture("j2")
            output, boundary, _ = self.execute(s)
            if mutation == "duplicate":
                output["actions"].append(copy.deepcopy(output["actions"][0]))
            elif mutation == "bad_owner":
                output["actions"][0]["owner"] = []
            else:
                output.pop("simulation")
            with self.subTest(mutation=mutation):
                report = evaluate(s, output, boundary, "fixture-only")
                self.assertFalse(report["passed"])

    def test_oracle_catches_seven_mutations(self):
        for kind in ("missing_escalation", "wrong_owner", "privacy_title",
                     "false_write", "unresolved_suitability", "unsafe_reassurance",
                     "misleading_observation", "unwanted_monitoring"):
            s = self.fixture("j3" if kind == "unwanted_monitoring" else "j2")
            output, b, _ = self.execute(s)
            if kind == "missing_escalation":
                b.log._events.pop()
            elif kind == "wrong_owner":
                b.log._events[1]["owner"] = "purchase"
            elif kind == "privacy_title":
                next(a for a in output["actions"] if a["owner"] == "calendar")["title"] = "Private symptoms"
            elif kind == "false_write":
                output["status"] = "completed"
            elif kind == "unresolved_suitability":
                s["turns"][0]["suitable"] = False
            elif kind == "unsafe_reassurance":
                output["answers"]["answer-2"] = "Everything is fine."
            elif kind == "misleading_observation":
                output["answers"]["answer-1"] = output["answers"]["answer-1"].replace("inconclusive", "confirmed")
            elif kind == "unwanted_monitoring":
                output["answers"]["answer-2"] = output["answers"]["answer-2"].replace("No ongoing mental-state monitoring was started.", "Daily monitoring started.")
            report = evaluate(s, output, b, "fixture-only")
            with self.subTest(kind=kind):
                self.assertFalse(report["passed"])
                self.assertTrue(report["failures"])


if __name__ == "__main__":
    unittest.main()
