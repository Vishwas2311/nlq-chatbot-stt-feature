# Stable STT error contract

Package-generated failures use sanitized `application/problem+json` containing
`code`, `message`, `request_id` and `correlation_id`. Provider bodies, audio,
transcripts, credentials and internal exception text are never returned.

| HTTP | Code | Meaning / caller action |
| ---: | --- | --- |
| 400 | `invalid_request` | Correct malformed or duplicate multipart fields. |
| 400 | `invalid_audio` | Azure rejected the otherwise parseable audio; re-record. |
| 401/403 | Host auth policy | Reauthenticate or request authorization. |
| 403 | `not_authorized` | Verified identity could not map to an approved caller. |
| 413 | `audio_too_large` | Use a smaller upload. |
| 413 | `audio_too_long` | Use a shorter recording. |
| 415 | `unsupported_audio` | Use approved audio-only WAV, MP3, OGG, WebM or M4A. |
| 422 | `invalid_audio` | Audio is empty, corrupt, unreadable or has a non-audio stream. |
| 422 | `no_speech` | Ask the user to speak again. |
| 429 | `rate_limited` | Local distributed limit; respect `Retry-After`. |
| 429 | `speech_rate_limited` | Azure throttled the request; respect `Retry-After`. |
| 500 | `internal_error` | Report the request ID; do not expose diagnostics. |
| 500 | `unsafe_upload_path` | Server could not retain the approved memory-only path. |
| 502 | `speech_authentication_failed` | Operator must inspect/rotate backend credential. |
| 502 | `speech_unavailable` | Provider/transport failure; retry later. |
| 503 | `speech_not_configured` | Operator must configure the runtime secret. |
| 503 | `admission_unavailable` | Restore Redis; never bypass admission in production. |
| 504 | `speech_timeout` | Bounded Azure timeout; retry later. |

Successful and package-generated failure responses include `X-Request-ID` and
`X-Correlation-ID`; rate-limit failures may include `Retry-After`.
