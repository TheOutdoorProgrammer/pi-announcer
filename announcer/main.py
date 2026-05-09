import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .tts import PiperTTS
from .audio import AudioPlayer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Pi Announcer", version="1.0.0")

tts = PiperTTS(
    piper_binary=os.getenv("PIPER_BINARY", "/opt/piper/piper"),
    model_path=os.getenv("PIPER_MODEL", "/data/voices/en_US-libritts_r-medium.onnx"),
    speaker=int(os.getenv("PIPER_SPEAKER", "82")),
    cache_dir=os.getenv("CACHE_DIR", "/data/cache"),
)

player = AudioPlayer(
    default_volume=int(os.getenv("DEFAULT_VOLUME", "80")),
    silence_ms=int(os.getenv("SILENCE_MS", "1000")),
)


class AnnounceRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    volume: Optional[int] = Field(None, ge=0, le=100)
    priority: str = Field("normal", pattern="^(normal|urgent)$")


class AnnounceResponse(BaseModel):
    status: str
    message: str
    cached: bool


class HealthResponse(BaseModel):
    status: str
    voice: str
    speaker: int
    cache_size: int


async def _play_in_background(wav_path: Path, volume: Optional[int]) -> None:
    """Play audio without blocking the HTTP response."""
    try:
        await player.play(wav_path, volume)
    except Exception:
        logger.exception("Background playback failed for: %s", wav_path)


@app.post("/announce", response_model=AnnounceResponse)
async def announce(req: AnnounceRequest):
    cache_key = tts._cache_key(req.message)
    was_cached = (tts.cache_dir / f"{cache_key}.wav").exists()

    # Generate TTS (blocks on first request, instant on cache hit)
    try:
        wav_path = await asyncio.to_thread(tts.synthesize, req.message)
    except Exception as e:
        logger.exception("TTS generation failed")
        raise HTTPException(status_code=500, detail=str(e))

    # Fire and forget playback — return HTTP response immediately
    asyncio.create_task(_play_in_background(wav_path, req.volume))

    return AnnounceResponse(
        status="ok",
        message=req.message,
        cached=was_cached,
    )


@app.post("/cache/clear")
async def clear_cache():
    count = tts.clear_cache()
    return {"status": "ok", "cleared": count}


@app.get("/health", response_model=HealthResponse)
async def health():
    cache_files = list(tts.cache_dir.glob("*.wav"))
    return HealthResponse(
        status="ok",
        voice=os.path.basename(tts.model_path),
        speaker=tts.speaker,
        cache_size=len(cache_files),
    )
