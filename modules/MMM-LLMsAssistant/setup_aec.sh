#!/usr/bin/env bash
# Acoustic Echo Cancellation setup for Raspberry Pi.
#
# Loads the WebRTC-AEC echo-cancel module so Porcupine + STT can still hear the
# user when MagicMirror is playing music through the same speaker. Works on both
# pure PulseAudio (Pi OS Bullseye and earlier) and PipeWire (Pi OS Bookworm+),
# because PipeWire ships a PulseAudio-compatible `pactl` interface.
#
# Run once after install. Re-run is idempotent (unloads the previous instance).

set -euo pipefail

SOURCE_NAME="mic_aec"
SINK_NAME="speaker_aec"

if ! command -v pactl >/dev/null 2>&1; then
    echo "pactl not found. Install pulseaudio-utils or pipewire-pulse." >&2
    exit 1
fi

if ! pactl info >/dev/null 2>&1; then
    echo "PulseAudio/PipeWire is not running for this user." >&2
    echo "Start the user audio service first:  systemctl --user start pulseaudio.service  (or pipewire-pulse.service)" >&2
    exit 1
fi

server_name="$(pactl info | awk -F': ' '/Server Name/ {print $2}')"
echo "Detected audio server: ${server_name}"

# Capture current defaults so the AEC sink can chain to the real hardware sink.
default_sink="$(pactl info | awk -F': ' '/Default Sink/ {print $2}')"
default_source="$(pactl info | awk -F': ' '/Default Source/ {print $2}')"
echo "Current default sink:   ${default_sink}"
echo "Current default source: ${default_source}"

if [[ "${default_sink}" == "${SINK_NAME}" || "${default_source}" == "${SOURCE_NAME}" ]]; then
    echo "AEC defaults already active. Resetting so we can reload cleanly..."
    # Pick a non-AEC fallback so unloading doesn't leave us with no defaults.
    fallback_sink="$(pactl list short sinks   | awk -v s="${SINK_NAME}"   '$2!=s {print $2; exit}')"
    fallback_source="$(pactl list short sources | awk -v s="${SOURCE_NAME}" '$2!=s && $2 !~ /\.monitor$/ {print $2; exit}')"
    [[ -n "${fallback_sink:-}"   ]] && pactl set-default-sink   "${fallback_sink}"
    [[ -n "${fallback_source:-}" ]] && pactl set-default-source "${fallback_source}"
    default_sink="${fallback_sink:-${default_sink}}"
    default_source="${fallback_source:-${default_source}}"
fi

# Unload any existing echo-cancel instance.
existing="$(pactl list short modules | awk '/module-echo-cancel/ {print $1}')"
if [[ -n "${existing}" ]]; then
    echo "Unloading existing module-echo-cancel (id=${existing})"
    while read -r id; do pactl unload-module "${id}"; done <<<"${existing}"
fi

# Load the module. WebRTC backend gives the best AEC on speech.
echo "Loading module-echo-cancel (WebRTC backend)..."
pactl load-module module-echo-cancel \
    aec_method=webrtc \
    source_name="${SOURCE_NAME}" \
    source_master="${default_source}" \
    sink_name="${SINK_NAME}" \
    sink_master="${default_sink}" \
    aec_args="analog_gain_control=0 digital_gain_control=0 noise_suppression=0 voice_detection=0 extended_filter=1" \
    use_master_format=1 >/dev/null

# Make the AEC source/sink the system defaults so browser audio (music) flows
# through the cancelled sink and PvRecorder reads from the cancelled source.
pactl set-default-sink   "${SINK_NAME}"
pactl set-default-source "${SOURCE_NAME}"

echo "AEC active. Defaults are now:"
pactl info | grep -E 'Default (Sink|Source):'

# Persist across reboots by appending to the user's pulse autoload config.
# PipeWire-pulse reads the same path, so this works for both backends.
PA_CONF_DIR="${HOME}/.config/pulse"
PA_CONF="${PA_CONF_DIR}/default.pa"
mkdir -p "${PA_CONF_DIR}"
if [[ ! -f "${PA_CONF}" ]]; then
    cat > "${PA_CONF}" <<'EOF'
# Inherit the system defaults, then add our own overrides below.
.include /etc/pulse/default.pa
EOF
fi

if ! grep -q "module-echo-cancel" "${PA_CONF}"; then
    cat >> "${PA_CONF}" <<EOF

# === MMM-LLMsAssistant AEC (added by setup_aec.sh) ===
load-module module-echo-cancel aec_method=webrtc source_name=${SOURCE_NAME} sink_name=${SINK_NAME} aec_args="analog_gain_control=0 digital_gain_control=0 noise_suppression=0 voice_detection=0 extended_filter=1" use_master_format=1
set-default-source ${SOURCE_NAME}
set-default-sink ${SINK_NAME}
EOF
    echo "Persisted AEC config to ${PA_CONF}"
else
    echo "AEC config already present in ${PA_CONF}, leaving it alone."
fi

# Sanity check that ALSA (which PvRecorder uses) is bridged to PulseAudio.
# On standard Pi OS this is true; warn loudly if it isn't, because otherwise
# PvRecorder will read directly from the I2S card and bypass the AEC source.
if ! grep -RIlq 'type[[:space:]]*pulse' /etc/asound.conf "${HOME}/.asoundrc" 2>/dev/null; then
    cat <<'EOF'

WARNING: ALSA does not appear to route through PulseAudio.
PvRecorder uses ALSA, so without a bridge it will skip AEC and read the raw mic.

Fix it with one of:
  sudo apt install pulseaudio-alsa     # PulseAudio systems
  sudo apt install pipewire-alsa       # PipeWire systems (Pi OS Bookworm+)

Then verify with:  cat /etc/asound.conf
EOF
fi

cat <<EOF

Done. Test it:
  1) Restart MagicMirror so wakeword_service.py picks up the new default source.
  2) Play music through the SoundCloud module.
  3) Say "Hey Lens" while music is playing -- it should still trigger.

If the wake word still misses while music plays, run:
  python wakeword_service.py --list-devices
and pick the index of "${SOURCE_NAME}", then set audioDeviceIndex in config.js.
EOF
