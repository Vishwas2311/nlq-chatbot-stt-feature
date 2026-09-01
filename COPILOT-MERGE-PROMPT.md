# Prompt to paste into GitHub Copilot on the office laptop

```text
You are integrating the reviewed Azure STT handoff into this existing FastAPI
chatbot repository. First read HANDOFF-MANIFEST.md,
integration/BACKEND-INTEGRATION.md,
integration/GITHUB-COPILOT-MERGE-GUIDE.md,
integration/FRONTEND-INLINE-MERGE.md, chatbot-overlay/README.md,
frontend-reference/README.md and the complete repository. Treat the office
repository as the source of truth and the handoff as additive candidate code.

Phase A — analysis only, no edits:
1. Report the exact FastAPI app construction, lifespan/startup/shutdown,
   verified auth dependency and identity model, async Redis client/lifecycle,
   configuration pattern, dependency files, frontend entry/template/controller,
   textbox/send-button symbols, bearer-token source and existing tests.
2. Compare installed FastAPI/Starlette/Pydantic/httpx/redis/Python versions with
   integration/requirements-api.delta.txt.
3. Produce an exact file-by-file merge plan. Clearly label anything not proven.
4. Stop if JWT signature/issuer/audience/expiry verification, async Redis, or a
   safe frontend bearer-token source cannot be proven. Ask for a decision; do
   not invent them.

After a human approves Phase A, implement Phase B:
1. Copy/merge only the new files listed in the guide. Never overwrite existing
   src/api.py, src/config.py, src/services/__init__.py, requirements/api.txt,
   existing __init__.py files or existing frontend files wholesale.
2. Keep one FastAPI application, one process and one deployment. Do not create
   a standalone STT microservice or a second Uvicorn entry point.
3. Inject the existing verified auth dependency and map only verified claims to
   SpeechCaller. Reuse the existing async Redis client. Construct and close one
   AzureSpeechClient through the chatbot's real lifecycle.
4. Add the path-scoped request limit and speech router without modifying
   /ews-chatbot/chat or Oracle, session, MCP, NL2SQL, LLM and history behavior.
5. Merge the microphone workflow directly into the real UI controller. Reuse
   its existing API request/token helper, make that helper FormData-aware, and
   do not create or load any separate speech frontend file. Merge markup into
   the existing HTML/template, rules into the existing stylesheet and logic
   into the existing controller, following
   integration/FRONTEND-INLINE-MERGE.md. Populate the existing textbox and
   dispatch input, but never auto-send. Never expose Azure keys in browser code.
   Use `frontend-reference/` as the complete tested behavior reference, not as
   a wholesale replacement for office files.
6. Preserve transient processing: do not persist or log audio/transcripts and
   never log tokens, keys, multipart bodies or raw Azure responses.
7. Add/merge tests and run all existing plus new tests, lint, typing, security
   and dependency scans. Do not weaken tests to make the merge pass.

At completion, return: changed-file table, concise diffs, commands/results,
security checks, and unresolved items. Never insert real secrets or claim
production readiness if auth, Redis, CORS, secret management, networking,
version compatibility or tests remain unresolved.
```
