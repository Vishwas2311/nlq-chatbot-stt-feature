from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

_REDIS_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9:_-]{1,64}$")


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class SpeechSettings:
    endpoint: str
    allowed_endpoint_hosts: tuple[str, ...]
    api_version: str = "2025-10-15"
    default_locale: str = "en-IN"
    allowed_locales: tuple[str, ...] = ("en-IN",)
    max_upload_bytes: int = 20 * 1024 * 1024
    multipart_overhead_bytes: int = 128 * 1024
    max_decoded_seconds: int = 120
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 60.0
    write_timeout_seconds: float = 15.0
    pool_timeout_seconds: float = 5.0
    max_attempts: int = 2
    retry_base_delay_seconds: float = 0.25
    retry_max_delay_seconds: float = 2.0
    principal_requests_per_minute: int = 5
    client_requests_per_minute: int = 100
    global_requests_per_minute: int = 400
    max_concurrency: int = 20
    max_concurrent_per_principal: int = 1
    admission_lease_seconds: int = 300
    redis_key_prefix: str = "speech:admission"

    def __post_init__(self) -> None:
        parsed = urlsplit(self.endpoint)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not hostname:
            raise ValueError("Azure Speech endpoint must be an HTTPS origin")
        if parsed.username or parsed.password or parsed.port not in {None, 443}:
            raise ValueError(
                "Azure Speech endpoint must not contain credentials or a custom port"
            )
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError(
                "Azure Speech endpoint must not contain path, query or fragment"
            )
        allowed_hosts = tuple(
            host.lower().rstrip(".") for host in self.allowed_endpoint_hosts
        )
        if not allowed_hosts or hostname not in allowed_hosts:
            raise ValueError("Azure Speech endpoint host is not explicitly allowlisted")
        if self.api_version != "2025-10-15":
            raise ValueError("This integration kit is pinned to Speech API 2025-10-15")
        if self.default_locale not in self.allowed_locales:
            raise ValueError("Default locale must be included in allowed locales")
        if self.max_attempts not in {1, 2}:
            raise ValueError("Maximum attempts must be 1 or 2")
        if self.retry_max_delay_seconds < self.retry_base_delay_seconds:
            raise ValueError("Retry maximum must be at least the base delay")
        if self.max_concurrent_per_principal > self.max_concurrency:
            raise ValueError(
                "Per-principal concurrency cannot exceed global concurrency"
            )
        if not _REDIS_PREFIX_PATTERN.fullmatch(self.redis_key_prefix):
            raise ValueError("Redis key prefix contains unsupported characters")

    @property
    def max_request_body_bytes(self) -> int:
        return self.max_upload_bytes + self.multipart_overhead_bytes

    @classmethod
    def from_environment(cls) -> SpeechSettings:
        endpoint = os.getenv("AZURE_SPEECH_ENDPOINT", "").strip()
        if not endpoint:
            raise ValueError("AZURE_SPEECH_ENDPOINT is required")
        allowed_endpoint_hosts = tuple(
            value.strip().lower().rstrip(".")
            for value in os.getenv("AZURE_SPEECH_ALLOWED_HOSTS", "").split(",")
            if value.strip()
        )
        if not allowed_endpoint_hosts:
            raise ValueError("AZURE_SPEECH_ALLOWED_HOSTS is required")
        locales = tuple(
            value.strip()
            for value in os.getenv("SPEECH_ALLOWED_LOCALES", "en-IN").split(",")
            if value.strip()
        )
        return cls(
            endpoint=endpoint,
            allowed_endpoint_hosts=allowed_endpoint_hosts,
            api_version=os.getenv("AZURE_SPEECH_API_VERSION", "2025-10-15"),
            default_locale=os.getenv("SPEECH_DEFAULT_LOCALE", "en-IN"),
            allowed_locales=locales,
            max_upload_bytes=_positive_int("SPEECH_MAX_UPLOAD_BYTES", 20 * 1024 * 1024),
            max_decoded_seconds=_positive_int("SPEECH_MAX_DECODED_SECONDS", 120),
            connect_timeout_seconds=_positive_float(
                "SPEECH_CONNECT_TIMEOUT_SECONDS", 5
            ),
            read_timeout_seconds=_positive_float("SPEECH_READ_TIMEOUT_SECONDS", 60),
            write_timeout_seconds=_positive_float("SPEECH_WRITE_TIMEOUT_SECONDS", 15),
            pool_timeout_seconds=_positive_float("SPEECH_POOL_TIMEOUT_SECONDS", 5),
            max_attempts=_positive_int("SPEECH_MAX_ATTEMPTS", 2),
            retry_base_delay_seconds=_positive_float(
                "SPEECH_RETRY_BASE_DELAY_SECONDS", 0.25
            ),
            retry_max_delay_seconds=_positive_float(
                "SPEECH_RETRY_MAX_DELAY_SECONDS", 2
            ),
            principal_requests_per_minute=_positive_int(
                "SPEECH_PRINCIPAL_REQUESTS_PER_MINUTE", 5
            ),
            client_requests_per_minute=_positive_int(
                "SPEECH_CLIENT_REQUESTS_PER_MINUTE", 100
            ),
            global_requests_per_minute=_positive_int(
                "SPEECH_GLOBAL_REQUESTS_PER_MINUTE", 400
            ),
            max_concurrency=_positive_int("SPEECH_MAX_CONCURRENCY", 20),
            max_concurrent_per_principal=_positive_int(
                "SPEECH_MAX_CONCURRENT_PER_PRINCIPAL", 1
            ),
            admission_lease_seconds=_positive_int(
                "SPEECH_ADMISSION_LEASE_SECONDS", 300
            ),
            redis_key_prefix=os.getenv("SPEECH_REDIS_KEY_PREFIX", "speech:admission"),
        )
