# Security regression coverage

Security scenarios are executable in the neighboring suites to avoid duplicate
test setup:

- `integration/test_speech_route.py`: authentication-before-parsing, caller
  authorization, body/duration limits, sanitized unexpected failures and
  transcript-free logs.
- `unit/services/audio/test_azure_client.py`: missing/malformed key, bounded
  retry, provider status mapping, timeouts, transport failures and raw-response
  redaction.
- `unit/services/audio/test_config_and_limits.py`: endpoint allowlist, HTTPS
  enforcement, opaque Redis identifiers and fail-closed admission control.

Frontend security cases belong in the target chatbot's existing UI test file,
because this handoff deliberately adds no second runtime JavaScript module.
Cover bearer-token use, absence of Azure keys, multipart boundaries, oversize
rejection, safe errors and microphone cleanup there.

Do not delete these cases when merging them into the target repository's test
conventions.
