# Azure STT chatbot merge handoff v0.6.0

This handoff merges Azure Speech-to-Text into the existing office FastAPI
chatbot as a cohesive internal capability. It is not a standalone microservice,
does not add a second deployment and contains no real credentials.

## Start here

1. Read `integration/GITHUB-COPILOT-MERGE-GUIDE.md` and
   `integration/FRONTEND-INLINE-MERGE.md`.
2. Read `HANDOFF-MANIFEST.md` and `integration/BACKEND-INTEGRATION.md`.
3. Review the complete tested UI in `frontend-reference/`.
4. Paste `COPILOT-MERGE-PROMPT.md` into GitHub Copilot on the office laptop.
5. Approve Copilot's analysis-only phase before allowing edits.
6. Merge the new files under `chatbot-overlay/`; never overwrite existing
   chatbot files wholesale.
7. Complete `integration/PRODUCTION-ACCEPTANCE-CHECKLIST.md` before production.

The known target repository uses `_web/`, `src/`, `mcp_server/`, `requirements/`
and `tests/`, with `src/api.py` as the existing FastAPI entry point. The overlay
is aligned to that evidence. Any deeper target symbol not proven by the office
repository must be discovered by Copilot and approved before wiring.

## Validated package boundary

- `chatbot-overlay/src/services/audio/`: Azure STT capability and controls.
- `chatbot-overlay/src/routes/speech.py`: thin authenticated route.
- `chatbot-overlay/src/core/middleware/request_size.py`: STT-only body limit.
- `chatbot-overlay/tests/`: backend unit and integration tests.
- `frontend-reference/`: complete HTML, CSS, inline-controller JavaScript and
  browser tests for review and exact behavior reference.
- `integration/`: exact merge guide, dependency/config deltas, error contract
  and production checklist.

There is intentionally no standalone production frontend artifact. Follow
`integration/FRONTEND-INLINE-MERGE.md` to add the measured 193 functional lines
directly to the chatbot's existing HTML, stylesheet and controller while
reusing its token and API-request paths.

Run `validate-chatbot-overlay.ps1` after installing the documented development
dependencies. It performs compilation, backend/frontend tests, Ruff, strict
mypy and Bandit without making a live Azure request.

The target team must additionally run a synthetic live request from the target
runtime and verify it in Azure Speech metrics.
