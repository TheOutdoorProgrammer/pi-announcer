import asyncio
import logging
import subprocess
import struct
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SILENCE_PATH = Path("/tmp/silence.wav")


def _ensure_silence_file() -> None:
    """Create a short silence WAV to wake up HDMI audio before announcements."""
    if SILENCE_PATH.exists():
        return
    sample_rate = 22050
    duration_ms = 500
    num_samples = int(sample_rate * duration_ms / 1000)
    with wave.open(str(SILENCE_PATH), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{num_samples}h", *([0] * num_samples)))
    logger.info("Created silence pad: %s", SILENCE_PATH)


class AudioPlayer:
    def __init__(self, default_volume: int = 80):
        self.default_volume = default_volume
        self._lock = asyncio.Lock()
        _ensure_silence_file()

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
