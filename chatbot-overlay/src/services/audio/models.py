from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True, slots=True)
class SpeechCaller:
    principal_id: str
    client_id: str


@dataclass(frozen=True, slots=True)
class ValidatedAudio:
    content: bytes
    media_type: str
    duration_milliseconds: int


@dataclass(frozen=True, slots=True)
class TranscriptResult:
    text: str
    locale: str


class TranscriptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    correlation_id: str
    locale: str
    transcript: str
    audio_duration_milliseconds: int = Field(ge=0)
    status: Literal["succeeded"]
