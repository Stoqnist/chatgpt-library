"""Deterministic contract journeys for the deployed Daily app (no API calls).

These assert routing limits, scoping, selection provenance and safe interruption.
They do NOT measure real model accuracy, latency, or cost. See QUALITY.md.
"""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App, ROUTE_SCHEMA, RESULT_SCHEMA, PLAN_SCHEMA, password_hash


JOURNEYS = (
    {"name": "one-planning-task",
     "prompt": "I have 25 minutes to read a book.",
     "assign": (("planning", "I have 25 minutes to read a book."),),
     "domains": ("planning",)},
    {"name": "home-only",
     "prompt": "I need to tidy my desk.",
     "assign": (("home", "I need to tidy my desk."),),
     "domains": ("home",)},
    {"name": "wellbeing-only",
     "prompt": "I feel tired.",
     "assign": (("wellbeing", "I feel tired."),),
     "domains": ("wellbeing",)},
    {"name": "home-and-planning",
     "prompt": "I need groceries. I have 20 minutes this evening.",
     "assign": (("home", "I need groceries."),
                ("planning", "I have 20 minutes this evening.")),
     "domains": ("home", "planning")},
    {"name": "wellbeing-and-planning",
     "prompt": "I slept poorly. I want to take a short break this afternoon.",
     "assign": (("wellbeing", "I slept poorly."),
                ("planning", "I want to take a short break this afternoon.")),
     "domains": ("wellbeing", "planning")},
    {"name": "all-bounded-domains",
     "prompt": "I feel tired. I need groceries. I have 20 minutes this evening.",
     "assign": (("wellbeing", "I feel tired."),
                ("home", "I need groceries."),
                ("planning", "I have 20 minutes this evening.")),
     "domains": ("wellbeing", "home", "planning")},
    {"name": "possible-urgent-case",
     "prompt": "I may be in immediate danger and need urgent help.",
     "assign": (),
     "domains": (),
     "urgent": True},
)


class JourneyProvider:
    def __init__(self, journey):
        self.journey = journey
        self.calls = []

    def call(self, instructions, payload, schema):
        self.calls.append((schema, payload))
        if schema is ROUTE_SCHEMA:
            assert payload["check_in"] == self.journey["prompt"]
            return {"urgent": self.journey.get("urgent", False),
                    "tasks": [
                        {"domain": domain, "excerpts": [excerpt]}
                        for domain, excerpt in self.journey["assign"]
                    ]}
        if schema is RESULT_SCHEMA:
            excerpt = payload["user_reported_excerpts"][0]
            assert excerpt in self.journey["prompt"]
            return {"summary": "Fictional test only.",
                    "suggestions": ["Consider one small task for today."],
                    "missing_context": [], "question": ""}
        if schema is PLAN_SCHEMA:
            assert "check_in" not in payload
            return {"step_ids": list(payload["suggestions"])[:3],
                    "question_owner": ""}
        raise AssertionError("Unexpected unbounded model call")


class JourneyAcceptance(unittest.TestCase):
    def test_offline_journeys_and_provenance(self):
        for journey in JOURNEYS:
            with self.subTest(journey=journey["name"]):
                with tempfile.TemporaryDirectory() as work:
                    provider = JourneyProvider(journey)
                    app = App(work, "https://daily.example",
                              password_hash("fictional-test-access-code"),
                              provider)
                    try:
                        run_id = "synthetic-" + journey["name"]
                        with app.db() as db:
                            db.execute(
                                "INSERT INTO runs VALUES (?,?,?,?,?,?)",
                                (run_id, run_id, journey["prompt"],
                                 time.time(), "running", "{}"))
                        app.run(run_id, journey["prompt"])
                        with app.db() as db:
                            stored = db.execute(
                                "SELECT status,result FROM runs WHERE id=?",
                                (run_id,)).fetchone()
                        result = json.loads(stored["result"])
                        if journey.get("urgent"):
                            self.assertEqual(stored["status"], "needs_attention")
                            self.assertEqual(len(provider.calls), 1)
                            self.assertEqual(result["agents"], [])
                            continue
                        self.assertEqual(stored["status"], "completed")
                        domains = tuple(x["domain"] for x in result["agents"])
                        self.assertEqual(domains, journey["domains"])
                        self.assertLessEqual(len(domains), 3)
                        self.assertEqual(len(provider.calls), 2 + len(domains))
                        self.assertGreaterEqual(len(result["next_steps"]), 1)
                        self.assertLessEqual(len(result["next_steps"]), 3)
                        emitted = {
                            x for agent in result["agents"]
                            for x in agent.get("suggestions", [])
                        }
                        self.assertTrue(all(
                            step["text"] in emitted
                            for step in result["next_steps"]))
                        self.assertTrue(all(
                            schema in (ROUTE_SCHEMA, RESULT_SCHEMA, PLAN_SCHEMA)
                            for schema, _ in provider.calls))
                    finally:
                        app.pool.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
