import hashlib
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol

from src.services.audio.config import SpeechSettings
from src.services.audio.errors import SpeechProblem
from src.services.audio.models import SpeechCaller


class AdmissionController(Protocol):
    def admit(self, caller: SpeechCaller) -> AbstractAsyncContextManager[None]: ...


class AsyncRedis(Protocol):
    async def eval(
        self, script: str, numkeys: int, *keys_and_args: str | int
    ) -> Any: ...


_ACQUIRE_SCRIPT = """
local now_parts = redis.call('TIME')
local now_ms = (tonumber(now_parts[1]) * 1000) + math.floor(tonumber(now_parts[2]) / 1000)
local window_ms = tonumber(ARGV[1])
local token = ARGV[2]
local lease_ms = tonumber(ARGV[3])
local limits = {tonumber(ARGV[4]), tonumber(ARGV[5]), tonumber(ARGV[6])}
local concurrency_limits = {tonumber(ARGV[7]), tonumber(ARGV[8])}

for index = 1, 3 do
    redis.call('ZREMRANGEBYSCORE', KEYS[index], 0, now_ms - window_ms)
    if redis.call('ZCARD', KEYS[index]) >= limits[index] then
        local oldest = redis.call('ZRANGE', KEYS[index], 0, 0, 'WITHSCORES')
        local retry_ms = window_ms
        if oldest[2] then
            retry_ms = math.max(1000, tonumber(oldest[2]) + window_ms - now_ms)
        end
        return {0, math.ceil(retry_ms / 1000)}
    end
end

for index = 4, 5 do
    redis.call('ZREMRANGEBYSCORE', KEYS[index], 0, now_ms)
    if redis.call('ZCARD', KEYS[index]) >= concurrency_limits[index - 3] then
        return {0, 1}
    end
end

for index = 1, 3 do
    redis.call('ZADD', KEYS[index], now_ms, token)
    redis.call('PEXPIRE', KEYS[index], window_ms + 1000)
end

local lease_expires_ms = now_ms + lease_ms
for index = 4, 5 do
    redis.call('ZADD', KEYS[index], lease_expires_ms, token)
    redis.call('PEXPIRE', KEYS[index], lease_ms + 1000)
end
return {1, 0}
"""

_RELEASE_SCRIPT = """
for index = 1, #KEYS do
    redis.call('ZREM', KEYS[index], ARGV[1])
end
return 1
"""

_LOGGER = logging.getLogger("chatbot.azure_stt")


class RedisAdmissionController:
    """Distributed limits for redis-py-compatible asynchronous Redis clients."""

    def __init__(self, redis: AsyncRedis, settings: SpeechSettings) -> None:
        self._redis = redis
        self._settings = settings

    @asynccontextmanager
    async def admit(self, caller: SpeechCaller) -> AsyncIterator[None]:
        token = uuid.uuid4().hex
        keys = self._keys(caller)
        try:
            result = await self._redis.eval(
                _ACQUIRE_SCRIPT,
                len(keys),
                *keys,
                60_000,
                token,
                self._settings.admission_lease_seconds * 1000,
                self._settings.global_requests_per_minute,
                self._settings.client_requests_per_minute,
                self._settings.principal_requests_per_minute,
                self._settings.max_concurrency,
                self._settings.max_concurrent_per_principal,
            )
        except Exception as exc:
            raise _admission_unavailable() from exc

        accepted, retry_after = _parse_redis_result(result)
        if not accepted:
            raise _rate_limited(retry_after)
        try:
            yield
        finally:
            try:
                await self._redis.eval(_RELEASE_SCRIPT, 2, *keys[3:], token)
            except Exception:  # noqa: BLE001 - expiring lease is the safe fallback
                # The expiring lease prevents a permanent capacity leak. Do not
                # expose Redis diagnostics or fail an otherwise valid response.
                _LOGGER.error("speech_admission_release_failed")

    def _keys(self, caller: SpeechCaller) -> tuple[str, str, str, str, str]:
        prefix = self._settings.redis_key_prefix
        client_key = _opaque_key(caller.client_id)
        principal_key = _opaque_key(caller.principal_id)
        return (
            f"{prefix}:rpm:global",
            f"{prefix}:rpm:client:{client_key}",
            f"{prefix}:rpm:principal:{principal_key}",
            f"{prefix}:concurrency:global",
            f"{prefix}:concurrency:principal:{principal_key}",
        )


def _parse_redis_result(result: Any) -> tuple[bool, int]:
    if not isinstance(result, (list, tuple)) or len(result) != 2:
        raise _admission_unavailable()
    try:
        accepted = int(result[0]) == 1
        retry_after = max(1, int(result[1]))
    except (TypeError, ValueError) as exc:
        raise _admission_unavailable() from exc
    return accepted, retry_after


def _opaque_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _rate_limited(retry_after: int) -> SpeechProblem:
    return SpeechProblem(
        429,
        "rate_limited",
        "Transcription request limit reached.",
        retry_after,
    )


def _admission_unavailable() -> SpeechProblem:
    return SpeechProblem(
        503,
        "admission_unavailable",
        "Transcription admission control is unavailable.",
        1,
    )
