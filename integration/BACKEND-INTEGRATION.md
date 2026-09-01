# Backend integration into the existing chatbot

The backend implementation is complete under `chatbot-overlay/`. The remaining
work is target-specific wiring into the office repository. Do not create a new
FastAPI application or deployment.

## 1. Copy additive modules

Copy these paths while preserving every existing target file:

```text
chatbot-overlay/src/services/audio/              -> src/services/audio/
chatbot-overlay/src/routes/speech.py             -> src/routes/speech.py
chatbot-overlay/src/core/middleware/request_size.py
                                                  -> src/core/middleware/request_size.py
chatbot-overlay/tests/unit/services/audio/       -> matching target test area
chatbot-overlay/tests/integration/test_speech_route.py
                                                  -> matching target test area
```

Create missing package directories and `__init__.py` files. If an
`__init__.py` already exists, preserve it and merge only required exports.

## 2. Merge configuration

Map `integration/speech.env.example` into the existing `src/config.py` pattern.
`AZURE_SPEECH_KEY` must come from Fulkrum's approved runtime secret mechanism;
it must never be committed or returned to the browser.

## 3. Construct services in the existing lifecycle

In the same startup/lifespan location that creates Oracle, Redis, MCP and other
external clients, add:

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
```

Store these objects in the chatbot's existing service container. In its real
shutdown/finally path, add:

```python
await azure_speech_client.aclose()
```

Use the existing asynchronous Redis client; do not create a second pool.

## 4. Map only verified identity

Create the mapper beside the target authentication code, using only verified
claims:

```python
from src.services.audio.models import SpeechCaller

def speech_caller_from_verified_user(user: ExistingVerifiedUser) -> SpeechCaller:
    return SpeechCaller(
        principal_id=user.<verified_subject_field>,
        client_id=user.<verified_client_or_application_field>,
    )
```

Replace the bracketed fields only after inspecting the actual identity model.
Do not use browser user IDs or decoded-but-unverified JWT claims. The target
auth dependency must verify signature, algorithm, issuer, audience and expiry.

## 5. Wire the existing `src/api.py`

At the existing app-construction location, merge:

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

Replace `services`, `get_verified_current_user` and identity fields with the
real inspected target symbols. Do not overwrite `src/api.py` or change the
existing `/ews-chatbot/chat` route.

## 6. Verify the merge

- Existing chatbot tests pass before and after the change.
- The 39 supplied backend tests pass in the target dependency set.
- Missing/invalid auth fails before multipart parsing.
- Oversize, corrupt, unsupported and over-duration audio fail before Azure.
- Redis outage fails closed for new STT admission.
- Logs and responses contain no token, Azure key, audio, transcript or raw
  provider body.
- A synthetic request from Fulkrum reaches the expected Azure Speech resource.

