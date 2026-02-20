const NodeHelper = require("node_helper");
const path = require("path");
const { spawn, execSync } = require("child_process");

// Set Windows console to UTF-8 for Vietnamese support
if (process.platform === "win32") {
    try {
        execSync("chcp 65001", { stdio: "ignore" });
    } catch (e) {
        // Ignore errors
    }
}

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
        } else if (notification === "MANUAL_ACTIVATE") {
            // User clicked the orb to manually activate AI
            if (this.porcupineProcess && this.porcupineProcess.stdin) {
                try {
                    this.porcupineProcess.stdin.write("ACTIVATE\n");
                    console.log("[MMM-LLMsAssistant] Manual activation sent to Python process");
                } catch (e) {
                    console.error("[MMM-LLMsAssistant] Failed to send manual activation:", e);
                }
            }
        } else if (notification === "SAVE_CURRENT_TRACK") {
            // Save current track info to JSON file for Python to read
            const fs = require("fs");
            const trackFile = path.join(__dirname, "current_track.json");
            try {
                const trackData = {
                    title: payload.title || "",
                    artist: payload.artist || "",
                    artwork: payload.artwork || "",
                    timestamp: Date.now()
                };
                fs.writeFileSync(trackFile, JSON.stringify(trackData, null, 2), "utf8");
            } catch (e) {
                console.error("[MMM-LLMsAssistant] Failed to save current track:", e);
            }
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

        // Auto-detect .ppn file based on platform
        let ppnPath = null;
        try {
            const files = fs.readdirSync(ppnDir);
            const ppnFiles = files.filter(f => f.endsWith(".ppn"));

            if (ppnFiles.length > 0) {
                // Determine platform keyword to look for
                let platformKeyword;
                if (process.platform === "win32") {
                    platformKeyword = "windows";
                } else if (process.platform === "linux") {
                    // Raspberry Pi and other Linux ARM devices
                    platformKeyword = "raspberry-pi";
                } else if (process.platform === "darwin") {
                    platformKeyword = "mac";
                } else {
                    platformKeyword = "linux";
                }

                // Try to find platform-specific .ppn file
                let ppnFile = ppnFiles.find(f => f.toLowerCase().includes(platformKeyword));

                // If not found, try generic linux for non-windows platforms
                if (!ppnFile && process.platform !== "win32") {
                    ppnFile = ppnFiles.find(f => f.toLowerCase().includes("linux"));
                }

                // Fallback to first available .ppn file
                if (!ppnFile) {
                    ppnFile = ppnFiles[0];
                    console.warn(`[MMM-LLMsAssistant] No platform-specific .ppn file found for ${process.platform}. Using: ${ppnFile}`);
                    console.warn(`[MMM-LLMsAssistant] Expected file containing: "${platformKeyword}". Available: ${ppnFiles.join(", ")}`);
                } else {
                    console.log(`[MMM-LLMsAssistant] Using platform-specific .ppn file: ${ppnFile}`);
                }

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

        // Build command with chcp for UTF-8 support on Windows
        const command = process.platform === "win32"
            ? `chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && python "${pythonScript}" --access-key "${this.config.picovoiceAccessKey}" --ppn-path "${ppnPath}" --llm-provider ${this.config.llmProvider} --llm-api-key "${this.config.llmApiKey}" --voice-id ${this.config.voiceId}`
            : `python "${pythonScript}" --access-key "${this.config.picovoiceAccessKey}" --ppn-path "${ppnPath}" --llm-provider ${this.config.llmProvider} --llm-api-key "${this.config.llmApiKey}" --voice-id ${this.config.voiceId}`;

        this.porcupineProcess = spawn(command, [], {
            shell: true,
            env: {
                ...process.env,
                PYTHONIOENCODING: "utf-8",
                PYTHONUTF8: "1"
            },
            windowsHide: true
        });

        // Set encoding to UTF-8 for Vietnamese support
        this.porcupineProcess.stdout.setEncoding("utf8");
        this.porcupineProcess.stderr.setEncoding("utf8");

        this.porcupineProcess.stdout.on("data", (data) => {
            const lines = data.trim().split("\n");
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

    // Decode base64-encoded text fields from Python
    decodeBase64Text: function (event, field) {
        if (event[field + "_encoded"] && event[field]) {
            return Buffer.from(event[field], "base64").toString("utf8");
        }
        return event[field] || "";
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

            case "listening_active":
                console.log("[MMM-LLMsAssistant] Actively listening to user speech...");
                this.sendSocketNotification("LISTENING_ACTIVE", {});
                break;

            case "tool_call":
                console.log(`[MMM-LLMsAssistant] Tool call: ${event.tool_name || ''}`);
                this.sendSocketNotification("TOOL_CALL", { tool_name: event.tool_name || '' });
                break;

            case "speech": {
                const text = this.decodeBase64Text(event, "text");
                console.log(`[MMM-LLMsAssistant] Speech: ${text}`);
                this.sendSocketNotification("SPEECH_RECOGNIZED", { text: text });
                break;
            }

            case "llm_response": {
                const text = this.decodeBase64Text(event, "text");
                console.log(`[MMM-LLMsAssistant] LLM: ${text}`);
                this.sendSocketNotification("LLM_RESPONSE", { text: text });
                break;
            }

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

            case "reset_detected": {
                const text = this.decodeBase64Text(event, "text");
                console.log(`[MMM-LLMsAssistant] Reset detected: ${text}`);
                this.sendSocketNotification("RESET_DETECTED", { text: text });
                break;
            }

            case "max_turns_reached":
                console.log("[MMM-LLMsAssistant] Max conversation turns reached");
                this.sendSocketNotification("MAX_TURNS_REACHED", {});
                break;

            case "debug": {
                const message = this.decodeBase64Text(event, "message");
                console.log(`[MMM-LLMsAssistant] DEBUG: ${message}`);
                break;
            }

            case "error": {
                const message = this.decodeBase64Text(event, "message");
                console.error(`[MMM-LLMsAssistant] ${message}`);
                this.sendSocketNotification("ERROR", { message: message });
                break;
            }

            // Music control events
            case "music_lower_volume":
                console.log("[MMM-LLMsAssistant] Lowering music volume for conversation");
                this.sendSocketNotification("MUSIC_LOWER_VOLUME", {});
                break;

            case "music_restore_volume":
                console.log("[MMM-LLMsAssistant] Restoring music volume");
                this.sendSocketNotification("MUSIC_RESTORE_VOLUME", {});
                break;

            case "music_action": {
                const action = event.action;
                const data = event.data || {};
                console.log(`[MMM-LLMsAssistant] Music action: ${action}, data: ${JSON.stringify(data)}`);
                this.sendSocketNotification(action, data);
                break;
            }
        }
    },

    stop: function () {
        if (this.porcupineProcess) {
            this.porcupineProcess.kill();
        }
    }
});
