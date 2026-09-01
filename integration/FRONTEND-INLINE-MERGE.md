# Frontend inline merge — no new production frontend file

The office chatbot keeps its existing HTML, stylesheet and controller. Do not
copy a new JavaScript or CSS module into `_web/`. The files under
`frontend-reference/` are the tested source of truth for the small edits below.

## Measured change size

The reviewed reference implementation contains **193 nonblank functional
lines** of frontend change:

| Existing office file | Functional lines | Change |
|---|---:|---|
| Existing HTML/template | 9 | Add `micBtn` beside Send and `voiceStatus` below the textbox. |
| Existing stylesheet | 68 | Merge the marked microphone, focus, recording, processing and status rules. |
| Existing controller JavaScript | 116 | Add recording/upload lifecycle and make the existing request helper FormData-aware. |
| **Total** | **193** | No new production frontend file or framework. |

These are readable source lines, excluding blank lines and merge-marker
comments. The number may shift slightly when the office symbol names or
formatting differ. The behavior must not be compressed or minified merely to
reduce a line counter.

The JavaScript is 116 lines—not the former 300-plus-line adapter—because it
reuses the existing controller, token store, request helper and textbox. It
still retains browser support checks, permission errors, a 120-second stop,
20-MiB local validation, media-track cleanup, captured-user authentication,
safe API errors, accessible UI state and insertion without auto-send.

## Exact merge locations

1. In `frontend-reference/index.html`, merge only the content between the
   `STT MERGE` comments into the existing chat-input markup. Never copy the
   local demo token block.
2. In `frontend-reference/style.css`, merge the block between
   `STT MERGE START: microphone control` and its matching end marker into the
   current office stylesheet. Extend the existing Send-button selectors rather
   than duplicating their shared size/layout declarations.
3. In `frontend-reference/script.js`, merge the marked controller state, DOM
   references, click event, teardown and microphone workflow into the existing
   `ChatbotApp` controller.
4. Modify the existing `apiRequest()` in place:
   - accept `accessToken = null` as its third argument;
   - prefer that captured token over the current user's token;
   - preserve caller-provided headers;
   - set `Content-Type: application/json` only when the body is not `FormData`.
5. Keep the current chat Send handler unchanged. Speech fills the textbox,
   dispatches `input`, focuses the field and does **not** send the message.

## Do not add

- `_web/js/speech-input.js`
- `_web/css/speech-input.css`
- a second fetch wrapper, frontend class, state manager or dependency
- an Azure key, endpoint secret or hard-coded production bearer token

Run the existing frontend suite plus the tests in
`frontend-reference/tests/stt-frontend.test.mjs` after merging.
