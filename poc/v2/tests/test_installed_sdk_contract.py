"""Validate real Agents SDK interfaces offline when optional dependency is installed."""
import importlib.util
import unittest

from v2_poc.agents_sdk_adapter import AIAssessment, MODEL_DEFAULT, MAX_OUTPUT_TOKENS


@unittest.skipUnless(importlib.util.find_spec("agents"), "Optional Agents SDK not installed")
class InstalledSDKContractTests(unittest.TestCase):
    def test_agent_output_schema_and_bounded_run_config_without_api(self):
        from agents import Agent, AgentOutputSchema, ModelSettings, RunConfig
        agent = Agent(
            name="V2 purchase specialist",
            instructions="Read-only, fictional fixture only.",
            model=MODEL_DEFAULT,
            output_type=AIAssessment,
            model_settings=ModelSettings(max_output_tokens=MAX_OUTPUT_TOKENS),
            tools=[], handoffs=[],
        )
        self.assertEqual(agent.tools, [])
        self.assertEqual(agent.handoffs, [])
        self.assertEqual(agent.model_settings.max_output_tokens, MAX_OUTPUT_TOKENS)
        self.assertTrue(AgentOutputSchema(AIAssessment).json_schema())
        self.assertTrue(RunConfig(tracing_disabled=True).tracing_disabled)


if __name__ == "__main__":
    unittest.main()
