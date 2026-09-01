# GitHub Copilot merge guide — Azure STT into the existing chatbot

## Intended result

Merge Azure Speech-to-Text as one isolated capability inside the existing
FastAPI chatbot. There is one repository, one chatbot process and one
deployment. This package does not introduce a second microservice.

Known target paths from the office repository evidence:

```text
main chatbot backend/
├── _web/
├── artifacts/
├── mcp_server/
├── requirements/
│   └── api.txt
├── src/
│   ├── api.py                 # existing FastAPI entry point
│   ├── config.py              # existing environment configuration
│   ├── llm.py
│   ├── audit_db.py
│   └── services/
│       └── __init__.py        # existing service lifecycle
├── tests/
└── .env.example
```

The deeper directories in `chatbot-overlay/` are the approved STT target
layout. They are not proof that those directories already exist in the office
repository.

`frontend-reference/` is a complete tested UI replica for behavioral and code
review. It is not a replacement frontend and must not be copied wholesale.

## Non-negotiable merge rules

1. Create a feature branch and record the existing test result first.
2. Inspect the real files before editing. Never infer symbols from this guide.
3. Never replace `src/api.py`, `src/config.py`, `src/services/__init__.py`,
   `requirements/api.txt`, `_web` controller files or existing `__init__.py`
   files wholesale.
4. Copy new files, then merge only the documented additive wiring.
5. Do not change `/ews-chatbot/chat`, Oracle, Redis history, MCP, NL2SQL, LLM,
   session, response-formatting or existing frontend send behavior.
6. Never write an Azure key, bearer token or real company endpoint into source,
   tests, screenshots, logs or this package.
7. Do not expose the Azure Speech key to `_web/`. The browser calls the trusted
   chatbot route with the chatbot user's bearer token.
8. Authentication must verify JWT signature, algorithm, issuer, audience and
   expiry. Do not attach this route to code using `verify_signature=False`.
9. Use the existing asynchronous Redis connection for distributed limits in
   production. Do not create an in-memory production limiter.
10. Audio and transcript content are transient. Do not persist or log them.

## Step 1 — inspect and stop on uncertainty

Ask Copilot to report, without modifying code:

- FastAPI app symbol and exact construction location in `src/api.py`.
- Existing lifespan/startup/shutdown functions.
- Real verified authentication dependency and verified identity shape.
- Async Redis client symbol and lifecycle.
- Existing `Config` dataclass conventions.
- Actual frontend HTML/template, main controller, textbox, send button and
  token-access function.
- Installed FastAPI, Starlette, Pydantic, httpx, redis and Python versions.

Stop and request a human decision if verified authentication, an async Redis
client, the frontend token source or the lifecycle location cannot be proven.

## Step 2 — copy only new capability files

Copy these paths from `chatbot-overlay/` while preserving the target files:

```text
src/services/audio/
src/routes/speech.py
src/core/middleware/request_size.py
tests/unit/services/audio/
tests/integration/test_speech_route.py
```

For any provided `__init__.py`, create it only if missing. If it exists, merge
exports without removing target content.

## Step 3 — merge dependency delta

Review `integration/requirements-api.delta.txt`. Add only missing compatible
dependencies to `requirements/api.txt`, respecting the repository's existing
constraints/lock process. Re-resolve and vulnerability-scan dependencies.

## Step 4 — merge configuration

Use the names in `integration/speech.env.example`. The target may map them into
its existing `Config` dataclass, but `SpeechSettings.from_environment()` must
still receive the same runtime values. Add placeholders only to `.env.example`.

`AZURE_SPEECH_KEY` must come from the approved secret manager or protected
runtime environment. The photographed key from development must remain rotated.

## Step 5 — wire the existing service lifecycle

Adapt the following to the actual lifecycle symbols. Construct one client per
application process and close it at shutdown:

```python
from src.services.audio import (
    AudioTranscriptionService,
    AzureSpeechClient,
    RedisAdmissionController,
    SpeechSettings,
)

speech_settings = SpeechSettings.from_environment()
azure_speech_client = AzureSpeechClient(speech_settings)
speech_admission = RedisAdmissionController(existing_async_redis, speech_settings)
audio_transcription_service = AudioTranscriptionService(
    speech_settings,
    azure_speech_client,
    speech_admission,
)

# In the existing shutdown/finally path:
await azure_speech_client.aclose()
```

Do not initialize this at import time if the chatbot already uses a lifespan
container. Follow its established lifecycle and dependency access pattern.

## Step 6 — map verified chatbot identity

The mapper must use only cryptographically verified claims:

```python
from src.services.audio.models import SpeechCaller

def speech_caller_from_verified_user(user: ExistingVerifiedUser) -> SpeechCaller:
    return SpeechCaller(
        principal_id=user.<verified_subject_field>,
        client_id=user.<verified_client_or_application_field>,
    )
```

Replace bracketed fields only after inspecting the real identity model. Never
use browser-supplied user IDs, form values or unverified decoded claims.

## Step 7 — add the route and path-scoped body limit to `src/api.py`

At the existing app wiring location, make only these additive changes:

```python
from src.core.middleware.request_size import SpeechBodyLimitMiddleware
from src.routes.speech import create_speech_router

speech_router = create_speech_router(
    transcription_service=services.audio_transcription_service,
    authenticate=get_verified_current_user,
    caller_mapper=speech_caller_from_verified_user,
)

app.add_middleware(
    SpeechBodyLimitMiddleware,
    max_body_bytes=services.speech_settings.max_request_body_bytes,
    path="/api/v1/speech/transcriptions",
)
app.include_router(speech_router)
```

Use the real service-container symbol and verified auth dependency. Do not add
a second FastAPI app or run a second Uvicorn process.

## Step 8 — merge frontend wiring

Do **not** add a new frontend runtime file. Follow
`integration/FRONTEND-INLINE-MERGE.md`: merge the microphone markup into the
existing template, its rules into the existing stylesheet, and its workflow
into the existing controller that already owns the textbox, Send action, token
and `apiRequest()` helper.

Use `frontend-reference/index.html`, `frontend-reference/style.css` and
`frontend-reference/script.js` as the complete tested implementation reference.
Copy only the STT-related elements, rules, state, events and methods into their
matching office files; retain all unrelated office code.

Add one `type="button"` microphone button beside the existing textbox and one
`aria-live="polite"` status element. Register one click handler and release
tracks on page teardown.

Make the existing request helper accept an optional captured access token and
let the browser set the multipart boundary:

```javascript
async apiRequest(path, options = {}, accessToken = null) {
    const token = accessToken || this.tokensByUser[this.currentUserId];
    if (!token || token.startsWith("REPLACE_WITH_")) {
        throw new Error(`Missing token for ${this.currentUserId}`);
    }

    const headers = { Authorization: `Bearer ${token}`, ...(options.headers || {}) };
    if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";

    const response = await fetch(`${this.apiBaseUrl}${path}`, { ...options, headers });
    if (!response.ok) {
        let detail = `Request failed with status ${response.status}`;
        try {
            const problem = await response.json();
            detail = problem.message || problem.detail || detail;
        } catch (_error) {}
        throw new Error(detail);
    }

    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) return response.text();
    try {
        return await response.json();
    } catch (_error) {
        throw new Error("The API returned an invalid response.");
    }
}
```

Add only these controller responsibilities; reuse the real target symbol names:

1. Store only the active `MediaRecorder` and timeout on the controller. Keep
   stream, chunks and the token captured at recording start inside the recording
   closure.
2. On start, verify a chatbot token exists **before** requesting microphone
   permission, call `getUserMedia({audio: true})`, select the first supported
   type from WebM/Opus, WebM, Ogg/Opus and MP4, and start the 120-second timer.
3. On stop, stop the recorder, release every media track and show processing.
4. Build one `Blob`, reject empty or over-20-MiB audio locally, then submit:

```javascript
const formData = new FormData();
formData.append("audio", audioBlob, `microphone-${Date.now()}.${extension}`);
formData.append("locale", "en-IN");
const requestId = crypto.randomUUID();
const result = await this.apiRequest(
    "/api/v1/speech/transcriptions",
    {
        method: "POST",
        headers: { "X-Request-ID": requestId },
        body: formData
    },
    tokenCapturedAtRecordingStart
);
```

5. Append `result.transcript.trim()` to the textbox's current value so text
   typed while Azure was processing is preserved. Dispatch a bubbling `input`
   event and focus the textbox.
6. Never click Send and never call `/ews-chatbot/chat` from the speech flow.
7. In `finally`, clear the timeout, release tracks, clear recorder state and
   restore the accessible idle button state. Closure-local chunks and token are
   then naturally released.

The reviewed local reference implements this flow with four small controller
methods plus one cleanup helper and the FormData-aware request-helper change.
Do not introduce a
frontend class, factory, dependency-injection wrapper, duplicate fetch helper,
HTTP-status message table or speculative browser abstraction.

## Step 9 — required verification

- Existing chatbot tests still pass unchanged.
- Overlay Python unit, route and negative tests pass.
- The target frontend tests cover permission denial, start/stop cleanup,
  multipart headers, token capture, safe errors, typed-text preservation and
  insertion without auto-send.
- Ruff, strict mypy (or the repository's equivalent), Bandit and dependency
  scanning pass.
- Missing/invalid auth returns 401 before audio processing.
- Invalid type, corrupt audio, empty audio, oversize body and over-duration
  audio fail before Azure is called.
- Azure 400/401/403/408/413/429/5xx and timeout/transport failures map to the
  documented sanitized contract.
- Logs contain IDs, status, sizes and latency only—never audio, transcript,
  token, key, multipart body or raw provider response.
- A synthetic live test proves the deployed runtime can reach the allowlisted
  Azure endpoint.

## Completion evidence Copilot must return

Return a table of every changed file, why it changed, tests run and results.
Also report any unresolved auth, Redis, CORS, secret-manager, version or network
assumption. Do not claim production readiness while any of those are unresolved.
