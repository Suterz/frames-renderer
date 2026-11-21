from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError

from .backends.comfy import ComfyBackend
from .grounding import NeedsReview
from .runner import FFMPEG, FFPROBE, FONT, PROFILE, ROOT, atomic_json, probe_audio, run
from .schema import Story

app=FastAPI(title="storyboard-renderer",version="0.1.0")
tasks=queue.Queue()
lock=threading.Lock()


def folder(job_id):
    if len(job_id)!=32 or any(c not in "0123456789abcdef" for c in job_id):
        raise HTTPException(status_code=404,detail="unknown job")
    path=ROOT/job_id
    if not (path/"status.json").exists():
        raise HTTPException(status_code=404,detail="unknown job")
    return path


def save(job,status):
    status["updated"]=time.time()
    atomic_json(job/"status.json",status)


def worker():
    while True:
        job_id=tasks.get()
        try:
            job=folder(job_id)
            with lock:
                status=json.loads((job/"status.json").read_text())
                status["state"]="running"
                status["phase"]="backend readiness"
                status["started"]=time.time()
                save(job,status)
                try:
                    run(job,status,lambda s:save(job,s))
                except NeedsReview as exc:
                    status.update(state="needs_review",error={"kind":"ambiguous_visual_target","message":str(exc),"panel":status.get("current_panel")})
                except Exception as exc:
                    status.update(state="failed",error={"kind":type(exc).__name__,"message":str(exc),"panel":status.get("current_panel")})
                else:
                    status.update(state="succeeded",phase="complete",video=str(job/"video.mp4"))
                save(job,status)
        finally:
            tasks.task_done()


@app.on_event("startup")
def startup():
    ROOT.mkdir(parents=True,exist_ok=True)
    for path in ROOT.glob("*/status.json"):
        try:
            state=json.loads(path.read_text())
            if state["state"]=="queued":tasks.put(path.parent.name)
            elif state["state"]=="running":
                state.update(state="interrupted",error={"kind":"server_restart","message":"Worker interrupted by server exit; submit again with reuse_from"})
                save(path.parent,state)
        except Exception:pass
    threading.Thread(target=worker,daemon=True,name="single-gpu-worker").start()


@app.get("/health")
def health():
    return {"status":"alive"}


@app.get("/ready")
def ready():
    missing=[]
    for path in [FFMPEG,FFPROBE,FONT]:
        if not Path(path).exists():missing.append(path)
    model_dir=Path.home()/"ai/ComfyUI/models"
    required=(
        ["diffusion_models/flux-2-klein-4b.safetensors","text_encoders/qwen_3_4b.safetensors","vae/flux2-vae.safetensors"]
        if PROFILE=="flux" else ["checkpoints/hidream_o1_image_bf16.safetensors"]
    )
    for file in required:
        path=model_dir/file
        if not path.is_file() or path.stat().st_size<100_000_000:missing.append(f"inference model {path}")
    vision=Path.home()/"ai/models/vision/qwen3-vl-8b/model.safetensors.index.json"
    if not vision.is_file():missing.append("local Qwen3-VL grounding model")
    try:
        ComfyBackend(os.environ.get("STORY_COMFY_URL","http://127.0.0.1:8188"),PROFILE).ready()
    except Exception as exc:missing.append(f"generation backend: {str(exc)[:220]}")
    if missing:raise HTTPException(status_code=503,detail={"missing":missing})
    return {"status":"ready","profile":PROFILE,"gpu_jobs":"serialized"}


@app.post("/renders",status_code=202)
async def render_story(story: str=Form(...),audio: UploadFile=File(...),reuse_from: str|None=Form(default=None)):
    try:
        parsed=Story.model_validate_json(story)
        if parsed.audio.get("part")!="audio":
            raise ValueError("audio.part must be 'audio'")
    except (ValidationError,ValueError) as exc:
        raise HTTPException(status_code=422,detail=str(exc))
    if reuse_from:
        folder(reuse_from)
    b=await audio.read()
    if len(b)>20_000_000:
        raise HTTPException(status_code=413,detail="audio exceeds 20 MB")
    job_id=uuid.uuid4().hex
    job=ROOT/job_id
    job.mkdir(parents=True)
    (job/"request.json").write_text(parsed.model_dump_json(indent=2,by_alias=True))
    (job/"signature.md").write_text(parsed.signature)
    (job/"narration.wav").write_bytes(b)
    try:probe_audio(job/"narration.wav",parsed)
    except Exception as exc:
        for name in ("narration.wav","signature.md","request.json"):
            (job/name).unlink()
        job.rmdir()
        raise HTTPException(status_code=422,detail=str(exc))
    status={"id":job_id,"story_id":parsed.story_id,"state":"queued","phase":"queued","current_panel":None,
            "completed":0,"total":len(parsed.panels),"created":time.time(),"reuse_from":reuse_from,"artifacts":str(job)}
    save(job,status)
    tasks.put(job_id)
    return {"id":job_id,"state":"queued","status_url":f"/renders/{job_id}","video_url":f"/renders/{job_id}/video"}


@app.get("/renders/{job_id}")
def status(job_id:str):
    return json.loads((folder(job_id)/"status.json").read_text())


@app.get("/renders/{job_id}/video")
def video(job_id:str):
    job=folder(job_id)
    state=json.loads((job/"status.json").read_text())
    if state["state"]!="succeeded" or not (job/"video.mp4").is_file():
        raise HTTPException(status_code=409,detail={"state":state["state"],"error":state.get("error")})
    return FileResponse(job/"video.mp4",media_type="video/mp4",filename=f"{state['story_id']}.mp4")
