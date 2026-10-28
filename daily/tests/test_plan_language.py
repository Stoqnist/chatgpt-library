"""Owner-facing plan quality regressions; all data and model calls are synthetic."""
from datetime import datetime
from pathlib import Path
import json
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import (App, ProviderError, ROUTE_SCHEMA, RESULT_SCHEMA,
                 PLAN_SCHEMA, action_framing, password_hash)


def output(*suggestions):
    return {"summary": "Fictional fixture only.", "suggestions": list(suggestions),
            "missing_context": [], "question": ""}


class ActionFramingTest(unittest.TestCase):
    def test_agent_facing_planning_and_third_person_are_withheld(self):
        result = action_framing(output(
            "Consider scheduling an uninterrupted focus block.",
            "Plan essential health and meal breaks.",
            "The person's preferences should decide their time.",
            "Use 20 minutes to draft the reply you mentioned.",
        ), ["I need 20 minutes to draft a reply."], today="2026-10-28")
        self.assertEqual(result["suggestions"],
                         ["Use 20 minutes to draft the reply you mentioned."])

    def test_unsolicited_nap_withheld_even_if_plan_is_otherwise_valid(self):
        result = action_framing(
            output("Plan a short nap to recharge.", "Reply to the email you mentioned."),
            ["I need to reply to an email."], today="2026-10-28")
        self.assertEqual(result["suggestions"], ["Reply to the email you mentioned."])
        with self.assertRaises(ProviderError):
            action_framing(output("Take a nap."), ["I need to buy eggs."])

    def test_future_dated_window_cannot_be_called_today(self):
        result = action_framing(output(
            "Today, use the unblocked window on 2026-10-29 for your focus block.",
            "On 2026-10-29, if available, reply to the message you mentioned.",
        ), ["I need to reply to a message."], today="2026-10-28")
        self.assertEqual(len(result["suggestions"]), 1)
        self.assertIn("2026-10-29", result["suggestions"][0])

    def test_third_person_is_allowed_for_explicit_fictional_scenarios(self):
        result = action_framing(
            output("The person could tidy their fictional kitchen."),
            ["A fictional person needs to tidy their kitchen."],
            fictional=True, today="2026-10-28")
        self.assertEqual(len(result["suggestions"]), 1)


class PlanningDateContextTest(unittest.TestCase):
    def test_local_date_reaches_only_planning_and_title_avoids_phantom_today(self):
        timestamp = datetime(2026, 10, 28, 15, 30,
                             tzinfo=ZoneInfo("Europe/Amsterdam")).timestamp()

        class FictionalProvider:
            def __init__(self):
                self.calls = []
            def call(self, instructions, payload, schema):
                self.calls.append((payload, schema))
                if schema is ROUTE_SCHEMA:
                    return {"urgent": False, "tasks": [
                        {"domain": "planning", "excerpts": ["I need to reply to a message."]}]}
                if schema is RESULT_SCHEMA:
                    return output("Reply to the message you mentioned when it suits you.")
                if schema is PLAN_SCHEMA:
                    return {"step_ids": list(payload["suggestions"])[:1],
                            "question_owner": ""}
                raise AssertionError("Unexpected provider call")

        provider = FictionalProvider()
        with tempfile.TemporaryDirectory() as folder:
            app = App(folder, "https://daily.example", password_hash("synthetic-only"),
                      provider, clock=lambda: timestamp)
            try:
                prompt = "I need to reply to a message."
                with app.db() as db:
                    db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?)",
                               ("test", "test", prompt, timestamp, "running", "{}"))
                app.run("test", prompt)
                with app.db() as db:
                    record = db.execute(
                        "SELECT status,result FROM runs WHERE id='test'").fetchone()
                result = json.loads(record["result"])
                self.assertEqual(record["status"], "completed")
                self.assertEqual(result["message"], "Your next steps from this check-in.")
                self.assertEqual(len(result["next_steps"]), 1)
                self.assertEqual(provider.calls[0][0], {"check_in": prompt})
                planning = next(p for p, schema in provider.calls
                                if schema is RESULT_SCHEMA)
                self.assertEqual(planning["local_date_context"]["today"], "2026-10-28")
                self.assertEqual(planning["local_date_context"]["timezone"],
                                 "Europe/Amsterdam")
                self.assertNotIn("calendar_availability", planning)
                final = next(p for p, schema in provider.calls if schema is PLAN_SCHEMA)
                self.assertNotIn("local_date_context", final)
            finally:
                app.pool.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
