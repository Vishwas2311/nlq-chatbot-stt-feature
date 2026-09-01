import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from src.services.audio.errors import SpeechProblem, problem_response
from src.services.audio.models import SpeechCaller, TranscriptionResponse
from src.services.audio.service import AudioTranscriptionService

_LOGGER = logging.getLogger("chatbot.azure_stt")


def create_speech_router(
    *,
    transcription_service: AudioTranscriptionService,
    authenticate: Callable[..., Any],
    caller_mapper: Callable[[Any], SpeechCaller],
) -> APIRouter:
    """Create the additive route using the chatbot's verified auth dependency."""

    router = APIRouter(prefix="/api/v1", tags=["speech"])

    @router.post(
        "/speech/transcriptions",
        response_model=TranscriptionResponse,
        responses={
            400: {},
            401: {},
            403: {},
            413: {},
            415: {},
            422: {},
            429: {},
            500: {},
            502: {},
            503: {},
            504: {},
        },
    )
    async def create_transcription(
        request: Request,
        response: Response,
        authenticated_identity: Any = Depends(authenticate),  # noqa: B008
    ) -> Any:
        request_id = str(
            getattr(request.state, "speech_request_id", None) or uuid.uuid4()
        )
        started = time.perf_counter()
        try:
            caller = caller_mapper(authenticated_identity)
            if (
                not isinstance(caller, SpeechCaller)
                or not _valid_caller_identifier(caller.principal_id)
                or not _valid_caller_identifier(caller.client_id)
            ):
                raise SpeechProblem(403, "not_authorized", "Caller is not authorized.")
            result = await transcription_service.transcribe(request, caller)
        except SpeechProblem as problem:
            _LOGGER.info(
                "speech_request_failed request_id=%s status=%d code=%s",
                request_id,
                problem.status,
                problem.code,
            )
            return problem_response(problem, request_id)
        except Exception:  # noqa: BLE001 - sanitize the public route boundary
            _LOGGER.error(
                "speech_request_failed request_id=%s status=500 code=internal_error",
                request_id,
            )
            return problem_response(
                SpeechProblem(
                    500,
                    "internal_error",
                    "The transcription request could not be completed.",
                ),
                request_id,
            )

        elapsed_ms = round((time.perf_counter() - started) * 1000)
        _LOGGER.info(
            "speech_request_completed request_id=%s status=200 audio_bytes=%d "
            "duration_ms=%d processing_ms=%d media_type=%s",
            request_id,
            result.audio_bytes,
            result.duration_milliseconds,
            elapsed_ms,
            result.media_type,
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = request_id
        return TranscriptionResponse(
            request_id=request_id,
            correlation_id=request_id,
            locale=result.locale,
            transcript=result.transcript,
            audio_duration_milliseconds=result.duration_milliseconds,
            status="succeeded",
        )

    return router


def _valid_caller_identifier(value: str) -> bool:
    return bool(value and not value.isspace() and len(value) <= 256)
