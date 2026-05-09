import hashlib
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class PiperTTS:
    def __init__(
        self,
        piper_binary: str = "/opt/piper/piper",
        model_path: str = "/data/voices/en_US-libritts_r-medium.onnx",
        speaker: int = 82,
        cache_dir: str = "/data/cache",
    ):
        self.piper_binary = piper_binary
        self.model_path = model_path
        self.speaker = speaker
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, message: str) -> str:
        raw = f"{message}|{self.model_path}|{self.speaker}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def synthesize(self, message: str) -> Path:
        """Generate a WAV file from text. Returns path to cached WAV."""
        key = self._cache_key(message)
        wav_path = self.cache_dir / f"{key}.wav"

        if wav_path.exists():
            logger.info("Cache hit for '%s' -> %s", message, wav_path)
            return wav_path

        logger.info("Generating TTS for '%s' (speaker %d)", message, self.speaker)

        result = subprocess.run(
            [
                self.piper_binary,
                "--model", self.model_path,
                "--speaker", str(self.speaker),
                "--output_file", str(wav_path),
            ],
            input=message.encode(),
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error("Piper failed: %s", result.stderr.decode())
            wav_path.unlink(missing_ok=True)
            raise RuntimeError(f"Piper TTS failed: {result.stderr.decode()}")

        logger.info("Generated %s (%.1f KB)", wav_path, wav_path.stat().st_size / 1024)
        return wav_path

    def clear_cache(self) -> int:
        """Remove all cached WAV files. Returns count of files removed."""
        count = 0
        for f in self.cache_dir.glob("*.wav"):
            f.unlink()
            count += 1
        logger.info("Cleared %d cached files", count)
        return count
