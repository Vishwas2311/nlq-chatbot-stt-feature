# Handoff manifest

This package contains everything needed to review and merge Azure Speech input
into the existing NLQ chatbot. It does not create another application or
deployment.

## Production merge inputs

| Path | Use |
| --- | --- |
| `chatbot-overlay/src/services/audio/` | Azure client, validation, multipart handling, limits and service workflow. |
| `chatbot-overlay/src/routes/speech.py` | Authenticated chatbot STT route. |
| `chatbot-overlay/src/core/middleware/request_size.py` | Request-size limit scoped to the STT endpoint. |
| `chatbot-overlay/tests/` | Backend tests to adapt to the target test layout. |
| `integration/BACKEND-INTEGRATION.md` | Exact backend insertion points and wiring rules. |
| `integration/FRONTEND-INLINE-MERGE.md` | Exact no-new-file frontend merge boundary and measured line count. |
| `integration/GITHUB-COPILOT-MERGE-GUIDE.md` | End-to-end guarded merge procedure. |
| `COPILOT-MERGE-PROMPT.md` | Prompt for analysis-first integration on the office laptop. |

## Complete frontend reference

`frontend-reference/` contains a complete HTML/CSS/JavaScript chatbot replica
with the microphone workflow already integrated and tested. It exists so the
team can review the full working implementation.

Do not replace the real office frontend with this replica. Merge the microphone
HTML, CSS and the marked controller logic into the office files. The target
must still have one main JavaScript controller; it must not load a second STT
runtime module.

No production frontend artifact exists under `chatbot-overlay/`. The target
team edits its existing HTML, CSS and JavaScript files in place.

## Deliberately excluded

- Azure keys, real JWTs and company endpoints.
- A second FastAPI app, Uvicorn process, container or Azure deployment.
- Standalone `speech-input.js` or `speech-input.css` runtime files.
- Local demo-server code.
