from collections.abc import Awaitable, Callable, Coroutine

import httpx
import pytest

from src.services.audio.azure_client import AzureSpeechClient
from src.services.audio.config import SpeechSettings
from src.services.audio.errors import SpeechProblem
from src.services.audio.models import ValidatedAudio


def settings(**overrides: object) -> SpeechSettings:
    values: dict[str, object] = {
        "endpoint": "https://speech.test.invalid",
        "allowed_endpoint_hosts": ("speech.test.invalid",),
        "max_attempts": 2,
        "retry_base_delay_seconds": 0.01,
        "retry_max_delay_seconds": 0.01,
    }
    values.update(overrides)
    return SpeechSettings(**values)  # type: ignore[arg-type]


def sample_audio() -> ValidatedAudio:
    return ValidatedAudio(b"RIFF-synthetic", "audio/wav", 250)


async def no_sleep(delay: float) -> None:
    assert delay >= 0


def client_with_handler(
    handler: Callable[[httpx.Request], Coroutine[None, None, httpx.Response]],
    configured: SpeechSettings | None = None,
    *,
    sleep: Callable[[float], Awaitable[None]] = no_sleep,
) -> tuple[AzureSpeechClient, httpx.AsyncClient]:
    resolved = configured or settings()
    http_client = httpx.AsyncClient(
        base_url=resolved.endpoint,
        transport=httpx.MockTransport(handler),
    )
    return (
        AzureSpeechClient(
            resolved,
            http_client=http_client,
            sleep=sleep,
            jitter=lambda: 1.0,
        ),
        http_client,
    )


@pytest.mark.asyncio
async def test_expected_fast_transcription_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_SPEECH_KEY", "synthetic-test-key")

    async def handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        assert request.url.path == "/speechtotext/transcriptions:transcribe"
        assert request.url.params["api-version"] == "2025-10-15"
        assert request.headers["Ocp-Apim-Subscription-Key"] == "synthetic-test-key"
        assert b'"locales":["en-IN"]' in body
        assert b"synthetic-test-key" not in body
        return httpx.Response(
            200,
            json={
                "durationMilliseconds": 250,
                "combinedPhrases": [{"text": "Synthetic transcript"}],
                "phrases": [{"locale": "en-IN"}],
            },
        )

    client, http_client = client_with_handler(handler)
    try:
        result = await client.transcribe(sample_audio(), "en-IN")
    finally:
        await http_client.aclose()
    assert result.text == "Synthetic transcript"


@pytest.mark.asyncio
async def test_transient_failure_retries_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_SPEECH_KEY", "synthetic-test-key")
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, text="raw-provider-content")

    client, http_client = client_with_handler(handler)
    try:
        with pytest.raises(SpeechProblem) as error:
            await client.transcribe(sample_audio(), "en-IN")
    finally:
        await http_client.aclose()
    assert attempts == 2
    assert error.value.status == 502
    assert "raw-provider-content" not in error.value.message


@pytest.mark.asyncio
async def test_permanent_auth_failure_is_sanitized_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_SPEECH_KEY", "synthetic-test-key")
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, text="credential diagnostic")

    client, http_client = client_with_handler(handler)
    try:
        with pytest.raises(SpeechProblem) as error:
            await client.transcribe(sample_audio(), "en-IN")
    finally:
        await http_client.aclose()
    assert attempts == 1
    assert error.value.status == 502
    assert error.value.code == "speech_authentication_failed"
    assert "credential diagnostic" not in error.value.message


@pytest.mark.asyncio
async def test_missing_key_fails_closed() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Azure must not be called")

    client, http_client = client_with_handler(handler)
    try:
        with pytest.raises(SpeechProblem) as error:
            await client.transcribe(sample_audio(), "en-IN")
    finally:
        await http_client.aclose()
    assert error.value.status == 503


@pytest.mark.asyncio
async def test_malformed_key_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_SPEECH_KEY", "synthetic-key\nheader-injection")

    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Azure must not be called")

    client, http_client = client_with_handler(handler)
    try:
        with pytest.raises(SpeechProblem) as error:
            await client.transcribe(sample_audio(), "en-IN")
    finally:
        await http_client.aclose()
    assert error.value.status == 503


@pytest.mark.asyncio
async def test_invalid_success_payload_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_SPEECH_KEY", "synthetic-test-key")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="private invalid provider body")

    client, http_client = client_with_handler(handler)
    try:
        with pytest.raises(SpeechProblem) as error:
            await client.transcribe(sample_audio(), "en-IN")
    finally:
        await http_client.aclose()
    assert error.value.status == 502
    assert "private invalid provider body" not in error.value.message


@pytest.mark.asyncio
async def test_no_speech_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_SPEECH_KEY", "synthetic-test-key")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "durationMilliseconds": 250,
                "combinedPhrases": [{"text": "  "}],
                "phrases": [],
            },
        )

    client, http_client = client_with_handler(handler)
    try:
        with pytest.raises(SpeechProblem) as error:
            await client.transcribe(sample_audio(), "en-IN")
    finally:
        await http_client.aclose()
    assert error.value.status == 422
    assert error.value.code == "no_speech"


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_SPEECH_KEY", "synthetic-test-key")
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("private upstream diagnostic", request=request)

    client, http_client = client_with_handler(handler, settings(max_attempts=1))
    try:
        with pytest.raises(SpeechProblem) as error:
            await client.transcribe(sample_audio(), "en-IN")
    finally:
        await http_client.aclose()
    assert attempts == 1
    assert error.value.status == 504
    assert "private upstream diagnostic" not in error.value.message


@pytest.mark.parametrize(
    ("provider_status", "expected_status", "expected_code"),
    [
        (400, 400, "invalid_audio"),
        (408, 504, "speech_timeout"),
        (413, 413, "audio_too_large"),
        (429, 429, "speech_rate_limited"),
        (500, 502, "speech_unavailable"),
    ],
)
@pytest.mark.asyncio
async def test_provider_statuses_are_mapped_to_sanitized_problems(
    monkeypatch: pytest.MonkeyPatch,
    provider_status: int,
    expected_status: int,
    expected_code: str,
) -> None:
    monkeypatch.setenv("AZURE_SPEECH_KEY", "synthetic-test-key")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            provider_status,
            headers={"Retry-After": "7"},
            text="PRIVATE-PROVIDER-BODY",
        )

    client, http_client = client_with_handler(handler, settings(max_attempts=1))
    try:
        with pytest.raises(SpeechProblem) as error:
            await client.transcribe(sample_audio(), "en-IN")
    finally:
        await http_client.aclose()
    assert error.value.status == expected_status
    assert error.value.code == expected_code
    assert "PRIVATE-PROVIDER-BODY" not in error.value.message
    if provider_status == 429:
        assert error.value.retry_after_seconds == 7


@pytest.mark.asyncio
async def test_transport_failure_is_bounded_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_SPEECH_KEY", "synthetic-test-key")

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("PRIVATE-NETWORK-DIAGNOSTIC", request=request)

    client, http_client = client_with_handler(handler, settings(max_attempts=1))
    try:
        with pytest.raises(SpeechProblem) as error:
            await client.transcribe(sample_audio(), "en-IN")
    finally:
        await http_client.aclose()
    assert error.value.status == 502
    assert "PRIVATE-NETWORK-DIAGNOSTIC" not in error.value.message
