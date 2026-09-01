import io
import logging
import wave
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from starlette.formparsers import MultiPartParser

from src.core.middleware.request_size import SpeechBodyLimitMiddleware
from src.routes.speech import create_speech_router
from src.services.audio.config import SpeechSettings
from src.services.audio.models import SpeechCaller, TranscriptResult, ValidatedAudio
from src.services.audio.service import AudioTranscriptionService


class StubSpeechClient:
    def __init__(self) -> None:
        self.calls: list[tuple[ValidatedAudio, str]] = []

    async def transcribe(self, audio: ValidatedAudio, locale: str) -> TranscriptResult:
        self.calls.append((audio, locale))
        return TranscriptResult("PRIVATE-SYNTHETIC-TRANSCRIPT", locale)


class AllowAllAdmissionController:
    @asynccontextmanager
    async def admit(self, caller: SpeechCaller) -> AsyncIterator[None]:
        yield


async def verified_auth(
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    if authorization != "Bearer verified-test-token":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"subject": "test-user", "client": "test-client"}


def caller_mapper(identity: dict[str, str]) -> SpeechCaller:
    return SpeechCaller(identity["subject"], identity["client"])


def wav_audio(*, seconds: int = 1, rate: int = 16000, channels: int = 1) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * rate * seconds * channels)
    return output.getvalue()


def make_client(
    settings: SpeechSettings | None = None,
) -> tuple[TestClient, StubSpeechClient]:
    resolved = settings or SpeechSettings(
        endpoint="https://speech.test.invalid",
        allowed_endpoint_hosts=("speech.test.invalid",),
    )
    speech_client = StubSpeechClient()
    app = FastAPI()
    app.add_middleware(
        SpeechBodyLimitMiddleware,
        max_body_bytes=resolved.max_request_body_bytes,
        path="/api/v1/speech/transcriptions",
    )
    app.include_router(
        create_speech_router(
            transcription_service=AudioTranscriptionService(
                resolved,
                speech_client,  # type: ignore[arg-type]
                AllowAllAdmissionController(),
            ),
            authenticate=verified_auth,
            caller_mapper=caller_mapper,
        )
    )
    return TestClient(app), speech_client


def test_valid_audio_returns_provider_neutral_response_without_logging_transcript(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, speech_client = make_client()
    with client, caplog.at_level(logging.INFO, logger="chatbot.azure_stt"):
        response = client.post(
            "/api/v1/speech/transcriptions",
            headers={
                "Authorization": "Bearer verified-test-token",
                "X-Request-ID": "request-test-1",
            },
            files={"audio": ("sample.wav", wav_audio(), "audio/wav")},
            data={"locale": "en-IN"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "request_id": "request-test-1",
        "correlation_id": "request-test-1",
        "locale": "en-IN",
        "transcript": "PRIVATE-SYNTHETIC-TRANSCRIPT",
        "audio_duration_milliseconds": 1000,
        "status": "succeeded",
    }
    assert len(speech_client.calls) == 1
    assert "PRIVATE-SYNTHETIC-TRANSCRIPT" not in caplog.text
    assert response.headers["content-type"] == "application/json"


def test_authentication_occurs_before_audio_processing() -> None:
    client, speech_client = make_client()
    with client:
        response = client.post(
            "/api/v1/speech/transcriptions",
            files={"audio": ("sample.wav", b"not-audio", "audio/wav")},
        )
    assert response.status_code == 401
    assert not speech_client.calls


def test_authenticated_empty_body_returns_documented_400_problem() -> None:
    client, speech_client = make_client()
    with client:
        response = client.post(
            "/api/v1/speech/transcriptions",
            headers={"Authorization": "Bearer verified-test-token"},
        )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "invalid_request"
    assert not speech_client.calls


def test_declared_and_actual_media_must_match() -> None:
    client, speech_client = make_client()
    with client:
        response = client.post(
            "/api/v1/speech/transcriptions",
            headers={"Authorization": "Bearer verified-test-token"},
            files={"audio": ("fake.wav", b"not-audio", "audio/wav")},
        )
    assert response.status_code == 415
    assert not speech_client.calls


def test_audio_above_decoded_duration_is_rejected() -> None:
    configured = replace(
        SpeechSettings(
            endpoint="https://speech.test.invalid",
            allowed_endpoint_hosts=("speech.test.invalid",),
        ),
        max_decoded_seconds=1,
    )
    client, speech_client = make_client(configured)
    with client:
        response = client.post(
            "/api/v1/speech/transcriptions",
            headers={"Authorization": "Bearer verified-test-token"},
            files={"audio": ("long.wav", wav_audio(seconds=2), "audio/wav")},
        )
    assert response.status_code == 413
    assert not speech_client.calls


def test_large_accepted_audio_does_not_roll_to_temporary_file() -> None:
    configured = replace(
        SpeechSettings(
            endpoint="https://speech.test.invalid",
            allowed_endpoint_hosts=("speech.test.invalid",),
        ),
        max_upload_bytes=2 * 1024 * 1024,
        max_decoded_seconds=10,
    )
    client, speech_client = make_client(configured)
    large_audio = wav_audio(seconds=8, rate=48000, channels=2)
    assert len(large_audio) > 1024 * 1024
    with client:
        response = client.post(
            "/api/v1/speech/transcriptions",
            headers={"Authorization": "Bearer verified-test-token"},
            files={"audio": ("large.wav", large_audio, "audio/wav")},
        )
    assert response.status_code == 200
    assert len(speech_client.calls) == 1


def test_request_body_limit_rejects_before_provider_call() -> None:
    configured = replace(
        SpeechSettings(
            endpoint="https://speech.test.invalid",
            allowed_endpoint_hosts=("speech.test.invalid",),
        ),
        max_upload_bytes=1024,
        multipart_overhead_bytes=1024,
    )
    client, speech_client = make_client(configured)
    with client:
        response = client.post(
            "/api/v1/speech/transcriptions",
            headers={"Authorization": "Bearer verified-test-token"},
            content=b"x" * 4096,
        )
    assert response.status_code == 413
    assert not speech_client.calls


def test_empty_wav_returns_documented_422_problem() -> None:
    client, speech_client = make_client()
    with client:
        response = client.post(
            "/api/v1/speech/transcriptions",
            headers={"Authorization": "Bearer verified-test-token"},
            files={"audio": ("empty.wav", wav_audio(seconds=0), "audio/wav")},
        )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "invalid_audio"
    assert not speech_client.calls


def test_correlation_id_is_accepted_and_echoed() -> None:
    client, _ = make_client()
    with client:
        response = client.post(
            "/api/v1/speech/transcriptions",
            headers={
                "Authorization": "Bearer verified-test-token",
                "X-Correlation-ID": "correlation-test-1",
            },
            files={"audio": ("sample.wav", wav_audio(), "audio/wav")},
        )
    assert response.status_code == 200
    assert response.json()["correlation_id"] == "correlation-test-1"
    assert response.headers["X-Correlation-ID"] == "correlation-test-1"


def test_router_does_not_change_global_multipart_spool_setting() -> None:
    original = MultiPartParser.spool_max_size
    make_client()
    assert MultiPartParser.spool_max_size == original


def test_unexpected_dependency_error_is_sanitized(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class BrokenSpeechClient(StubSpeechClient):
        async def transcribe(
            self, audio: ValidatedAudio, locale: str
        ) -> TranscriptResult:
            raise RuntimeError("PRIVATE-DEPENDENCY-DIAGNOSTIC")

    settings = SpeechSettings(
        endpoint="https://speech.test.invalid",
        allowed_endpoint_hosts=("speech.test.invalid",),
    )
    app = FastAPI()
    app.add_middleware(
        SpeechBodyLimitMiddleware,
        max_body_bytes=settings.max_request_body_bytes,
        path="/api/v1/speech/transcriptions",
    )
    app.include_router(
        create_speech_router(
            transcription_service=AudioTranscriptionService(
                settings,
                BrokenSpeechClient(),  # type: ignore[arg-type]
                AllowAllAdmissionController(),
            ),
            authenticate=verified_auth,
            caller_mapper=caller_mapper,
        )
    )
    with (
        TestClient(app) as client,
        caplog.at_level(logging.ERROR, logger="chatbot.azure_stt"),
    ):
        response = client.post(
            "/api/v1/speech/transcriptions",
            headers={"Authorization": "Bearer verified-test-token"},
            files={"audio": ("sample.wav", wav_audio(), "audio/wav")},
        )
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "PRIVATE-DEPENDENCY-DIAGNOSTIC" not in response.text
    assert "PRIVATE-DEPENDENCY-DIAGNOSTIC" not in caplog.text


def test_invalid_caller_mapping_is_denied_without_provider_call() -> None:
    settings = SpeechSettings(
        endpoint="https://speech.test.invalid",
        allowed_endpoint_hosts=("speech.test.invalid",),
    )
    speech_client = StubSpeechClient()
    app = FastAPI()
    app.add_middleware(
        SpeechBodyLimitMiddleware,
        max_body_bytes=settings.max_request_body_bytes,
        path="/api/v1/speech/transcriptions",
    )
    app.include_router(
        create_speech_router(
            transcription_service=AudioTranscriptionService(
                settings,
                speech_client,  # type: ignore[arg-type]
                AllowAllAdmissionController(),
            ),
            authenticate=verified_auth,
            caller_mapper=lambda identity: object(),  # type: ignore[arg-type,return-value]
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/speech/transcriptions",
            headers={"Authorization": "Bearer verified-test-token"},
            files={"audio": ("sample.wav", wav_audio(), "audio/wav")},
        )
    assert response.status_code == 403
    assert not speech_client.calls
