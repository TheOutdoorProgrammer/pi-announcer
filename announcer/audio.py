import asyncio
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioPlayer:
    def __init__(self, default_volume: int = 80):
        self.default_volume = default_volume
        self._lock = asyncio.Lock()

    async def play(self, wav_path: Path, volume: int | None = None) -> None:
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
