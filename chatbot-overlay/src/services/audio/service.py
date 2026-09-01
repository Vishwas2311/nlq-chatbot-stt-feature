from dataclasses import dataclass

from anyio import to_thread
from fastapi import Request

from src.services.audio.azure_client import AzureSpeechClient
from src.services.audio.config import SpeechSettings
from src.services.audio.limits import AdmissionController
from src.services.audio.models import SpeechCaller
from src.services.audio.multipart import read_transcription_form
from src.services.audio.validation import validate_audio


@dataclass(frozen=True, slots=True)
class AudioTranscription:
    transcript: str
    locale: str
    media_type: str
    audio_bytes: int
    duration_milliseconds: int


class AudioTranscriptionService:
    """Application service that owns the complete transient STT workflow."""

    def __init__(
        self,
        settings: SpeechSettings,
        speech_client: AzureSpeechClient,
        admission: AdmissionController,
    ) -> None:
        self._settings = settings
        self._speech_client = speech_client
        self._admission = admission

    async def transcribe(
        self, request: Request, caller: SpeechCaller
    ) -> AudioTranscription:
        async with self._admission.admit(caller):
            content, media_type, locale = await read_transcription_form(
                request, self._settings
            )
            validated = await to_thread.run_sync(
                validate_audio,
                content,
                media_type,
                self._settings.max_decoded_seconds,
            )
            result = await self._speech_client.transcribe(validated, locale)

        return AudioTranscription(
            transcript=result.text,
            locale=result.locale,
            media_type=validated.media_type,
            audio_bytes=len(validated.content),
            duration_milliseconds=validated.duration_milliseconds,
        )
