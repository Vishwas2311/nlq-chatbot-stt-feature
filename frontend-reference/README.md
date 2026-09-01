# Complete frontend reference — review only

These files are the complete tested office-UI replica with Azure speech input
integrated:

- `index.html`: chatbot layout, microphone button and accessible status region.
- `style.css`: complete replica styles, including recording and processing states.
- `script.js`: complete chatbot controller with the STT workflow inline.
- `tests/stt-frontend.test.mjs`: microphone, multipart, cleanup, error and
  no-auto-send tests.

This directory is intentionally complete for review, but it is **not** copied
wholesale into the office repository and it does not create a frontend module.
The exact measured change and merge locations are documented in
`../integration/FRONTEND-INLINE-MERGE.md`. In production:

1. Add the `micBtn` and `voiceStatus` elements to the existing chatbot HTML.
2. Merge the microphone CSS rules into the existing stylesheet.
3. Merge the speech fields, events and methods from this `script.js` into the
   existing office controller and retain its existing chat/session behavior.
4. Reuse the office token source and `apiRequest()` helper. Never retain the
   local demonstration token block.
5. Keep transcript insertion without calling the Send handler.

Run the reference checks with:

```powershell
node --check script.js
node --test tests/stt-frontend.test.mjs
```
