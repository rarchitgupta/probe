from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SECRET_PLACEHOLDER = re.compile(r"^\{\{secret:([A-Za-z][A-Za-z0-9_-]*)\}\}$")
EnvName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]


class EnvironmentValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | None = None
    env: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")

    @model_validator(mode="after")
    def exactly_one_source(self) -> Self:
        if (self.value is None) == (self.env is None):
            raise ValueError("Provide exactly one of value or env")
        return self

    def resolve(self) -> str:
        if self.value is not None:
            return self.value
        assert self.env is not None
        try:
            return os.environ[self.env]
        except KeyError:
            raise ValueError(f"Environment variable {self.env!r} is not set") from None


class EnvironmentCookie(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: EnvironmentValue
    domain: str | None = None
    path: str = "/"


class EnvironmentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headers: dict[str, EnvironmentValue] = Field(default_factory=dict)
    cookies: tuple[EnvironmentCookie, ...] = ()
    secrets: dict[str, EnvName] = Field(default_factory=dict)


@dataclass(frozen=True)
class EnvironmentProfile:
    id: str
    name: str
    definition: EnvironmentDefinition
    viewport_width: int
    viewport_height: int
    created_at: datetime


@dataclass(frozen=True)
class ResolvedEnvironment:
    headers: dict[str, str]
    cookies: list[dict[str, object]]
    secrets: dict[str, str]
    viewport: dict[str, int]


def resolve_environment(
    environment: EnvironmentProfile | None, start_url: str
) -> ResolvedEnvironment:
    if not environment:
        return ResolvedEnvironment({}, [], {}, {"width": 1280, "height": 720})
    definition = environment.definition
    cookies: list[dict[str, object]] = []
    for cookie in definition.cookies:
        resolved: dict[str, object] = {
            "name": cookie.name,
            "value": cookie.value.resolve(),
        }
        if cookie.domain:
            resolved.update(domain=cookie.domain, path=cookie.path)
        else:
            resolved["url"] = start_url
        cookies.append(resolved)
    return ResolvedEnvironment(
        headers={name: value.resolve() for name, value in definition.headers.items()},
        cookies=cookies,
        secrets={
            name: EnvironmentValue(env=env).resolve()
            for name, env in definition.secrets.items()
        },
        viewport={
            "width": environment.viewport_width,
            "height": environment.viewport_height,
        },
    )


def resolve_secret(value: str, secrets: dict[str, str]) -> str:
    match = SECRET_PLACEHOLDER.fullmatch(value)
    if not match:
        return value
    try:
        return secrets[match.group(1)]
    except KeyError:
        raise ValueError(f"Unknown secret placeholder {value!r}") from None
