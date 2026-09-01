import json
import os
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import anyio
import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from src.services.audio.config import SpeechSettings
from src.services.audio.errors import SpeechProblem
from src.services.audio.models import TranscriptResult, ValidatedAudio

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
_SYSTEM_RANDOM = secrets.SystemRandom()


class _CombinedPhrase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str


class _Phrase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    locale: str | None = None


class _AzureResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    durationMilliseconds: int = Field(ge=0)
    combinedPhrases: list[_CombinedPhrase]
    phrases: list[_Phrase] = Field(default_factory=list)


class AzureSpeechClient:
    def __init__(
        self,
        settings: SpeechSettings,
        *,
        http_client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._jitter = jitter or (lambda: _SYSTEM_RANDOM.uniform(0.8, 1.2))
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=settings.endpoint.rstrip("/"),
            timeout=httpx.Timeout(
                connect=settings.connect_timeout_seconds,
                read=settings.read_timeout_seconds,
                write=settings.write_timeout_seconds,
                pool=settings.pool_timeout_seconds,
            ),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": "office-chatbot-azure-stt/0.6.0",
            },
        )

    async def transcribe(self, audio: ValidatedAudio, locale: str) -> TranscriptResult:
        key = self._speech_key()
        for attempt in range(1, self._settings.max_attempts + 1):
            try:
                response = await self._client.post(
                    "/speechtotext/transcriptions:transcribe",
                    params={"api-version": self._settings.api_version},
                    headers={"Ocp-Apim-Subscription-Key": key.get_secret_value()},
                    files={
                        "definition": (
                            None,
                            json.dumps(
                                {"locales": [locale], "profanityFilterMode": "Masked"},
                                separators=(",", ":"),
                            ),
                            "application/json",
                        ),
                        "audio": (
                            _safe_filename(audio.media_type),
                            audio.content,
                            audio.media_type,
                        ),
                    },
                )
            except httpx.TimeoutException as exc:
                if attempt < self._settings.max_attempts:
                    await self._sleep(self._retry_delay(attempt, None))
                    continue
                raise _timeout() from exc
            except httpx.TransportError as exc:
                if attempt < self._settings.max_attempts:
                    await self._sleep(self._retry_delay(attempt, None))
                    continue
                raise _unavailable() from exc

            if response.status_code == 200:
                return _parse_success(response, locale)
            if (
                response.status_code in _RETRYABLE_STATUS
                and attempt < self._settings.max_attempts
            ):
                await self._sleep(self._retry_delay(attempt, response))
                continue
            raise _map_failure(response)

        raise _unavailable()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _speech_key(self) -> SecretStr:
        value = os.getenv("AZURE_SPEECH_KEY")
        if (
            not value
            or value != value.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise SpeechProblem(
                503, "speech_not_configured", "Speech service is unavailable."
            )
        return SecretStr(value)

    def _retry_delay(self, attempt: int, response: httpx.Response | None) -> float:
        if response is not None:
            retry_after = _numeric_retry_after(response.headers.get("Retry-After"))
            if retry_after is not None:
                return min(retry_after, self._settings.retry_max_delay_seconds)
        delay = self._settings.retry_base_delay_seconds * (2 ** (attempt - 1))
        return float(
            min(delay * self._jitter(), self._settings.retry_max_delay_seconds)
        )


def _parse_success(response: httpx.Response, requested_locale: str) -> TranscriptResult:
    try:
        payload = _AzureResult.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        raise _unavailable() from exc
    text = "\n".join(
        phrase.text.strip() for phrase in payload.combinedPhrases if phrase.text.strip()
    )
    if not text:
        raise SpeechProblem(422, "no_speech", "No recognizable speech was found.")
    detected = next(
        (phrase.locale for phrase in payload.phrases if phrase.locale), None
    )
    return TranscriptResult(text=text, locale=detected or requested_locale)


def _map_failure(response: httpx.Response) -> SpeechProblem:
    if response.status_code == 400:
        return SpeechProblem(400, "invalid_audio", "Azure rejected the audio request.")
    if response.status_code == 413:
        return SpeechProblem(
            413, "audio_too_large", "Audio exceeds the accepted limit."
        )
    if response.status_code == 429:
        retry_after = max(
            1, round(_numeric_retry_after(response.headers.get("Retry-After")) or 1)
        )
        return SpeechProblem(
            429,
            "speech_rate_limited",
            "Speech capacity is temporarily limited.",
            retry_after,
        )
    if response.status_code == 408:
        return _timeout()
    if response.status_code in {401, 403}:
        return SpeechProblem(
            502,
            "speech_authentication_failed",
            "Speech transcription is unavailable.",
        )
    return _unavailable()


def _numeric_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        try:
            parsed_date = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=UTC)
        return max(0.0, (parsed_date - datetime.now(UTC)).total_seconds())
    return parsed if parsed >= 0 else None


def _safe_filename(media_type: str) -> str:
    extensions = {
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/wave": "wav",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/ogg": "ogg",
        "application/ogg": "ogg",
        "audio/webm": "webm",
        "audio/mp4": "m4a",
        "audio/x-m4a": "m4a",
    }
    return f"audio.{extensions.get(media_type, 'bin')}"


def _timeout() -> SpeechProblem:
    return SpeechProblem(504, "speech_timeout", "Speech transcription timed out.")


def _unavailable() -> SpeechProblem:
    return SpeechProblem(
        502, "speech_unavailable", "Speech transcription is unavailable."
    )
