from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlsplit


class PolicyViolation(Exception):
    pass


def origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return f"{parsed.scheme}:"


@dataclass(frozen=True)
class ExecutionPolicy:
    max_actions: int = 50
    timeout_seconds: float = 60
    allowed_origins: frozenset[str] = frozenset()

    def for_start_url(self, url: str) -> ExecutionPolicy:
        if self.max_actions < 1:
            raise ValueError("max_actions must be at least 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        if self.allowed_origins:
            return self
        return ExecutionPolicy(
            max_actions=self.max_actions,
            timeout_seconds=self.timeout_seconds,
            allowed_origins=frozenset({origin(url)}),
        )


class ExecutionGuard:
    def __init__(self, policy: ExecutionPolicy) -> None:
        self.policy = policy
        self.actions = 0
        self._deadline = monotonic() + policy.timeout_seconds

    def check_url(self, url: str) -> None:
        current_origin = origin(url)
        if current_origin not in self.policy.allowed_origins:
            raise PolicyViolation(f"Origin {current_origin!r} is not allowed")

    def record_action(self) -> None:
        if self.actions >= self.policy.max_actions:
            raise PolicyViolation(
                f"Action limit of {self.policy.max_actions} reached"
            )
        self.actions += 1

    @property
    def remaining_seconds(self) -> float:
        return max(0, self._deadline - monotonic())
