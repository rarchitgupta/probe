from __future__ import annotations

from dataclasses import dataclass

PROMPT_VERSION = "6"
MODEL_CONFIG_VERSION = "2"


@dataclass(frozen=True)
class AgentConfiguration:
    model: str
    prompt_version: str = PROMPT_VERSION
    model_config_version: str = MODEL_CONFIG_VERSION
