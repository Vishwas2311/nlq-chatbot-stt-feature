import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";
import { File } from "node:buffer";
import { webcrypto } from "node:crypto";

class ClassList {
    constructor() {
        this.values = new Set();
    }

    add(...names) {
        names.forEach((name) => this.values.add(name));
    }

    remove(...names) {
        names.forEach((name) => this.values.delete(name));
    }

    contains(name) {
        return this.values.has(name);
    }

    toggle(name, force) {
        if (force === true) this.values.add(name);
        else if (force === false) this.values.delete(name);
        else if (this.values.has(name)) this.values.delete(name);
        else this.values.add(name);
    }
}

class FakeElement {
    constructor() {
        this.attributes = new Map();
        this.classList = new ClassList();
        this.disabled = false;
        this.events = [];
        this.icon = { className: "fas fa-microphone" };
        this.style = {};
        this.textContent = "";
        this.title = "";
        this.value = "";
        this.focused = false;
    }

    addEventListener(name, callback) {
        this.events.push({ name, callback });
    }

    dispatchEvent(event) {
        this.events.push({ name: event.type, event });
        return true;
    }

    focus() {
        this.focused = true;
    }

    querySelector(selector) {
        return selector === "i" ? this.icon : null;
    }

    setAttribute(name, value) {
        this.attributes.set(name, value);
    }

    getAttribute(name) {
        return this.attributes.get(name) ?? null;
    }
}

const scriptPath = new URL("../script.js", import.meta.url);
const source = await readFile(scriptPath, "utf8");
const context = vm.createContext({
    Blob,
    Event,
    File,
    FormData,
    URLSearchParams,
    console,
    crypto: webcrypto,
    document: {
        addEventListener() {},
        createElement() { return new FakeElement(); },
        getElementById() { return new FakeElement(); },
        querySelectorAll() { return []; }
    },
    fetch: async () => { throw new Error("fetch mock not configured"); },
    navigator: {},
    window: {
        addEventListener() {},
        clearTimeout() {},
        setTimeout() { return 1; }
    }
});
vm.runInContext(`${source}\nthis.__ChatbotApp = ChatbotApp;`, context);
const ChatbotApp = context.__ChatbotApp;

function makeApp() {
    const app = Object.create(ChatbotApp.prototype);
    app.apiBaseUrl = "http://127.0.0.1:8000";
    app.currentUserId = "user1";
    app.tokensByUser = { user1: "local-stt-demo-token" };
    app.mediaRecorder = null;
    app.recordingTimer = null;
    app.elements = {
        micBtn: new FakeElement(),
        voiceStatus: new FakeElement(),
        messageInput: new FakeElement()
    };
    return app;
}

function jsonResponse(status, payload, headers = {}) {
    return {
        ok: status >= 200 && status < 300,
        status,
        headers: new Headers({ "content-type": "application/json", ...headers }),
        async json() { return payload; }
    };
}

test("shows a safe message when microphone APIs are unavailable", async () => {
    context.navigator = {};
    context.MediaRecorder = undefined;
    const app = makeApp();
    await app.startVoiceInput();
    assert.match(app.elements.voiceStatus.textContent, /not supported/i);
    assert.ok(app.elements.voiceStatus.classList.contains("error"));
});

test("rejects recording before permission when the user token is missing", async () => {
    let permissionRequested = false;
    context.navigator = { mediaDevices: { async getUserMedia() { permissionRequested = true; } } };
    context.MediaRecorder = class {};
    const app = makeApp();
    app.tokensByUser.user1 = "REPLACE_WITH_USER1_BEARER_TOKEN";
    await app.startVoiceInput();
    assert.equal(permissionRequested, false);
    assert.match(app.elements.voiceStatus.textContent, /Missing token/);
});

test("handles microphone permission denial and restores controls", async () => {
    context.navigator = {
        mediaDevices: {
            async getUserMedia() {
                const error = new Error("denied");
                error.name = "NotAllowedError";
                throw error;
            }
        }
    };
    context.MediaRecorder = class {};
    const app = makeApp();
    await app.startVoiceInput();
    assert.match(app.elements.voiceStatus.textContent, /permission was denied/i);
    assert.equal(app.elements.micBtn.disabled, false);
    assert.equal(app.mediaRecorder, null);
});

test("starts recording with the correct accessible UI state", async () => {
    const tracks = [{ stopped: false, stop() { this.stopped = true; } }];
    context.navigator = { mediaDevices: { async getUserMedia() { return { getTracks: () => tracks }; } } };
    context.MediaRecorder = class {
        static isTypeSupported(type) { return type === "audio/webm;codecs=opus"; }
        constructor(stream, options) {
            this.stream = stream;
            this.mimeType = options.mimeType;
            this.state = "inactive";
            this.handlers = {};
        }
        addEventListener(name, callback) { this.handlers[name] = callback; }
        start() { this.state = "recording"; }
    };
    const app = makeApp();
    await app.startVoiceInput();
    assert.equal(app.mediaRecorder.state, "recording");
    assert.equal(app.mediaRecorder.mimeType, "audio/webm;codecs=opus");
    assert.ok(app.elements.micBtn.classList.contains("is-recording"));
    assert.equal(app.elements.micBtn.getAttribute("aria-pressed"), "true");
    assert.match(app.elements.voiceStatus.textContent, /Listening/);
});

test("stopping recording releases tracks and enters processing state", () => {
    const track = { stopped: false, stop() { this.stopped = true; } };
    const app = makeApp();
    app.mediaRecorder = {
        state: "recording",
        stream: { getTracks: () => [track] },
        stopCalled: false,
        stop() { this.stopCalled = true; }
    };
    app.stopVoiceInput();
    assert.equal(app.mediaRecorder.stopCalled, true);
    assert.equal(track.stopped, true);
    assert.equal(app.elements.micBtn.disabled, true);
    assert.ok(app.elements.micBtn.classList.contains("is-processing"));
});

test("sends multipart audio with auth and without manually setting Content-Type", async () => {
    let captured;
    context.fetch = async (url, options) => {
        captured = { url, options };
        return jsonResponse(200, { transcript: "synthetic transcript" });
    };
    const app = makeApp();
    const formData = new FormData();
    formData.append("audio", new File([new Uint8Array([1, 2, 3])], "test.webm", { type: "audio/webm" }));
    formData.append("locale", "en-IN");
    const result = await app.apiRequest(
        "/api/v1/speech/transcriptions",
        { method: "POST", body: formData },
        "recording-token"
    );
    assert.equal(result.transcript, "synthetic transcript");
    assert.equal(captured.url, "http://127.0.0.1:8000/api/v1/speech/transcriptions");
    assert.equal(captured.options.method, "POST");
    assert.equal(captured.options.headers.Authorization, "Bearer recording-token");
    assert.equal(captured.options.headers["Content-Type"], undefined);
    assert.ok(captured.options.body instanceof FormData);
    assert.equal(captured.options.body.get("locale"), "en-IN");
});

test("uses sanitized backend problem messages", async () => {
    context.fetch = async () => jsonResponse(415, { message: "Approved audio formats only." });
    const app = makeApp();
    await assert.rejects(() => app.apiRequest("/api/v1/speech/transcriptions"), /Approved audio formats only/);
});

test("rejects a missing session token before sending audio", async () => {
    let fetchCalled = false;
    context.fetch = async () => { fetchCalled = true; };
    const app = makeApp();
    app.tokensByUser.user1 = "REPLACE_WITH_USER1_BEARER_TOKEN";
    await assert.rejects(() => app.apiRequest("/api/v1/speech/transcriptions"), /Missing token/i);
    assert.equal(fetchCalled, false);
});

test("rejects malformed successful backend JSON with a safe message", async () => {
    context.fetch = async () => ({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        async json() { throw new SyntaxError("PRIVATE-PARSER-DIAGNOSTIC"); }
    });
    const app = makeApp();
    await assert.rejects(() => app.apiRequest("/api/v1/speech/transcriptions"), /invalid response/i);
});

test("falls back to a status-only error when an error body is not JSON", async () => {
    context.fetch = async () => ({
        ok: false,
        status: 504,
        headers: new Headers(),
        async json() { throw new SyntaxError("not json"); }
    });
    const app = makeApp();
    await assert.rejects(() => app.apiRequest("/api/v1/speech/transcriptions"), /status 504/i);
});

test("successful transcription fills the textbox but never auto-sends", async () => {
    const app = makeApp();
    let sendCalled = false;
    app.sendMessage = () => { sendCalled = true; };
    app.apiRequest = async () => ({ transcript: "please show account status" });
    const chunks = [new Blob([new Uint8Array([1, 2, 3])], { type: "audio/webm" })];
    await app.processRecordedAudio(chunks, "audio/webm", "token");
    assert.equal(app.elements.messageInput.value, "please show account status");
    assert.equal(app.elements.messageInput.focused, true);
    assert.equal(sendCalled, false);
    assert.match(app.elements.voiceStatus.textContent, /Review it, then send/);
});

test("does not overwrite text typed while transcription is processing", async () => {
    const app = makeApp();
    app.elements.messageInput.value = "original plus typed text";
    app.apiRequest = async () => ({ transcript: "voice transcript" });
    const chunks = [new Blob([new Uint8Array([1])], { type: "audio/webm" })];
    await app.processRecordedAudio(chunks, "audio/webm", "token");
    assert.equal(app.elements.messageInput.value, "original plus typed text voice transcript");
});

test("empty Azure transcript is rejected and controls recover", async () => {
    const app = makeApp();
    app.apiRequest = async () => ({ transcript: "   " });
    await app.processRecordedAudio([new Blob([new Uint8Array([1])])], "audio/webm", "token");
    assert.match(app.elements.voiceStatus.textContent, /empty transcript/i);
    assert.ok(app.elements.voiceStatus.classList.contains("error"));
    assert.equal(app.elements.micBtn.disabled, false);
});

test("zero-byte recording is rejected locally without calling backend", async () => {
    const app = makeApp();
    let backendCalled = false;
    app.apiRequest = async () => { backendCalled = true; };
    await app.processRecordedAudio([], "audio/webm", "token");
    assert.equal(backendCalled, false);
    assert.match(app.elements.voiceStatus.textContent, /No audio was recorded/);
});

test("recording over 20 MiB is rejected locally", async () => {
    const app = makeApp();
    let backendCalled = false;
    app.apiRequest = async () => { backendCalled = true; };
    await app.processRecordedAudio([new Blob([new Uint8Array(20 * 1024 * 1024 + 1)])], "audio/webm", "token");
    assert.equal(backendCalled, false);
    assert.match(app.elements.voiceStatus.textContent, /20 MiB limit/);
});

test("network failure is sanitized and controls recover", async () => {
    context.fetch = async () => { throw new TypeError("fetch failed"); };
    const app = makeApp();
    await app.processRecordedAudio([new Blob([new Uint8Array([1])])], "audio/webm", "token");
    assert.match(app.elements.voiceStatus.textContent, /Cannot reach the speech backend/);
    assert.doesNotMatch(app.elements.voiceStatus.textContent, /fetch failed/);
    assert.ok(app.elements.voiceStatus.classList.contains("error"));
    assert.equal(app.elements.micBtn.disabled, false);
});
