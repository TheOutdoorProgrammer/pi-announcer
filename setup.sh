#!/usr/bin/env bash
set -euo pipefail

VOICE_MODEL="en_US-libritts_r-medium"
VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/libritts_r/medium"

echo "=== Pi Announcer Setup ==="

# Ensure PulseAudio is installed and running
if ! command -v pulseaudio &>/dev/null; then
    echo "Installing PulseAudio..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq pulseaudio pulseaudio-utils
fi

# Configure PulseAudio with TCP access for Docker containers
PULSE_CONFIG="$HOME/.config/pulse/default.pa"
mkdir -p "$(dirname "$PULSE_CONFIG")"
echo "Configuring PulseAudio for Docker TCP access, HDMI keep-alive, and high-quality resampling..."
cat > "$PULSE_CONFIG" <<'EOF'
.include /etc/pulse/default.pa
load-module module-native-protocol-tcp auth-anonymous=1
set-default-sample-channels 2
set-default-sample-rate 44100
EOF

PULSE_DAEMON_CONFIG="$HOME/.config/pulse/daemon.conf"
cat > "$PULSE_DAEMON_CONFIG" <<'EOF'
resample-method = src-sinc-best-quality
default-sample-rate = 44100
EOF

# Restart PulseAudio to pick up new config
pulseaudio -k 2>/dev/null || true

# Start PulseAudio if not running
if ! pulseaudio --check 2>/dev/null; then
    echo "Starting PulseAudio..."
    pulseaudio --start
fi

# Set HDMI as default audio output
HDMI_SINK=$(pactl list short sinks | grep hdmi | head -1 | awk '{print $2}')
if [ -n "$HDMI_SINK" ]; then
    pactl set-default-sink "$HDMI_SINK"
    echo "Default audio sink set to: $HDMI_SINK"
else
    echo "WARNING: No HDMI sink found. Audio may not work."
fi

# Enable PulseAudio on boot via systemd user service
systemctl --user enable pulseaudio.service 2>/dev/null || true
systemctl --user enable pulseaudio.socket 2>/dev/null || true

# Enable lingering so user services start without login
sudo loginctl enable-linger "$(whoami)" 2>/dev/null || true

# Download voice model if not present
VOICE_DIR="$(docker volume inspect pi-announcer_voices --format '{{.Mountpoint}}' 2>/dev/null || echo "")"

if [ -z "$VOICE_DIR" ]; then
    echo "Creating Docker volumes and downloading voice model..."
    docker compose up --no-start 2>/dev/null || true
    VOICE_DIR="$(docker volume inspect pi-announcer_voices --format '{{.Mountpoint}}')"
fi

if [ ! -f "$VOICE_DIR/${VOICE_MODEL}.onnx" ]; then
    echo "Downloading voice model: $VOICE_MODEL..."
    sudo curl -fsSL "${VOICE_URL}/${VOICE_MODEL}.onnx" \
        -o "$VOICE_DIR/${VOICE_MODEL}.onnx"
    sudo curl -fsSL "${VOICE_URL}/${VOICE_MODEL}.onnx.json" \
        -o "$VOICE_DIR/${VOICE_MODEL}.onnx.json"
    echo "Voice model downloaded."
else
    echo "Voice model already present."
fi

# Pull and start
echo "Pulling and starting pi-announcer..."
docker compose pull
docker compose up -d

echo ""
echo "=== Setup Complete ==="
echo "Service running at: http://$(hostname -I | awk '{print $1}'):8180"
echo ""
echo "Test it:"
echo "  curl -X POST http://localhost:8180/announce \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"message\": \"Pi announcer is ready\"}'"
