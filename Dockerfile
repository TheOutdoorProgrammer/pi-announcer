FROM debian:bullseye-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    pulseaudio-utils \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Piper TTS binary (armv7l)
RUN curl -fsSL https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_armv7l.tar.gz \
    | tar xz -C /opt

# Create data directories
RUN mkdir -p /data/voices /data/cache

# Install Python dependencies
COPY announcer/requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

# Copy application
COPY announcer/ /app/announcer/

WORKDIR /app
EXPOSE 8080

ENV PIPER_BINARY=/opt/piper/piper
ENV PIPER_MODEL=/data/voices/en_US-libritts_r-medium.onnx
ENV PIPER_SPEAKER=82
ENV DEFAULT_VOLUME=80
ENV CACHE_DIR=/data/cache
ENV SILENCE_MS=1000
ENV PULSE_SERVER=unix:/run/user/1000/pulse/native

CMD ["python3", "-m", "uvicorn", "announcer.main:app", "--host", "0.0.0.0", "--port", "8080"]
