from pydantic_ai.models.openai import (
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
)
from pydantic_ai.providers.deepseek import DeepSeekProvider

DEEPSEEK_SETTINGS = OpenAIResponsesModelSettings(
    temperature=0,
    thinking=False,
    timeout=30,
)


def deepseek_model() -> OpenAIResponsesModel:
    return OpenAIResponsesModel(
        "deepseek-v4-flash",
        provider=DeepSeekProvider(),
    )
