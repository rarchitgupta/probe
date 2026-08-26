from __future__ import annotations

from datetime import UTC, datetime

import pytest

from qa_agent.environments import (
    EnvironmentCookie,
    EnvironmentDefinition,
    EnvironmentProfile,
    EnvironmentValue,
    resolve_environment,
    resolve_secret,
)


def test_resolves_browser_configuration_and_secret_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROBE_TEST_TOKEN", "token-value")
    monkeypatch.setenv("PROBE_TEST_PASSWORD", "secret-value")
    environment = EnvironmentProfile(
        id="environment-1",
        name="Staging",
        definition=EnvironmentDefinition(
            headers={"Authorization": EnvironmentValue(env="PROBE_TEST_TOKEN")},
            cookies=(
                EnvironmentCookie(
                    name="session", value=EnvironmentValue(value="cookie-value")
                ),
            ),
            secrets={"password": "PROBE_TEST_PASSWORD"},
        ),
        viewport_width=800,
        viewport_height=600,
        created_at=datetime.now(UTC),
    )

    resolved = resolve_environment(environment, "https://example.com/")

    assert resolved.headers == {"Authorization": "token-value"}
    assert resolved.cookies == [
        {
            "name": "session",
            "value": "cookie-value",
            "url": "https://example.com/",
        }
    ]
    assert resolved.viewport == {"width": 800, "height": 600}
    assert resolve_secret("{{secret:password}}", resolved.secrets) == "secret-value"
    assert resolve_secret("ordinary value", resolved.secrets) == "ordinary value"


def test_rejects_missing_environment_variable() -> None:
    with pytest.raises(ValueError, match="is not set"):
        EnvironmentValue(env="PROBE_MISSING_TEST_VALUE").resolve()
