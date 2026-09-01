from collections.abc import AsyncGenerator

from fastapi import Request
from starlette.datastructures import Headers, UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException, MultiPartParser

from src.services.audio.config import SpeechSettings
from src.services.audio.errors import SpeechProblem


async def read_transcription_form(
    request: Request, settings: SpeechSettings
) -> tuple[bytes, str, str]:
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise _invalid("Content-Type must be multipart/form-data.")

    parser = _SpeechMultiPartParser(
        request.headers,
        request.stream(),
        spool_max_size=settings.max_request_body_bytes,
        max_files=1,
        max_fields=1,
        max_part_size=settings.max_upload_bytes,
    )
    try:
        form = await parser.parse()
        try:
            if any(key not in {"audio", "locale"} for key in form):
                raise _invalid("Only audio and locale fields are accepted.")
            if len(form.getlist("audio")) != 1 or len(form.getlist("locale")) > 1:
                raise _invalid(
                    "Exactly one audio file and at most one locale are accepted."
                )
            upload = form.get("audio")
            if not isinstance(upload, UploadFile):
                raise _invalid("One audio file is required.")
            locale = form.get("locale", settings.default_locale)
            if not isinstance(locale, str) or locale not in settings.allowed_locales:
                raise _invalid("The requested locale is not enabled.")
            content = await _read_bounded(upload, settings.max_upload_bytes)
            if getattr(upload.file, "_rolled", False):
                raise SpeechProblem(
                    500,
                    "unsafe_upload_path",
                    "The request could not be processed safely.",
                )
            return content, upload.content_type or "application/octet-stream", locale
        finally:
            await form.close()
    except SpeechProblem:
        raise
    except (MultiPartException, StarletteHTTPException) as exc:
        raise _invalid("Malformed multipart request.") from exc


class _SpeechMultiPartParser(MultiPartParser):
    """Request-scoped parser that never changes Starlette process-wide state."""

    def __init__(
        self,
        headers: Headers,
        stream: AsyncGenerator[bytes, None],
        *,
        spool_max_size: int,
        max_files: int,
        max_fields: int,
        max_part_size: int,
    ) -> None:
        self.spool_max_size = spool_max_size
        super().__init__(
            headers,
            stream,
            max_files=max_files,
            max_fields=max_fields,
            max_part_size=max_part_size,
        )


async def _read_bounded(upload: UploadFile, limit: int) -> bytes:
    content = bytearray()
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        if len(content) + len(chunk) > limit:
            raise SpeechProblem(413, "audio_too_large", "Audio upload is too large.")
        content.extend(chunk)
    if not content:
        raise SpeechProblem(422, "invalid_audio", "Audio is empty or invalid.")
    return bytes(content)


def _invalid(message: str) -> SpeechProblem:
    return SpeechProblem(400, "invalid_request", message)
