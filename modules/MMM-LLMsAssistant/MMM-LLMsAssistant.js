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
        this.state = "idle"; // idle, listening, processing, speaking
        this.transcript = "";
        this.response = "";

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
            case "listening": return "Listening...";
            case "processing": return "Thinking...";
            case "speaking": return "Speaking...";
            default: return "";
        }
    },

    socketNotificationReceived: function (notification, payload) {
        switch (notification) {
            case "WAKE_WORD_DETECTED":
                this.state = "listening";
                this.transcript = "";
                this.response = "";
                this.updateDom(300);
                break;

            case "SPEECH_RECOGNIZED":
                this.state = "processing";
                this.transcript = payload.text;
                this.updateDom(300);
                break;

            case "LLM_RESPONSE":
                this.state = "speaking";
                this.response = payload.text;
                this.updateDom(300);
                break;

            case "SPEECH_COMPLETE":
                this.state = "idle";
                this.updateDom(300);
                // Clear after delay
                setTimeout(() => {
                    this.transcript = "";
                    this.response = "";
                    this.updateDom(300);
                }, 5000);
                break;

            case "ERROR":
                Log.error("MMM-LLMsAssistant Error:", payload);
                this.state = "idle";
                this.updateDom(300);
                break;
        }
    }
});
