import os

from openai import AsyncOpenAI
from pydantic_ai.models.openai import (
    OpenAIChatModel,
    OpenAIChatModelSettings,
)
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.deepseek import DeepSeekProvider

MODEL_REQUEST_TIMEOUT_SECONDS = 60
DEEPSEEK_MODEL_NAME = "deepseek-v4-flash"

DEEPSEEK_SETTINGS = OpenAIChatModelSettings(
    max_tokens=1024,
    temperature=0,
    thinking=False,
    timeout=MODEL_REQUEST_TIMEOUT_SECONDS,
)


def deepseek_model() -> OpenAIChatModel:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    provider = DeepSeekProvider(api_key=api_key)
    return OpenAIChatModel(
        DEEPSEEK_MODEL_NAME,
        profile=OpenAIModelProfile(
            openai_chat_supports_max_completion_tokens=False,
        ),
        provider=DeepSeekProvider(
            openai_client=AsyncOpenAI(
                api_key=api_key,
                base_url=provider.base_url,
                max_retries=1,
                timeout=MODEL_REQUEST_TIMEOUT_SECONDS,
            )
        ),
    )
