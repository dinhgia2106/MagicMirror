Module.register("MMM-LLMsAssistant", {
    defaults: {
        wakeWord: "Hey lens",
        picovoiceAccessKey: "",
        llmProvider: "gemini",
        llmApiKey: "",
        language: "vi-VN",
        voiceId: "vi-VN-NamMinhNeural",
        wakeTimeout: 10000,
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

        this.sendSocketNotification("INIT", this.config);
    },

    getDom: function () {
        const wrapper = document.createElement("div");
        wrapper.className = "llms-assistant";

        // Status indicator orb only
        const statusOrb = document.createElement("div");
        statusOrb.className = `assistant-orb ${this.state}`;
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

    socketNotificationReceived: function (notification, payload) {
        switch (notification) {
            case "WAKE_WORD_DETECTED":
                this.state = "activated";
                this.transcript = "";
                this.response = "";
                this.isConversationActive = true;
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
                this.state = "idle";
                this.isConversationActive = false;
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
