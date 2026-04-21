import asyncio
import json
import logging
import queue
import shutil
import threading

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from dotenv import load_dotenv
load_dotenv()  # loads .env from project root → makes GROQ_API_KEY available
from dataclasses import asdict
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from lower_third.pipeline import generate_lower_third

log = logging.getLogger(__name__)

OUTPUT_DIR = Path("./lower_third_output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Lower Third Generation API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assets", StaticFiles(directory=str(OUTPUT_DIR)), name="assets")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


class GenerateRequest(BaseModel):
    prompt: str
    upstream_signals: dict = {}
    project_fps: int = 30
    total_duration_ms: int | None = None
    tts_timestamps: dict | None = None
    instance_id: str | None = None


class GenerateResponse(BaseModel):
    instance_id: str
    video_url: str
    manifest: dict
    cache_hit: bool
    qc_passed: bool
    qc_warnings: list[str]
    min_contrast_ratio: float


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0"}


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    if not request.prompt:
        raise HTTPException(status_code=422, detail="prompt cannot be empty")

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: generate_lower_third(
                user_prompt=request.prompt,
                upstream_signals=request.upstream_signals,
                output_dir=OUTPUT_DIR,
                project_fps=request.project_fps,
                total_duration_ms=request.total_duration_ms,
                tts_timestamps=request.tts_timestamps,
                instance_id=request.instance_id,
            ),
        )

        spec_instance_id = result["manifest"]["instance_id"]
        video_url = f"/assets/{spec_instance_id}.webm"
        target_path = OUTPUT_DIR / f"{spec_instance_id}.webm"
        source_path = Path(result["video_path"])

        if source_path.resolve() != target_path.resolve() and source_path.exists():
            shutil.move(str(source_path), str(target_path))

        qc = result["qc_report"]

        return GenerateResponse(
            instance_id=spec_instance_id,
            video_url=video_url,
            manifest=result["manifest"],
            cache_hit=result["cache_hit"],
            qc_passed=qc.passed,
            qc_warnings=qc.warnings,
            min_contrast_ratio=qc.min_contrast_ratio,
        )
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Pipeline error")
        raise HTTPException(status_code=500, detail=str(e))


STAGE_LABELS = {
    "brand_resolve": "Brand Resolution",
    "llm_parse": "Parsing Prompt (LLM)",
    "cache_check": "Cache Check",
    "geometry": "Geometric Corrections",
    "interpolation": "Frame Interpolation",
    "render": "Rendering Frames",
    "encode": "Encoding Video",
    "qc": "Quality Check",
    "manifest": "Writing Manifest",
}


@app.post("/generate/stream")
async def generate_stream(request: GenerateRequest):
    if not request.prompt:
        raise HTTPException(status_code=422, detail="prompt cannot be empty")

    q: queue.Queue = queue.Queue()

    def progress_callback(stage: str) -> None:
        q.put({"stage": stage, "label": STAGE_LABELS.get(stage, stage)})

    def run_pipeline() -> None:
        try:
            result = generate_lower_third(
                user_prompt=request.prompt,
                upstream_signals=request.upstream_signals,
                output_dir=OUTPUT_DIR,
                project_fps=request.project_fps,
                total_duration_ms=request.total_duration_ms,
                tts_timestamps=request.tts_timestamps,
                instance_id=request.instance_id,
                progress_callback=progress_callback,
            )
            q.put({"result": result})
        except Exception as e:
            log.exception("Pipeline error in stream")
            q.put({"error": str(e)})

    async def event_stream():
        loop = asyncio.get_event_loop()
        thread = threading.Thread(target=run_pipeline, daemon=True)
        thread.start()

        while True:
            try:
                item = await loop.run_in_executor(None, lambda: q.get(timeout=120))
            except queue.Empty:
                yield "data: {\"error\": \"timeout\"}\n\n"
                break

            if "error" in item:
                yield f"data: {json.dumps(item)}\n\n"
                break

            if "result" in item:
                raw = item["result"]
                spec_instance_id = raw["manifest"]["instance_id"]
                video_url = f"/assets/{spec_instance_id}.webm"
                target_path = OUTPUT_DIR / f"{spec_instance_id}.webm"
                source_path = Path(raw["video_path"])
                if source_path.resolve() != target_path.resolve() and source_path.exists():
                    shutil.move(str(source_path), str(target_path))
                qc = raw["qc_report"]
                response_data = GenerateResponse(
                    instance_id=spec_instance_id,
                    video_url=video_url,
                    manifest=raw["manifest"],
                    cache_hit=raw["cache_hit"],
                    qc_passed=qc.passed,
                    qc_warnings=qc.warnings,
                    min_contrast_ratio=qc.min_contrast_ratio,
                )
                yield f"data: {json.dumps({'result': response_data.model_dump()})}\n\n"
                break

            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/manifest/{instance_id}")
async def get_manifest(instance_id: str):
    try:
        path = OUTPUT_DIR / f"{instance_id}_manifest.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Manifest not found: {instance_id}")
        return json.loads(path.read_text())
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Manifest read error")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("lower_third.api:app", host="0.0.0.0", port=8001, reload=True)
