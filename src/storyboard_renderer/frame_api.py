"""Durable, audio-independent panel HTTP service."""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .frame_engine import run, NeedsReview, atomic, digest
from .schema import Asset, DerivedAnchor, Overlay
from .backends.comfy import ComfyBackend

ROOT = Path(os.environ.get("FRAME_STORE", Path.home() / "Videos/frames-renderer"))
COMFY = os.environ.get("STORY_COMFY_URL", "http://127.0.0.1:8188")
PROFILE = os.environ.get("STORY_PROFILE", "flux")
tasks = queue.Queue()
submit_lock = threading.Lock()
ID = re.compile(r"[a-f0-9]{32}")
KEY = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,79}")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Session(Strict):
    story_context: str = Field(min_length=1, max_length=8000)
    visual_signature: str = Field(min_length=1, max_length=8000)
    style_ref_ids: list[str] = Field(default_factory=list, max_length=3)
    canvas: tuple[int, int] = (1080, 1920)
    assets: dict[str, Asset] = Field(default_factory=dict)
    values: dict[str, str | int] = Field(default_factory=dict)
    checks: list[dict[str, str]] = Field(default_factory=list)
    legacy_input: bool = False
    graphic_theme: Literal["paper","atlas"] | None = None
    legacy_premise: str = ""
    legacy_context: str = ""

    @model_validator(mode="after")
    def validate_session(self):
        w, h = self.canvas
        if not (360 <= w <= 2160 and h * 9 == w * 16 and w % 2 == h % 2 == 0):
            raise ValueError("expected an even 9:16 canvas")
        if not self.visual_signature.strip() or any(not KEY.fullmatch(k) for k in self.assets):
            raise ValueError("invalid signature or asset name")
        if any(not KEY.fullmatch(k) for asset in self.assets.values() for k in asset.anchors):
            raise ValueError("unsafe cutout anchor name")
        for check in self.checks:
            try:
                a, b, c = (self.values[check[k]] for k in ("total_minor", "count", "each_minor"))
                if check["kind"] != "equal_groups" or not all(type(n) is int and n > 0 for n in (a, b, c)) or a != b * c:
                    raise ValueError("invalid equal_groups arithmetic")
            except KeyError as exc:
                raise ValueError("unknown exact arithmetic operand") from exc
        return self


class Observation(Strict):
    question: str
    expected: str


class Link(Strict):
    source: str = Field(alias="from")
    to: str


class Focus(Strict):
    anchor: str
    zoom: float = Field(ge=1.25, le=5)


class Panel(Strict):
    key: str = Field(pattern=KEY.pattern)
    op: Literal["new_scene", "edit_scene", "overlay_only", "focus"]
    scene_id: str = Field(pattern=KEY.pattern)
    parent_panel_id: str | None = None
    revision_of: str | None = None
    objective: str = Field(min_length=1, max_length=5000)
    instruction: str = Field(min_length=1, max_length=5000)
    change: str = ""
    keep: str = ""
    seed: int = 42
    anchors: dict[str, str | DerivedAnchor] = Field(default_factory=dict)
    overlays: list[Overlay] = Field(default_factory=list, max_length=40)
    overlay_repairs: list[list[Overlay]] = Field(default_factory=list, max_length=4)
    layout: dict | None = None
    fallback_layout: dict | None = None
    clean_checks: list[Observation] = Field(default_factory=list, max_length=6)
    composed_checks: list[Observation] = Field(default_factory=list, max_length=6)
    expected_links: list[Link] | None = None
    clear_of: list[str] = Field(default_factory=list)
    focus: Focus | None = None
    paper_scene: bool = False
    action_claim: str | None = Field(default=None,min_length=3,max_length=400)
    retry_budget: int = Field(default=2, ge=0, le=4)

    @model_validator(mode="after")
    def validate_panel(self):
        if self.action_claim and self.op!="edit_scene":
            raise ValueError("a depicted action requires an edit_scene, not only an annotation")
        if (self.op == "new_scene") == bool(self.parent_panel_id):
            raise ValueError("new_scene forbids a parent; edits/reveals require one")
        if (self.op == "focus") != bool(self.focus):
            raise ValueError("focus requires a focus specification on the focus operation only")
        if self.paper_scene and (self.op != "new_scene" or self.layout or self.fallback_layout or self.anchors):
            raise ValueError("paper scene is an authored graphic canvas, not generated art or a layout")
        if any(not KEY.fullmatch(k) for k in self.anchors):
            raise ValueError("unsafe anchor name")
        if (self.layout or self.fallback_layout) and self.op != "new_scene":
            raise ValueError("a controlled layout must establish a scene")
        for key, spec in self.anchors.items():
            if isinstance(spec, str) and not spec.strip():
                raise ValueError(f"empty anchor query: {key}")
            if isinstance(spec, DerivedAnchor) and not all(isinstance(self.anchors.get(k), str) for k in (spec.of, spec.toward)):
                raise ValueError(f"{key}: derived anchors require two directly grounded inputs")
        return self


def resolve_dir(path: Path, id_: str, marker: str) -> Path:
    if not ID.fullmatch(id_) or not (path / id_ / marker).is_file():
        raise HTTPException(404, "unknown resource")
    return path / id_


def read(path):
    return json.loads(path.read_text())


def status_write(path, **changes):
    target = path / "status.json"
    atomic(target, {**read(target), **changes})


def worker():
    while True:
        session, job = tasks.get()
        try:
            status_write(job, state="running")
            run(ROOT, session, job, ComfyBackend(COMFY, PROFILE))
            status_write(job, state="accepted")
        except NeedsReview as exc:
            status_write(job, state="needs_review", error=str(exc))
        except Exception as exc:
            status_write(job, state="failed", error=f"{type(exc).__name__}: {exc}")
        finally:
            tasks.task_done()


@asynccontextmanager
async def lifespan(_):
    for path in (ROOT / "sessions").glob("*/panels/*/status.json"):
        state = read(path)["state"]
        if state == "queued":
            tasks.put((path.parents[2], path.parent))
        elif state == "running":
            status_write(path.parent, state="interrupted", error="service restarted; submit a new key/revision")
    threading.Thread(target=worker, daemon=True).start()
    yield


app = FastAPI(title="frames-renderer", version="2.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "alive"}


@app.get("/ready")
def ready():
    try:
        vision_model = Path.home() / "ai/models/vision/qwen3-vl-8b/model.safetensors.index.json"
        vision_python = Path(os.environ.get("STORY_VISION_PYTHON", Path.home() / "venvs/storyboard-vision/bin/python"))
        if not vision_model.is_file() or not vision_python.is_file():
            raise RuntimeError("local vision checkpoint or environment missing")
        ComfyBackend(COMFY, PROFILE).ready()
    except Exception as exc:
        raise HTTPException(503, f"ComfyUI: {exc}") from exc
    return {"status": "ready", "profile": PROFILE, "contract": "2.0"}


@app.post("/v2/assets", status_code=201)
def upload(image: UploadFile = File(...)):
    from io import BytesIO
    data = image.file.read(12_000_001)
    if len(data) > 12_000_000:
        raise HTTPException(413, "PNG exceeds 12 MB")
    try:
        with Image.open(BytesIO(data)) as im:
            if im.format != "PNG" or im.width * im.height > 12_000_000:
                raise ValueError("expected a bounded PNG")
            im.verify()
    except Exception as exc:
        raise HTTPException(422, "invalid reference PNG") from exc
    key = hashlib.sha256(data).hexdigest()
    p = ROOT / "references" / f"{key}.png"
    with submit_lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_bytes(data)
    return {"asset_id": key, "sha256": key}


@app.post("/v2/sessions", status_code=201)
def session(req: Session):
    for ref in req.style_ref_ids:
        if not re.fullmatch("[a-f0-9]{64}", ref) or not (ROOT / "references" / f"{ref}.png").exists():
            raise HTTPException(422, "unknown style reference")
    id_ = uuid.uuid4().hex
    p = ROOT / "sessions" / id_
    (p / "panels").mkdir(parents=True)
    atomic(p / "request.json", req.model_dump(mode="json"))
    return {"session_id": id_, "signature_hash": digest(req.visual_signature)}


@app.post("/v2/sessions/{sid}/panels", status_code=202)
def panel(sid: str, req: Panel):
    s = resolve_dir(ROOT / "sessions", sid, "request.json")
    sd = read(s / "request.json")
    body = req.model_dump(mode="json", by_alias=True)
    fingerprint = digest(body)
    for layout in filter(None, (req.layout, req.fallback_layout)):
        if ("asset" in layout) == ("layers" in layout):
            raise HTTPException(422, "layout requires asset or layers")
        layers = layout.get("layers", [{"asset": layout.get("asset")}])
        if not isinstance(layers, list) or not layers or any(not isinstance(x, dict) or x.get("asset") not in sd["assets"] for x in layers):
            raise HTTPException(422, "layout refers to unknown assets")
        if "asset" in layout:
            count = layout.get("count")
            if isinstance(count, str):
                count = sd["values"].get(count)
            if type(count) is not int or not 1 <= count <= 5:
                raise HTTPException(422, "controlled repeat count requires an integer 1..5")
    with submit_lock:
        for old in (s / "panels").glob("*/status.json"):
            data = read(old)
            if data["key"] == req.key:
                if data["fingerprint"] != fingerprint:
                    # Revalidate historical payloads before deciding a key
                    # conflicts. Additive schema defaults are not a revision.
                    try:
                        prior = Panel.model_validate(read(old.parent / "request.json")).model_dump(mode="json", by_alias=True)
                    except ValueError:
                        prior = None
                    if prior != body:
                        raise HTTPException(409, "idempotency key already used with different request")
                return data
        for ref in (req.parent_panel_id, req.revision_of):
            if ref:
                p = resolve_dir(s / "panels", ref, "status.json")
                if read(p / "request.json")["scene_id"] != req.scene_id:
                    raise HTTPException(409, "reference belongs to a different scene")
                if ref == req.parent_panel_id and read(p / "status.json")["state"] != "accepted":
                    raise HTTPException(409, "parent must be accepted")
        id_ = uuid.uuid4().hex
        p = s / "panels" / id_
        p.mkdir()
        url = f"/v2/sessions/{sid}/panels/{id_}"
        data = {"panel_id": id_, "key": req.key, "fingerprint": fingerprint, "state": "queued", "status_url": url}
        atomic(p / "request.json", body)
        atomic(p / "status.json", data)
        tasks.put((s, p))
        return data


@app.get("/v2/sessions/{sid}/panels/{pid}")
def status(sid: str, pid: str):
    s = resolve_dir(ROOT / "sessions", sid, "request.json")
    p = resolve_dir(s / "panels", pid, "status.json")
    d = read(p / "status.json")
    d["artifacts"] = {name: f"{d['status_url']}/artifacts/{name}" for name in
                      ("clean.png", "composed.png", "overlay.png", "review.json", "phone.png") if (p / name).is_file()}
    if (p / "review.json").exists():
        report = read(p / "review.json")
        d["summary"] = {k: report[k] for k in ("clean_sha256", "composed_sha256", "scene_root", "anchors") if k in report}
        for k in ("verified_facts","accepted_attempt"):
            if k in report:
                d["summary"][k]=report[k]
        d["attempt_artifacts"] = [
            {name: f"{d['status_url']}/attempts/{index}/{name}" for name in ("clean.png", "composed.png", "phone.png", "overlay.png")
             if (p / f"attempt-{index}" / name).is_file()}
            for index in range(len(report.get("attempts", [])))
        ]
    return d


@app.get("/v2/sessions/{sid}/panels/{pid}/artifacts/{name}")
def artifact(sid: str, pid: str, name: str):
    s = resolve_dir(ROOT / "sessions", sid, "request.json")
    p = resolve_dir(s / "panels", pid, "status.json")
    if name not in ("clean.png", "composed.png", "overlay.png", "review.json", "phone.png") or not (p / name).is_file():
        raise HTTPException(404, "unknown artifact")
    return FileResponse(p / name)


@app.get("/v2/sessions/{sid}/panels/{pid}/attempts/{index}/{name}")
def attempt_artifact(sid: str, pid: str, index: int, name: str):
    s = resolve_dir(ROOT / "sessions", sid, "request.json")
    p = resolve_dir(s / "panels", pid, "status.json")
    if not (0 <= index <= 4) or name not in ("clean.png", "composed.png", "overlay.png", "phone.png"):
        raise HTTPException(404, "unknown artifact")
    f = p / f"attempt-{index}" / name
    if not f.is_file():
        raise HTTPException(404, "unknown artifact")
    return FileResponse(f)
