import os

from openai import AsyncOpenAI
from pydantic_ai.models.openai import (
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
)
from pydantic_ai.providers.openai import OpenAIProvider

MODEL_REQUEST_TIMEOUT_SECONDS = 60
OPENAI_MODEL_NAME = "gpt-5.6-terra"

OPENAI_SETTINGS = OpenAIResponsesModelSettings(
    max_tokens=4096,
    openai_reasoning_effort="low",
    timeout=MODEL_REQUEST_TIMEOUT_SECONDS,
)


def openai_model() -> OpenAIResponsesModel:
    return OpenAIResponsesModel(
        OPENAI_MODEL_NAME,
        provider=OpenAIProvider(
            openai_client=AsyncOpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                max_retries=1,
                timeout=MODEL_REQUEST_TIMEOUT_SECONDS,
            )
        ),
    )
