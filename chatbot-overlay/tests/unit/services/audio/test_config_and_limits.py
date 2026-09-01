from typing import Any

import pytest

from src.services.audio.config import SpeechSettings
from src.services.audio.errors import SpeechProblem
from src.services.audio.limits import RedisAdmissionController
from src.services.audio.models import SpeechCaller


def test_configuration_loads_names_without_exposing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_SPEECH_ENDPOINT", "https://speech.test.invalid")
    monkeypatch.setenv("AZURE_SPEECH_ALLOWED_HOSTS", "speech.test.invalid")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "must-not-enter-settings")
    settings = SpeechSettings.from_environment()
    assert settings.endpoint == "https://speech.test.invalid"
    assert "must-not-enter-settings" not in repr(settings)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://speech.test.invalid",
        "https://speech.test.invalid/a/path",
        "https://speech.test.invalid?query=true",
        "not-an-endpoint",
    ],
)
def test_invalid_endpoint_is_rejected(endpoint: str) -> None:
    with pytest.raises(ValueError):
        SpeechSettings(
            endpoint=endpoint,
            allowed_endpoint_hosts=("speech.test.invalid",),
        )


def test_endpoint_host_must_be_explicitly_allowlisted() -> None:
    with pytest.raises(ValueError, match="allowlisted"):
        SpeechSettings(
            endpoint="https://different.test.invalid",
            allowed_endpoint_hosts=("speech.test.invalid",),
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user:password@speech.test.invalid",
        "https://speech.test.invalid:8443",
    ],
)
def test_endpoint_rejects_credentials_and_custom_ports(endpoint: str) -> None:
    with pytest.raises(ValueError):
        SpeechSettings(
            endpoint=endpoint,
            allowed_endpoint_hosts=("speech.test.invalid",),
        )


class StubRedis:
    def __init__(self, acquire_result: object = (1, 0), *, fail: bool = False) -> None:
        self.acquire_result = acquire_result
        self.fail = fail
        self.calls: list[tuple[str, int, tuple[str | int, ...]]] = []

    async def eval(self, script: str, numkeys: int, *keys_and_args: str | int) -> Any:
        self.calls.append((script, numkeys, keys_and_args))
        if self.fail:
            raise ConnectionError("private redis diagnostic")
        if numkeys == 5:
            return self.acquire_result
        return 1


@pytest.mark.asyncio
async def test_redis_controller_acquires_and_releases_without_plain_identifiers() -> (
    None
):
    settings = SpeechSettings(
        endpoint="https://speech.test.invalid",
        allowed_endpoint_hosts=("speech.test.invalid",),
    )
    redis = StubRedis()
    controller = RedisAdmissionController(redis, settings)
    async with controller.admit(SpeechCaller("private-principal", "private-client")):
        pass
    assert [call[1] for call in redis.calls] == [5, 2]
    serialized = repr(redis.calls)
    assert "private-principal" not in serialized
    assert "private-client" not in serialized


@pytest.mark.asyncio
async def test_redis_controller_fails_closed_when_redis_is_unavailable() -> None:
    settings = SpeechSettings(
        endpoint="https://speech.test.invalid",
        allowed_endpoint_hosts=("speech.test.invalid",),
    )
    controller = RedisAdmissionController(StubRedis(fail=True), settings)
    with pytest.raises(SpeechProblem) as error:
        async with controller.admit(SpeechCaller("principal", "client")):
            pass
    assert error.value.status == 503
    assert "redis" not in error.value.message.lower()


@pytest.mark.asyncio
async def test_redis_controller_returns_retry_after_when_limit_is_reached() -> None:
    settings = SpeechSettings(
        endpoint="https://speech.test.invalid",
        allowed_endpoint_hosts=("speech.test.invalid",),
    )
    controller = RedisAdmissionController(StubRedis((0, 9)), settings)
    with pytest.raises(SpeechProblem) as error:
        async with controller.admit(SpeechCaller("principal", "client")):
            pass
    assert error.value.status == 429
    assert error.value.retry_after_seconds == 9
