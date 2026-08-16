import unittest

from qa_agent.llm import DEEPSEEK_SETTINGS


class LlmConfigurationTest(unittest.TestCase):
    def test_limits_model_output(self) -> None:
        self.assertEqual(DEEPSEEK_SETTINGS["max_tokens"], 1024)


if __name__ == "__main__":
    unittest.main()
