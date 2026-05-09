import asyncio
import logging
import os
import subprocess
import struct
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SILENCE_PATH = Path("/tmp/silence.wav")


def _create_silence_file(duration_ms: int) -> None:
    """Create a silence WAV to wake up HDMI audio before announcements."""
    # Always recreate in case duration changed
    sample_rate = 22050
    num_samples = int(sample_rate * duration_ms / 1000)
    with wave.open(str(SILENCE_PATH), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{num_samples}h", *([0] * num_samples)))
    logger.info("Created silence pad: %dms -> %s", duration_ms, SILENCE_PATH)


class AudioPlayer:
    def __init__(self, default_volume: int = 80, silence_ms: int = 1000):
        self.default_volume = default_volume
        self.silence_ms = silence_ms
        self._lock = asyncio.Lock()
        if silence_ms > 0:
            _create_silence_file(silence_ms)

    async def play(self, wav_path: Path, volume: Optional[int] = None) -> None:
        """Play a WAV file through PulseAudio. Queues if something is already playing."""
        vol = volume if volume is not None else self.default_volume

        async with self._lock:
            # Set volume (pactl uses 0-65536, we accept 0-100)
            pa_volume = int((vol / 100) * 65536)
            await asyncio.to_thread(
                subprocess.run,
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", str(pa_volume)],
                capture_output=True,
                timeout=5,
            )

            # Play a short silence to wake up HDMI DAC before the real audio
            if self.silence_ms > 0 and SILENCE_PATH.exists():
                await asyncio.to_thread(
                    subprocess.run,
                    ["paplay", str(SILENCE_PATH)],
                    capture_output=True,
                    timeout=5,
                )

            logger.info("Playing %s at volume %d%%", wav_path.name, vol)
            result = await asyncio.to_thread(
                subprocess.run,
                ["paplay", str(wav_path)],
                capture_output=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.error("paplay failed: %s", result.stderr.decode())
                raise RuntimeError(f"Audio playback failed: {result.stderr.decode()}")
