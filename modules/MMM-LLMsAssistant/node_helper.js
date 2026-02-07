const NodeHelper = require("node_helper");
const path = require("path");
const { spawn } = require("child_process");

module.exports = NodeHelper.create({
    config: null,
    porcupineProcess: null,
    isListening: false,

    start: function () {
        console.log("Starting node_helper for: " + this.name);
    },

    socketNotificationReceived: function (notification, payload) {
        if (notification === "INIT") {
            this.config = payload;
            this.startWakeWordDetection();
        }
    },

    startWakeWordDetection: function () {
        const pythonScript = path.join(__dirname, "wakeword_service.py");
        const ppnPath = path.join(__dirname, "Picovoice_ppn", "Hey-lens_en_raspberry-pi_v4_0_0.ppn");

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

            case "speech":
                console.log(`[MMM-LLMsAssistant] Speech: ${event.text}`);
                this.sendSocketNotification("SPEECH_RECOGNIZED", { text: event.text });
                break;

            case "llm_response":
                console.log(`[MMM-LLMsAssistant] LLM: ${event.text}`);
                this.sendSocketNotification("LLM_RESPONSE", { text: event.text });
                break;

            case "speech_complete":
                this.sendSocketNotification("SPEECH_COMPLETE", {});
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
