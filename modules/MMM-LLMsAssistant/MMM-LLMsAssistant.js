Module.register("MMM-LLMsAssistant", {
    defaults: {
        wakeWord: "Hey lens",
        picovoiceAccessKey: "",
        llmProvider: "gemini",
        llmApiKey: "",
        language: "vi-VN",
        voiceId: "vi-VN-NamMinhNeural",
        wakeTimeout: 10000,
        audioDeviceIndex: -1,
        debug: false
    },

    getStyles: function () {
        return ["MMM-LLMsAssistant.css"];
    },

    start: function () {
        Log.info("Starting module: " + this.name);
        this.state = "idle"; // idle, activated, listening, waiting-llm, toolcall, speaking
        this.transcript = "";
        this.response = "";
        this.isConversationActive = false;
        this.audioContext = null;

        this.sendSocketNotification("INIT", this.config);
    },

    /**
     * Play a pleasant notification chime using Web Audio API
     * when wake word is detected or user clicks the orb.
     */
    playActivationSound: function () {
        try {
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            const ctx = this.audioContext;
            const now = ctx.currentTime;

            // Two-tone chime: C5 then E5
            const frequencies = [523.25, 659.25];
            const duration = 0.12;

            frequencies.forEach((freq, i) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "sine";
                osc.frequency.setValueAtTime(freq, now);
                gain.gain.setValueAtTime(0, now + i * duration);
                gain.gain.linearRampToValueAtTime(1, now + i * duration + 0.02);
                gain.gain.exponentialRampToValueAtTime(0.001, now + i * duration + duration);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + i * duration);
                osc.stop(now + i * duration + duration);
            });
        } catch (e) {
            Log.warn("MMM-LLMsAssistant: Could not play activation sound", e);
        }
    },

    getDom: function () {
        const wrapper = document.createElement("div");
        wrapper.className = "llms-assistant";

        // Status indicator orb - clickable to activate AI
        const statusOrb = document.createElement("div");
        statusOrb.className = `assistant-orb ${this.state}`;
        statusOrb.title = this.state === "idle" ? "Click to activate assistant" : this.getStatusText();

        // Click handler - only activate when idle
        if (this.state === "idle") {
            statusOrb.style.cursor = "pointer";
            statusOrb.addEventListener("click", () => {
                this.playActivationSound();
                this.state = "activated";
                this.transcript = "";
                this.response = "";
                this.isConversationActive = true;
                this.updateDom(300);
                this.sendSocketNotification("MANUAL_ACTIVATE", {});
            });
        }

        wrapper.appendChild(statusOrb);

        return wrapper;
    },

    getStatusText: function () {
        switch (this.state) {
            case "idle": return `Say "${this.config.wakeWord}"`;
            case "activated": return "Ready...";
            case "listening": return "Listening...";
            case "waiting-llm": return "Thinking...";
            case "toolcall": return "Working...";
            case "speaking": return "Speaking...";
            default: return "";
        }
    },

    notificationReceived: function (notification, payload, sender) {
        // Listen for track changes from MMM-SoundCloud
        if (notification === "MUSIC_TRACK_CHANGED" && payload) {
            this.sendSocketNotification("SAVE_CURRENT_TRACK", payload);
        }
    },

    socketNotificationReceived: function (notification, payload) {
        switch (notification) {
            case "WAKE_WORD_DETECTED":
                this.state = "activated";
                this.transcript = "";
                this.response = "";
                this.isConversationActive = true;
                this.playActivationSound();
                this.updateDom(300);
                break;

            case "CONVERSATION_STARTED":
                this.state = "activated";
                this.isConversationActive = true;
                this.updateDom(300);
                break;

            case "LISTENING":
                this.state = "activated";
                this.updateDom(300);
                break;

            case "LISTENING_ACTIVE":
                this.state = "listening";
                this.updateDom(300);
                break;

            case "SPEECH_RECOGNIZED":
                this.state = "waiting-llm";
                this.transcript = payload.text;
                this.updateDom(300);
                break;

            case "TOOL_CALL":
                this.state = "toolcall";
                this.updateDom(300);
                break;

            case "LLM_RESPONSE":
                this.state = "speaking";
                this.response = payload.text;
                this.updateDom(300);
                break;

            case "RESPONSE_COMPLETE":
                // AI finished speaking, ready for next input
                this.state = "activated";
                this.updateDom(300);
                break;

            case "SPEECH_COMPLETE":
                // If conversation is still active, go back to activated
                if (this.isConversationActive) {
                    this.state = "activated";
                } else {
                    this.state = "idle";
                    // Clear after delay
                    setTimeout(() => {
                        this.transcript = "";
                        this.response = "";
                        this.updateDom(300);
                    }, 3000);
                }
                this.updateDom(300);
                break;

            case "CONVERSATION_ENDED":
            case "SILENCE_TIMEOUT":
            case "NOISE_TIMEOUT":
            case "RESET_DETECTED":
            case "MAX_TURNS_REACHED":
                this.isConversationActive = false;
                this.state = "idle";
                this.updateDom(300);
                // Clear after delay
                setTimeout(() => {
                    this.transcript = "";
                    this.response = "";
                    this.updateDom(300);
                }, 3000);
                break;

            case "ERROR":
                Log.error("MMM-LLMsAssistant Error:", payload);
                // If conversation is active, fallback to blue (activated) instead of gray (idle)
                if (this.isConversationActive) {
                    this.state = "activated";
                } else {
                    this.state = "idle";
                    this.isConversationActive = false;
                }
                this.updateDom(300);
                break;

            // Music control notifications - forward to MMM-SoundCloud
            case "MUSIC_LOWER_VOLUME":
                this.sendNotification("MUSIC_LOWER_VOLUME", {});
                break;

            case "MUSIC_RESTORE_VOLUME":
                this.sendNotification("MUSIC_RESTORE_VOLUME", {});
                break;

            case "MUSIC_PLAY":
            case "MUSIC_PAUSE":
            case "MUSIC_NEXT":
            case "MUSIC_PREV":
            case "MUSIC_SET_VOLUME":
            case "MUSIC_ADJUST_VOLUME":
            case "MUSIC_TOGGLE":
            case "MUSIC_SEARCH_PLAY":
            case "MUSIC_PLAY_MOOD":
                Log.info("MMM-LLMsAssistant: Forwarding " + notification + " with payload: " + JSON.stringify(payload));
                this.sendNotification(notification, payload);
                break;
        }
    }
});
