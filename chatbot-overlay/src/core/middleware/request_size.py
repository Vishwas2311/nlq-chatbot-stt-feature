import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.services.audio.errors import SpeechProblem, problem_response

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class SpeechBodyLimitMiddleware:
    """Bounds only the integration route and leaves existing chatbot routes unchanged."""

    def __init__(self, app: ASGIApp, max_body_bytes: int, path: str) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.path = path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != self.path:
            await self.app(scope, receive, send)
            return
        raw_headers = scope.get("headers", [])
        headers = dict(raw_headers)
        supplied_id = headers.get(
            b"x-request-id", headers.get(b"x-correlation-id", b"")
        )
        decoded_id = supplied_id.decode("ascii", errors="ignore")
        request_id = (
            decoded_id
            if _REQUEST_ID_PATTERN.fullmatch(decoded_id)
            else str(uuid.uuid4())
        )
        scope.setdefault("state", {})["speech_request_id"] = request_id
        supplied_lengths = [
            value for name, value in raw_headers if name == b"content-length"
        ]
        if supplied_lengths:
            try:
                if len(set(supplied_lengths)) != 1:
                    raise ValueError
                supplied_length = int(supplied_lengths[0])
                if supplied_length < 0:
                    raise ValueError
                if supplied_length > self.max_body_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await self._invalid(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise _BodyLimitExceeded
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyLimitExceeded:
            await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = problem_response(
            SpeechProblem(413, "audio_too_large", "Audio upload is too large."),
            _request_id(scope),
        )
        await response(scope, receive, send)

    async def _invalid(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = problem_response(
            SpeechProblem(400, "invalid_request", "Content-Length is invalid."),
            _request_id(scope),
        )
        await response(scope, receive, send)


class _BodyLimitExceeded(Exception):
    pass


def _request_id(scope: Scope) -> str:
    return str(scope.get("state", {}).get("speech_request_id", "unavailable"))
