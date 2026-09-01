# Chatbot-native Azure STT overlay

This directory is an additive overlay for the existing `main chatbot backend`
repository. It is not a second deployable service and it must not be copied over
the repository root with overwrite enabled.

The target deployment remains one FastAPI chatbot application. The existing
`src/api.py` stays the application entry point and the existing chat, Oracle,
Redis, MCP, session and LLM behavior stays unchanged.

New capability files:

- `src/services/audio/`: transient STT application service, Azure adapter,
  validation, parsing, limits and safe errors.
- `src/routes/speech.py`: one thin authenticated HTTP route.
- `src/core/middleware/request_size.py`: body limit scoped only to the STT path.
- `tests/`: backend unit, integration and security-oriented regression tests.

No production frontend file is supplied in this overlay. Follow
`../integration/FRONTEND-INLINE-MERGE.md` so the existing HTML, stylesheet and
controller remain the single owners of markup, styling, textbox, token,
request and teardown behavior.

The complete reviewed HTML/CSS/JavaScript implementation and its browser tests
are available under `../frontend-reference/`. They are integration reference
files, not an additional production frontend bundle.

Read `../integration/GITHUB-COPILOT-MERGE-GUIDE.md` before changing the target
repository. Empty `__init__.py` files in this overlay are creation hints; if the
target file already exists, preserve its content.
