from qa_agent.llm import DEEPSEEK_SETTINGS


class TestLlmConfiguration:
    def test_limits_model_output(self) -> None:
        assert DEEPSEEK_SETTINGS["max_tokens"] == 1024
