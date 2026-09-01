/**
 * EWS Chatbot Frontend
 * Multiuser, token-based session flow.
 */

class ChatbotApp {
    constructor() {
        this.apiBaseUrl = window.EWS_API_BASE_URL || "http://localhost:8000";
        this.sttOnlyMode = window.EWS_STT_ONLY_MODE === true;
        const localDemoToken = window.EWS_LOCAL_DEMO_TOKEN || "";
        this.tokensByUser = {
            demo_user: localDemoToken || "REPLACE_WITH_DEMO_USER_BEARER_TOKEN",
            user1: localDemoToken || "REPLACE_WITH_USER1_BEARER_TOKEN"
        };

        this.currentUserId = "user1";
        this.currentSessionId = null;
        this.userSessions = [];
        this.isLoading = false;

        // STT MERGE START: controller state
        this.mediaRecorder = null;
        this.recordingTimer = null;
        // STT MERGE END: controller state

        this.initializeElements();
        this.bindEvents();
        this.updateSessionTag();
        this.checkApiHealth();
        if (!this.sttOnlyMode) this.loadUserSessions();
    }

    initializeElements() {
        this.elements = {
            userSelect: document.getElementById("userSelect"),
            newChatBtn: document.getElementById("newChatBtn"),
            sessionList: document.getElementById("sessionList"),
            chatMessages: document.getElementById("chatMessages"),
            messageInput: document.getElementById("messageInput"),
            // STT MERGE START: DOM references
            micBtn: document.getElementById("micBtn"),
            voiceStatus: document.getElementById("voiceStatus"),
            // STT MERGE END: DOM references
            sendBtn: document.getElementById("sendBtn"),
            sessionTag: document.getElementById("sessionTag"),
            loadingIndicator: document.getElementById("loadingIndicator"),
            healthStatus: document.getElementById("healthStatus"),
            healthStatusText: document.getElementById("healthStatusText"),
            closeHealthStatus: document.getElementById("closeHealthStatus"),
            healthCheckBtn: document.getElementById("healthCheckBtn"),
            sqlModal: document.getElementById("sqlModal"),
            sqlQueryDisplay: document.getElementById("sqlQueryDisplay"),
            copySqlBtn: document.getElementById("copySqlBtn")
        };

        this.currentUserId = this.elements.userSelect?.value || this.currentUserId;
    }

    bindEvents() {
        this.elements.sendBtn.addEventListener("click", () => this.sendMessage());
        // STT MERGE: microphone event
        this.elements.micBtn.addEventListener("click", () => {
            if (this.mediaRecorder?.state === "recording") this.stopVoiceInput();
            else void this.startVoiceInput();
        });
        this.elements.messageInput.addEventListener("keydown", (e) => {
            if (e.ctrlKey && e.key === "Enter") {
                this.sendMessage();
            }
        });

        this.elements.newChatBtn.addEventListener("click", () => this.startNewSession());
        this.elements.userSelect.addEventListener("change", (e) => {
            this.currentUserId = e.target.value;
            this.currentSessionId = null;
            this.clearChat();
            this.updateSessionTag();
            if (!this.sttOnlyMode) this.loadUserSessions();
        });

        this.elements.closeHealthStatus.addEventListener("click", () => {
            this.elements.healthStatus.classList.add("is-hidden");
        });
        this.elements.healthCheckBtn.addEventListener("click", () => this.checkApiHealth());

        document.querySelectorAll(".modal-close, .modal-background").forEach((el) => {
            el.addEventListener("click", () => this.closeSqlModal());
        });
        this.elements.copySqlBtn.addEventListener("click", () => this.copySqlQuery());

        this.elements.messageInput.addEventListener("input", () => {
            this.elements.messageInput.style.height = "auto";
            this.elements.messageInput.style.height = `${Math.min(this.elements.messageInput.scrollHeight, 150)}px`;
        });

        // STT MERGE: release device access during page teardown
        window.addEventListener("beforeunload", () => {
            this.mediaRecorder?.stream.getTracks().forEach((track) => track.stop());
        });
    }

    // STT MERGE START: microphone workflow
    async startVoiceInput() {
        if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
            this.setVoiceState("idle", "Microphone recording is not supported in this browser.", true);
            return;
        }

        const token = this.tokensByUser[this.currentUserId];
        if (!token || token.startsWith("REPLACE_WITH_")) {
            this.setVoiceState("idle", `Missing token for ${this.currentUserId}.`, true);
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const chunks = [];
            const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]
                .find((type) => MediaRecorder.isTypeSupported(type));
            this.mediaRecorder = mimeType
                ? new MediaRecorder(stream, { mimeType })
                : new MediaRecorder(stream);

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data?.size) chunks.push(event.data);
            };
            this.mediaRecorder.onstop = () => this.processRecordedAudio(chunks, this.mediaRecorder?.mimeType, token);
            this.mediaRecorder.onerror = () => {
                this.mediaRecorder.onstop = null;
                this.setVoiceState("idle", "Recording failed. Please try again.", true);
                this.resetVoiceInput();
            };

            this.mediaRecorder.start(250);
            this.setVoiceState("recording", "Listening... click the microphone to stop.");
            this.recordingTimer = window.setTimeout(() => this.stopVoiceInput(), 120_000);
        } catch (error) {
            const message = error?.name === "NotAllowedError"
                ? "Microphone permission was denied."
                : "Unable to access the microphone.";
            this.setVoiceState("idle", message, true);
            this.resetVoiceInput();
        }
    }

    stopVoiceInput() {
        if (this.mediaRecorder?.state !== "recording") return;

        window.clearTimeout(this.recordingTimer);
        this.setVoiceState("processing", "Transcribing with Azure Speech...");
        this.mediaRecorder.stop();
        this.mediaRecorder.stream.getTracks().forEach((track) => track.stop());
    }

    async processRecordedAudio(chunks, mimeType = "audio/webm", token = null) {
        try {
            const audioBlob = new Blob(chunks, { type: mimeType });
            if (!audioBlob.size) throw new Error("No audio was recorded.");
            if (audioBlob.size > 20 * 1024 * 1024) throw new Error("Recording exceeds the 20 MiB limit.");

            const extension = mimeType.includes("ogg") ? "ogg" : mimeType.includes("mp4") ? "m4a" : "webm";
            const formData = new FormData();
            formData.append("audio", audioBlob, `microphone-${Date.now()}.${extension}`);
            formData.append("locale", "en-IN");
            const requestId = crypto.randomUUID();
            const result = await this.apiRequest("/api/v1/speech/transcriptions", {
                method: "POST",
                headers: { "X-Request-ID": requestId },
                body: formData
            }, token);
            const transcript = String(result.transcript || "").trim();
            if (!transcript) throw new Error("Azure Speech returned an empty transcript.");

            const currentInput = this.elements.messageInput.value;
            this.elements.messageInput.value = `${currentInput.trimEnd()} ${transcript}`.trim();
            this.elements.messageInput.dispatchEvent(new Event("input", { bubbles: true }));
            this.elements.messageInput.focus();
            this.setVoiceState("idle", "Transcript added. Review it, then send.");
        } catch (error) {
            const message = error?.name === "TypeError"
                ? "Cannot reach the speech backend. Check the connection and retry."
                : error.message || "Transcription failed.";
            this.setVoiceState("idle", message, true);
        } finally {
            this.resetVoiceInput();
        }
    }

    setVoiceState(state, message, isError = false) {
        const recording = state === "recording";
        const processing = state === "processing";
        this.elements.micBtn.disabled = processing;
        this.elements.micBtn.classList.toggle("is-recording", recording);
        this.elements.micBtn.classList.toggle("is-processing", processing);
        this.elements.micBtn.setAttribute("aria-pressed", String(recording));
        this.elements.micBtn.title = recording ? "Stop recording" : processing ? "Processing voice input" : "Start voice input";
        this.elements.micBtn.querySelector("i").className = recording
            ? "fas fa-stop"
            : processing ? "fas fa-spinner fa-spin" : "fas fa-microphone";
        if (message) {
            this.elements.voiceStatus.textContent = message;
            this.elements.voiceStatus.classList.toggle("error", isError);
        }
    }

    resetVoiceInput() {
        window.clearTimeout(this.recordingTimer);
        this.recordingTimer = null;
        this.mediaRecorder?.stream.getTracks().forEach((track) => track.stop());
        this.mediaRecorder = null;
        this.setVoiceState("idle");
    }
    // STT MERGE END: microphone workflow

    async apiRequest(path, options = {}, accessToken = null) {
        const token = accessToken || this.tokensByUser[this.currentUserId];
        if (!token || token.startsWith("REPLACE_WITH_")) {
            throw new Error(`Missing token for ${this.currentUserId}`);
        }

        // STT MERGE: FormData must keep the browser-generated multipart boundary.
        const headers = { Authorization: `Bearer ${token}`, ...(options.headers || {}) };
        if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";

        const response = await fetch(`${this.apiBaseUrl}${path}`, {
            ...options,
            headers
        });

        if (!response.ok) {
            let detail = `Request failed with status ${response.status}`;
            try {
                const errorBody = await response.json();
                detail = errorBody.detail || errorBody.message || detail;
            } catch (_error) {
                // Keep the status-based error when the response is not JSON.
            }
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

    async loadUserSessions() {
        try {
            const data = await this.apiRequest("/ews-chatbot/get_all_sessions");
            const sessions = Array.isArray(data) ? data : (data.sessions || []);
            this.userSessions = sessions.filter((session) => {
                const sessionUser = session.user_id || session.userId;
                return !sessionUser || sessionUser === this.currentUserId;
            });
            this.renderSessionList();
        } catch (error) {
            this.userSessions = [];
            this.renderSessionList();
            this.showHealthStatus(error.message, "is-warning");
        }
    }

    renderSessionList() {
        if (!this.userSessions.length) {
            this.elements.sessionList.innerHTML = '<div class="sessions-empty">No sessions yet</div>';
            return;
        }

        this.elements.sessionList.innerHTML = this.userSessions.map((session) => {
            const sessionId = session.session_id || session.sessionId || session.id;
            const title = session.title || session.first_message || `Session ${String(sessionId).substring(0, 8)}`;
            const dateValue = session.updated_at || session.created_at || session.timestamp;
            const activeClass = sessionId === this.currentSessionId ? " active" : "";
            return `
                <button class="session-item${activeClass}" data-session-id="${this.escapeHtml(String(sessionId))}">
                    <span class="session-title">${this.escapeHtml(title)}</span>
                    <span class="session-time">${dateValue ? this.formatTimestamp(new Date(dateValue)) : ""}</span>
                </button>
            `;
        }).join("");

        this.elements.sessionList.querySelectorAll(".session-item").forEach((item) => {
            item.addEventListener("click", () => this.loadSession(item.dataset.sessionId));
        });
    }

    startNewSession() {
        this.currentSessionId = null;
        this.clearChat();
        this.updateSessionTag();
        this.renderSessionList();
        this.elements.messageInput.focus();
    }

    async loadSession(sessionId) {
        if (!sessionId || this.isLoading) return;

        this.setLoading(true);
        try {
            const data = await this.apiRequest(`/ews-chatbot/load_session/${encodeURIComponent(sessionId)}`);
            this.currentSessionId = sessionId;
            this.clearChat(false);

            const messages = Array.isArray(data) ? data : (data.messages || data.history || []);
            messages.forEach((message) => {
                const role = message.role || message.sender || "assistant";
                const content = message.content || message.message || message.text || "";
                this.addMessage(role, content, {
                    sqlQuery: message.sql_query || message.sqlQuery,
                    results: message.results || message.data,
                    timestamp: message.timestamp || message.created_at
                });
            });

            this.updateSessionTag();
            this.renderSessionList();
            this.scrollToBottom();
        } catch (error) {
            this.showHealthStatus(`Failed to load session: ${error.message}`, "is-danger");
        } finally {
            this.setLoading(false);
        }
    }

    clearChat(showPlaceholder = true) {
        this.elements.chatMessages.innerHTML = showPlaceholder ? `
            <div class="message-placeholder has-text-centered py-6">
                <i class="fas fa-comment-dots fa-3x has-text-grey-light mb-4"></i>
                <p class="has-text-grey">Start a conversation by typing a message below</p>
            </div>
        ` : "";
    }

    async sendMessage() {
        const message = this.elements.messageInput.value.trim();
        if (!message || this.isLoading) return;

        this.removePlaceholder();
        this.addMessage("user", message);
        this.elements.messageInput.value = "";
        this.elements.messageInput.style.height = "auto";
        this.setLoading(true);

        try {
            const payload = {
                message,
                session_id: this.currentSessionId,
                user_id: this.currentUserId
            };
            const data = await this.apiRequest("/ews-chatbot/chat", {
                method: "POST",
                body: JSON.stringify(payload)
            });

            this.currentSessionId = data.session_id || data.sessionId || this.currentSessionId;
            const assistantText = data.response || data.answer || data.message || data.content || "No response returned.";
            this.addMessage("assistant", assistantText, {
                sqlQuery: data.sql_query || data.sqlQuery,
                results: data.results || data.data
            });
            this.updateSessionTag();
            await this.loadUserSessions();
        } catch (error) {
            this.addMessage("assistant", `Unable to process the request: ${error.message}`);
            this.showHealthStatus(error.message, "is-danger");
        } finally {
            this.setLoading(false);
            this.elements.messageInput.focus();
            this.scrollToBottom();
        }
    }

    addMessage(role, content, metadata = {}) {
        this.removePlaceholder();

        const messageElement = document.createElement("article");
        const normalizedRole = role === "user" ? "user" : "assistant";
        messageElement.className = `message ${normalizedRole}`;

        const displayRole = normalizedRole === "user" ? "You" : "Assistant";
        const timestamp = metadata.timestamp ? new Date(metadata.timestamp) : new Date();
        messageElement.innerHTML = `
            <div class="message-header-row">
                <span class="message-role">${displayRole}</span>
                <span class="message-time">${this.formatTimestamp(timestamp)}</span>
            </div>
            <div class="message-content">${this.formatMessageContent(content)}</div>
        `;

        if (metadata.sqlQuery) {
            const sqlButton = document.createElement("button");
            sqlButton.className = "sql-button";
            sqlButton.innerHTML = '<i class="fas fa-code mr-1"></i> View SQL';
            sqlButton.addEventListener("click", () => this.showSqlModal(metadata.sqlQuery));
            messageElement.appendChild(sqlButton);
        }

        const resultTable = this.createResultTable(metadata.results);
        if (resultTable) messageElement.appendChild(resultTable);

        this.elements.chatMessages.appendChild(messageElement);
        this.scrollToBottom();
    }

    formatMessageContent(content) {
        if (content === null || content === undefined) return "";
        const escaped = this.escapeHtml(String(content));
        return escaped.replace(/\n/g, "<br>");
    }

    createResultTable(results) {
        if (!Array.isArray(results) || !results.length || typeof results[0] !== "object") {
            return null;
        }

        const columns = Object.keys(results[0]);
        const wrapper = document.createElement("div");
        wrapper.className = "table-container";
        wrapper.innerHTML = `
            <table class="result-table">
                <thead><tr>${columns.map((column) => `<th>${this.escapeHtml(column)}</th>`).join("")}</tr></thead>
                <tbody>
                    ${results.map((row) => `
                        <tr>${columns.map((column) => `<td>${this.escapeHtml(String(row[column] ?? ""))}</td>`).join("")}</tr>
                    `).join("")}
                </tbody>
            </table>
        `;
        return wrapper;
    }

    async checkApiHealth() {
        const healthIndicator = this.elements.healthCheckBtn.querySelector(".health-indicator");
        try {
            const response = await fetch(`${this.apiBaseUrl}/health`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            if (data.status === "healthy" || data.status === "ok") {
                this.showHealthStatus("API is healthy", "is-success");
                healthIndicator.classList.remove("offline");
            } else {
                this.showHealthStatus(`API status: ${data.status}`, "is-warning");
                healthIndicator.classList.add("offline");
            }
        } catch (_error) {
            this.showHealthStatus("API connection failed", "is-danger");
            healthIndicator.classList.add("offline");
        }
    }

    showHealthStatus(message, className) {
        let statusClass = "";
        if (className === "is-success") {
            statusClass = "success";
        } else if (className === "is-danger") {
            statusClass = "error";
        } else if (className === "is-warning") {
            statusClass = "warning";
        }

        this.elements.healthStatus.className = `health-toast ${statusClass}`;
        this.elements.healthStatusText.textContent = message;
        this.elements.healthStatus.classList.remove("is-hidden");

        setTimeout(() => {
            this.elements.healthStatus.classList.add("is-hidden");
        }, 3000);
    }

    showSqlModal(sqlQuery) {
        this.elements.sqlQueryDisplay.innerText = sqlQuery;
        this.elements.sqlModal.classList.add("is-active");
    }

    closeSqlModal() {
        this.elements.sqlModal.classList.remove("is-active");
    }

    async copySqlQuery() {
        const sqlText = this.elements.sqlQueryDisplay.innerText;
        try {
            await navigator.clipboard.writeText(sqlText);
            this.showHealthStatus("SQL query copied to clipboard", "is-success");
        } catch (_error) {
            this.showHealthStatus("Failed to copy SQL query", "is-warning");
        }
    }

    setLoading(loading) {
        this.isLoading = loading;
        this.elements.sendBtn.disabled = loading;
        this.elements.messageInput.disabled = loading;

        if (loading) {
            this.elements.loadingIndicator.classList.remove("is-hidden");
            this.removePlaceholder();
        } else {
            this.elements.loadingIndicator.classList.add("is-hidden");
        }
    }

    updateSessionTag() {
        if (this.currentSessionId) {
            this.elements.sessionTag.textContent = `${this.currentSessionId.substring(0, 8)}...`;
            this.elements.sessionTag.className = "session-tag active";
        } else {
            this.elements.sessionTag.textContent = "New Chat";
            this.elements.sessionTag.className = "session-tag";
        }
    }

    removePlaceholder() {
        const placeholder = this.elements.chatMessages.querySelector(".message-placeholder");
        if (placeholder) {
            placeholder.remove();
        }
    }

    scrollToBottom() {
        setTimeout(() => {
            this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
        }, 100);
    }

    formatTimestamp(date) {
        return date.toLocaleTimeString("en-US", {
            hour: "2-digit",
            minute: "2-digit"
        });
    }

    escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    new ChatbotApp();
});
