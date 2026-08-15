from __future__ import annotations

import logging
import os
from functools import cache

from langfuse import Langfuse, get_client
from pydantic_ai import Agent, InstrumentationSettings

logger = logging.getLogger(__name__)


@cache
def configure_observability() -> Langfuse | None:
    if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
        return None

    try:
        client = get_client()
        Agent.instrument_all(
            InstrumentationSettings(
                include_binary_content=False,
                include_content=False,
            )
        )
        return client
    except Exception:
        logger.exception("Langfuse initialization failed; tracing is disabled")
        return None
