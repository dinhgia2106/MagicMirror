# MMM-LLMsAssistant

Voice Assistant module for MagicMirror with wake word detection using Picovoice Porcupine.

## Features

- Wake word detection ("Hey lens")
- Speech-to-text (Google Speech Recognition)
- LLM integration (Gemini or OpenAI)
- Text-to-speech (Edge TTS - Vietnamese)
- Animated UI with status indicator

## Installation

```bash
cd ~/MagicMirror/modules/MMM-LLMsAssistant
npm install
pip install -r requirements.txt
```

## Configuration

Add to `config/config.js`:

```javascript
{
    module: "MMM-LLMsAssistant",
    position: "bottom_left",
    config: {
        wakeWord: "Hey lens",
        picovoiceAccessKey: "YOUR_KEY", // console.picovoice.ai
        llmProvider: "gemini",          // or "openai"
        llmApiKey: "YOUR_KEY",          // aistudio.google.com
        language: "vi-VN",
        voiceId: "vi-VN-NamMinhNeural"
    }
}
```

## Usage

1. Say "Hey lens" to activate
2. Ask your question in Vietnamese
3. Listen to the response

## Acoustic Echo Cancellation (Raspberry Pi)

So the wake word still triggers while music is playing through the same speaker, set up the system AEC once:

```bash
cd ~/MagicMirror/modules/MMM-LLMsAssistant
chmod +x setup_aec.sh
./setup_aec.sh
```

This loads PulseAudio/PipeWire's `module-echo-cancel` (WebRTC backend), routes the SoundCloud sink and the mic source through it, and persists the config across reboots. After running it, restart MagicMirror.

If `PvRecorder` does not pick the AEC source automatically, list devices and pin it via config:

```bash
python wakeword_service.py --list-devices
```

Then in `config/config.js`:

```javascript
audioDeviceIndex: 2   // index of "mic_aec" from the list above
```

## API Keys

- **Picovoice**: [console.picovoice.ai](https://console.picovoice.ai/)
- **Gemini**: [aistudio.google.com](https://aistudio.google.com/)
