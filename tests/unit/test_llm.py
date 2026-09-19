from pydantic_ai.models.openai import OpenAIResponsesModel

from qa_agent.llm import OPENAI_MODEL_NAME, OPENAI_SETTINGS, openai_model


class TestLlmConfiguration:
    def test_limits_model_output(self) -> None:
        assert OPENAI_MODEL_NAME == "gpt-5.6-terra"
        assert OPENAI_SETTINGS["max_tokens"] == 4096
        assert OPENAI_SETTINGS["openai_reasoning_effort"] == "low"

    def test_builds_openai_responses_model(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        model = openai_model()
        assert isinstance(model, OpenAIResponsesModel)
        assert model.model_name == OPENAI_MODEL_NAME
