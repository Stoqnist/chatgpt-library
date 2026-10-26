import unittest
import app

class RoutineTests(unittest.TestCase):
    def test_domains(self):
        self.assertEqual(app.selected_domains('hello'), ['health', 'planner'])

    def test_conditional_domains(self):
        self.assertEqual(app.selected_domains('food and rent'), ['health', 'home', 'finance', 'planner'])

    def test_owner_input_excludes_health_details(self):
        sample = "My medical problem worries me and rent is due."
        finance = app.domain_excerpt(sample, "finance")
        self.assertIn("rent", finance)
        self.assertNotIn("medical problem", finance)
        self.assertNotIn("worries", finance)

    def test_raw_prompt_not_shared_with_inventory_adviser(self):
        sample = "I feel unwell and need groceries."
        home = app.domain_excerpt(sample, "home")
        self.assertIn("groceries", home)
        self.assertNotIn("feel unwell", home)

    def test_emergency(self):
        self.assertTrue(app.possible_emergency('chest pain'))

class FakeModel:
    def __init__(self, fail=None):
        self.fail = fail
        self.calls = []

    def complete(self, domain, prompt, health=""):
        self.calls.append(domain)
        if domain == self.fail:
            raise RuntimeError("test only")
        return "review:" + domain


class RunContractTests(unittest.TestCase):
    def test_one_final_synthesis(self):
        model = FakeModel()
        result = app.run_checkin("I need groceries and budget guidance.", model)
        self.assertEqual(model.calls, ["health", "home", "finance", "planner"])
        self.assertEqual(result["results"][-1]["domain"], "planner")
        self.assertTrue(all(item["status"] == "advisory" for item in result["results"]))
        self.assertEqual(result["mode"], "read_only")

    def test_urgent_warning_skips_all_provider_calls(self):
        model = FakeModel()
        result = app.run_checkin("Chest pain and difficulty breathing", model)
        self.assertTrue(result["urgent"])
        self.assertEqual(model.calls, [])

    def test_failed_health_skips_planner(self):
        model = FakeModel(fail="health")
        result = app.run_checkin("I need groceries", model)
        self.assertEqual(model.calls, ["health"])
        self.assertEqual(result["results"][0]["status"], "failed")

    def test_home_failure_does_not_invent_success(self):
        model = FakeModel(fail="home")
        result = app.run_checkin("Groceries and rent budget", model)
        self.assertEqual(model.calls, ["health", "home", "finance", "planner"])
        self.assertEqual(result["results"][1]["status"], "failed")

if __name__ == '__main__':
    unittest.main()
