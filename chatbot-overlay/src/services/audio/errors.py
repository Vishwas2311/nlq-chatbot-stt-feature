from dataclasses import dataclass

from fastapi.responses import JSONResponse


@dataclass(slots=True)
class SpeechProblem(Exception):
    status: int
    code: str
    message: str
    retry_after_seconds: int | None = None


def problem_response(problem: SpeechProblem, request_id: str) -> JSONResponse:
    headers = {"X-Request-ID": request_id, "X-Correlation-ID": request_id}
    if problem.retry_after_seconds is not None:
        headers["Retry-After"] = str(problem.retry_after_seconds)
    return JSONResponse(
        status_code=problem.status,
        media_type="application/problem+json",
        content={
            "code": problem.code,
            "message": problem.message,
            "request_id": request_id,
            "correlation_id": request_id,
        },
        headers=headers,
    )
