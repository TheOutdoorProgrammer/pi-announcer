import asyncio
import logging
import os

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
)


class AnnounceRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    volume: int | None = Field(None, ge=0, le=100)
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


@app.post("/announce", response_model=AnnounceResponse)
async def announce(req: AnnounceRequest):
    try:
        cache_key_before = tts._cache_key(req.message)
        was_cached = (tts.cache_dir / f"{cache_key_before}.wav").exists()

        wav_path = await asyncio.to_thread(tts.synthesize, req.message)
        await player.play(wav_path, req.volume)

        return AnnounceResponse(
            status="ok",
            message=req.message,
            cached=was_cached,
        )
    except Exception as e:
        logger.exception("Announce failed")
        raise HTTPException(status_code=500, detail=str(e))


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
