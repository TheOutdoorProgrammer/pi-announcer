# Pi Announcer

Local TTS announcement service for Raspberry Pi. Generates speech with [Piper TTS](https://github.com/rhasspy/piper) and plays it over HDMI audio. Built for Home Assistant but works with anything that can send HTTP requests.

## How It Works

```
HA Automation -> HTTP POST -> pi-announcer:8180/announce -> Piper TTS -> PulseAudio -> HDMI -> TV speakers
```

- Piper generates WAV files locally (no cloud, no internet needed after setup)
- WAV files are cached so repeated announcements play instantly
- Requests return immediately; TTS generation and playback happen in a background queue
- Audio is converted to stereo 44100Hz via sox to match the PulseAudio sink and prevent HDMI pop/click artifacts
- A 1-second silence pad plays before each announcement to wake up the HDMI DAC

## Voice

Uses the `en_US-libritts_r-medium` model with speaker 82 (male). Voice can be changed via environment variables in `docker-compose.yml`. Browse voices at [rhasspy.github.io/piper-samples](https://rhasspy.github.io/piper-samples/).

## Quick Start

```bash
git clone https://github.com/TheOutdoorProgrammer/pi-announcer.git
cd pi-announcer
bash setup.sh
```

`setup.sh` handles everything: installs PulseAudio if missing, configures HDMI audio output with high-quality resampling, downloads the voice model, pulls the Docker image from GHCR, and starts the service.

## API

### POST /announce

Queue a TTS announcement. Returns immediately.

```bash
curl -X POST http://<pi-ip>:8180/announce \
  -H 'Content-Type: application/json' \
  -d '{"message": "Front door opened"}'
```

Parameters:
- `message` (required): Text to speak (1-500 characters)
- `volume` (optional): Playback volume 0-100 (default: 80)
- `priority` (optional): `normal` or `urgent` (default: normal)

### POST /cache/clear

Clear all cached WAV files. Use after changing voice/speaker settings.

```bash
curl -X POST http://<pi-ip>:8180/cache/clear
```

### GET /health

```bash
curl http://<pi-ip>:8180/health
```

Returns voice model, speaker ID, cache size, and queue depth.

## Configuration

All settings are environment variables in `docker-compose.yml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `PIPER_SPEAKER` | `82` | Piper speaker ID (model-dependent) |
| `DEFAULT_VOLUME` | `80` | Default playback volume (0-100) |
| `SILENCE_MS` | `1000` | Silence pad before announcements in ms (HDMI DAC wake) |
| `PIPER_MODEL` | `/data/voices/en_US-libritts_r-medium.onnx` | Path to voice model inside container |
| `PULSE_SERVER` | `tcp:172.17.0.1:4713` | PulseAudio server address |

Change a value, then `docker restart pi-announcer`. No image rebuild needed.

## Home Assistant Integration

Add to HA's `configuration.yaml` under `rest_command:`:

```yaml
rest_command:
  pi_announce:
    url: "http://<pi-ip>:8180/announce"
    method: POST
    content_type: "application/json"
    payload: '{"message": "{{ message }}", "volume": {{ volume | default(80) }}}'
    timeout: 30
```

Then create a reusable script:

```yaml
script:
  announce:
    alias: Announce
    mode: queued
    max: 10
    fields:
      message:
        name: Message
        required: true
        selector:
          text:
            multiline: true
    sequence:
      - action: rest_command.pi_announce
        data:
          message: "{{ message }}"
```

Use in automations:

```yaml
action:
  - action: script.announce
    data:
      message: "The {{ trigger.to_state.attributes.friendly_name }} has been opened."
```

## Architecture

- **Docker image**: Built for `linux/arm/v7` via GitHub Actions, pushed to GHCR
- **Base**: `debian:bullseye-slim` (provides GLIBC 2.29+ for Piper binary)
- **TTS**: Piper standalone binary (C++/ONNX, no Python dependency for inference)
- **Audio conversion**: sox converts Piper's mono 22050Hz output to stereo 44100Hz
- **Playback**: PulseAudio via TCP from container to host
- **Web server**: Python FastAPI + uvicorn
- **Container**: Runs privileged for PulseAudio access, `restart: unless-stopped`

## PulseAudio Setup (handled by setup.sh)

The setup script configures:
- TCP access with anonymous auth (so Docker containers can connect)
- HDMI as default audio sink
- High-quality resampler (`src-sinc-best-quality`)
- Default sample rate 44100Hz, stereo
- PulseAudio systemd user service enabled with lingering for boot persistence

## Cache

WAV files are cached in a Docker named volume (`cache`). Cache keys are based on the normalized (lowercased, trimmed) message text + model + speaker ID. Cache survives container restarts and image updates.

Clear cache after changing voice settings:
```bash
curl -X POST http://<pi-ip>:8180/cache/clear
```

## Updating

```bash
cd ~/pi-announcer
git pull
docker compose pull
docker compose up -d
```

The Docker image is rebuilt automatically on push to `main` via GitHub Actions.
