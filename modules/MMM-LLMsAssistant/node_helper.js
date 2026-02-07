const NodeHelper = require("node_helper");
const path = require("path");
const { spawn } = require("child_process");

module.exports = NodeHelper.create({
    config: null,
    porcupineProcess: null,
    isListening: false,
    initialized: false,

    start: function () {
        console.log("Starting node_helper for: " + this.name);
    },

    socketNotificationReceived: function (notification, payload) {
        if (notification === "INIT") {
            // Prevent multiple initializations
            if (this.initialized) {
                console.log("[MMM-LLMsAssistant] Already initialized, skipping duplicate INIT");
                return;
            }
            this.initialized = true;
            this.config = payload;
            this.startWakeWordDetection();
        }
    },

    startWakeWordDetection: function () {
        // Prevent multiple processes
        if (this.porcupineProcess) {
            console.log("[MMM-LLMsAssistant] Wake word detection already running, skipping");
            return;
        }

        const fs = require("fs");
        const pythonScript = path.join(__dirname, "wakeword_service.py");
        const ppnDir = path.join(__dirname, "Picovoice_ppn");

        // Auto-detect .ppn file
        let ppnPath = null;
        try {
            const files = fs.readdirSync(ppnDir);
            const ppnFile = files.find(f => f.endsWith(".ppn"));
            if (ppnFile) {
                ppnPath = path.join(ppnDir, ppnFile);
            }
        } catch (e) {
            console.error(`[MMM-LLMsAssistant] Error reading ppn directory: ${e}`);
        }

        if (!ppnPath) {
            console.error("[MMM-LLMsAssistant] No .ppn file found in Picovoice_ppn folder!");
            return;
        }

        console.log(`[MMM-LLMsAssistant] Starting wake word detection...`);
        console.log(`[MMM-LLMsAssistant] PPN path: ${ppnPath}`);

        this.porcupineProcess = spawn("python", [
            pythonScript,
            "--access-key", this.config.picovoiceAccessKey,
            "--ppn-path", ppnPath,
            "--llm-provider", this.config.llmProvider,
            "--llm-api-key", this.config.llmApiKey,
            "--voice-id", this.config.voiceId
        ]);

        this.porcupineProcess.stdout.on("data", (data) => {
            const lines = data.toString().trim().split("\n");
            lines.forEach(line => {
                try {
                    const event = JSON.parse(line);
                    this.handlePythonEvent(event);
                } catch (e) {
                    if (this.config.debug) {
                        console.log(`[MMM-LLMsAssistant] ${line}`);
                    }
                }
            });
        });

        this.porcupineProcess.stderr.on("data", (data) => {
            console.error(`[MMM-LLMsAssistant] Error: ${data}`);
        });

        this.porcupineProcess.on("close", (code) => {
            console.log(`[MMM-LLMsAssistant] Process exited with code ${code}`);
            // Reset process reference
            this.porcupineProcess = null;
            // Restart after delay if unexpected exit
            if (code !== 0) {
                setTimeout(() => this.startWakeWordDetection(), 5000);
            }
        });
    },

    handlePythonEvent: function (event) {
        switch (event.type) {
            case "wake_word":
                console.log("[MMM-LLMsAssistant] Wake word detected!");
                this.sendSocketNotification("WAKE_WORD_DETECTED", {});
                break;

            case "conversation_started":
                console.log("[MMM-LLMsAssistant] Conversation started");
                this.sendSocketNotification("CONVERSATION_STARTED", {});
                break;

            case "conversation_ended":
                console.log("[MMM-LLMsAssistant] Conversation ended");
                this.sendSocketNotification("CONVERSATION_ENDED", {});
                break;

            case "listening":
                console.log("[MMM-LLMsAssistant] Listening...");
                this.sendSocketNotification("LISTENING", {});
                break;

            case "speech":
                console.log(`[MMM-LLMsAssistant] Speech: ${event.text}`);
                this.sendSocketNotification("SPEECH_RECOGNIZED", { text: event.text });
                break;

            case "llm_response":
                console.log(`[MMM-LLMsAssistant] LLM: ${event.text}`);
                this.sendSocketNotification("LLM_RESPONSE", { text: event.text });
                break;

            case "speech_complete":
                console.log("[MMM-LLMsAssistant] Speech complete - conversation ended");
                this.sendSocketNotification("SPEECH_COMPLETE", {});
                break;

            case "response_complete":
                console.log("[MMM-LLMsAssistant] Response complete - ready for next input");
                this.sendSocketNotification("RESPONSE_COMPLETE", {});
                break;

            case "silence_timeout":
                console.log("[MMM-LLMsAssistant] Silence timeout - ending conversation");
                this.sendSocketNotification("SILENCE_TIMEOUT", {});
                break;

            case "noise_timeout":
                console.log("[MMM-LLMsAssistant] Noise timeout - ending conversation");
                this.sendSocketNotification("NOISE_TIMEOUT", {});
                break;

            case "reset_detected":
                console.log(`[MMM-LLMsAssistant] Reset detected: ${event.text}`);
                this.sendSocketNotification("RESET_DETECTED", { text: event.text });
                break;

            case "max_turns_reached":
                console.log("[MMM-LLMsAssistant] Max conversation turns reached");
                this.sendSocketNotification("MAX_TURNS_REACHED", {});
                break;

            case "debug":
                console.log(`[MMM-LLMsAssistant] DEBUG: ${event.message}`);
                break;

            case "error":
                console.error(`[MMM-LLMsAssistant] ${event.message}`);
                this.sendSocketNotification("ERROR", { message: event.message });
                break;
        }
    },

    stop: function () {
        if (this.porcupineProcess) {
            this.porcupineProcess.kill();
        }
    }
});
