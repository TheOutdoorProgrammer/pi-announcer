import asyncio
import logging
import os
import subprocess
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

# Queue for sequential announcement processing
_announce_queue: asyncio.Queue = asyncio.Queue()


async def _queue_worker() -> None:
    """Process announcements sequentially from the queue."""
    while True:
        message, volume = await _announce_queue.get()
        try:
            wav_path = await asyncio.to_thread(tts.synthesize, message)
            await player.play(wav_path, volume)
        except Exception:
            logger.exception("Announce failed for: %s", message)
        finally:
            _announce_queue.task_done()


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(_queue_worker())


class AnnounceRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    volume: Optional[int] = Field(None, ge=0, le=100)
    priority: str = Field("normal", pattern="^(normal|urgent)$")


class AnnounceResponse(BaseModel):
    status: str
    message: str
    queued: bool


class HealthResponse(BaseModel):
    status: str
    voice: str
    speaker: int
    cache_size: int
    queue_size: int


@app.post("/announce", response_model=AnnounceResponse)
async def announce(req: AnnounceRequest):
    # Drop it on the queue and return immediately
    await _announce_queue.put((req.message, req.volume))
    logger.info("Queued: '%s' (queue size: %d)", req.message, _announce_queue.qsize())

    return AnnounceResponse(
        status="ok",
        message=req.message,
        queued=True,
    )


CEC_DEVICE = os.getenv("CEC_DEVICE", "/dev/cec0")


async def _cec_volume_step(direction: str, steps: int = 1) -> None:
    """Send CEC volume up/down/mute commands to the TV."""
    code = {"up": "0x41", "down": "0x42", "mute": "0x43"}[direction]
    for _ in range(steps):
        await asyncio.to_thread(
            subprocess.run,
            ["cec-ctl", f"-d{CEC_DEVICE}", "--to", "0",
             "--user-control-pressed", f"ui-cmd={code}"],
            capture_output=True, timeout=5,
        )
        await asyncio.sleep(0.2)
        await asyncio.to_thread(
            subprocess.run,
            ["cec-ctl", f"-d{CEC_DEVICE}", "--to", "0",
             "--user-control-released"],
            capture_output=True, timeout=5,
        )
        await asyncio.sleep(0.1)


class VolumeRequest(BaseModel):
    steps: int = Field(1, ge=1, le=20)


@app.post("/volume/up")
async def volume_up(req: Optional[VolumeRequest] = None):
    steps = req.steps if req else 1
    await _cec_volume_step("up", steps)
    logger.info("CEC volume up %d steps", steps)
    return {"status": "ok", "direction": "up", "steps": steps}


@app.post("/volume/down")
async def volume_down(req: Optional[VolumeRequest] = None):
    steps = req.steps if req else 1
    await _cec_volume_step("down", steps)
    logger.info("CEC volume down %d steps", steps)
    return {"status": "ok", "direction": "down", "steps": steps}


@app.post("/volume/mute")
async def volume_mute():
    await _cec_volume_step("mute", 1)
    logger.info("CEC mute toggle")
    return {"status": "ok", "action": "mute"}


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
        queue_size=_announce_queue.qsize(),
    )
