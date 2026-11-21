from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw


class NeedsReview(RuntimeError):
    pass


def inspect_relationship(image: Path, question: str, expected: str) -> dict:
    python = os.environ.get("STORY_VISION_PYTHON", str(Path.home() / "venvs/storyboard-vision/bin/python"))
    module = Path(__file__).with_name("review_worker.py")
    started=time.monotonic()
    try:
        result=subprocess.run([python,str(module),str(image),question],text=True,capture_output=True,timeout=240)
    except subprocess.TimeoutExpired as exc:
        raise NeedsReview("local relationship review timed out") from exc
    if result.returncode:
        raise NeedsReview(f"local relationship review failed: {result.stderr[-700:]}")
    text=result.stdout
    a,b=text.find("{"),text.rfind("}")
    try:
        answer=json.loads(text[a:b+1])
        if not isinstance(answer["answer"],str):raise TypeError
    except (ValueError,TypeError,KeyError) as exc:
        raise NeedsReview(f"malformed local relationship answer: {text[-300:]}") from exc
    verdict={"question":question,"expected":expected,"observed":answer["answer"],"reason":answer.get("reason",""),
             "seconds":round(time.monotonic()-started,3),
             "method":"local Qwen visual assertion; not independent proof"}
    if answer["answer"].strip().lower()!=expected.strip().lower():
        raise NeedsReview(f"visual assertion failed: expected {expected!r}, got {answer['answer']!r}: {answer.get('reason','')}")
    return verdict


def _parse_response(text: str) -> dict:
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise NeedsReview("local vision model did not return JSON")
    try:
        obj = json.loads(text[a:b+1])
        point = obj["point_2d"]
        box = obj["bbox_2d"]
        if len(point) != 2 or len(box) != 4 or any(not isinstance(v, (int, float)) or v < 0 or v > 1000 for v in point+box):
            raise ValueError("malformed coordinates")
        if box[0] >= box[2] or box[1] >= box[3] or not (box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]):
            raise ValueError("point outside target box")
        if obj.get("visible") is not True:
            raise NeedsReview(f"target not visibly resolved: {obj.get('reason', 'unspecified')}")
        return obj
    except (KeyError, ValueError, TypeError) as exc:
        raise NeedsReview(f"invalid grounding response: {str(exc)}") from exc


def _ask(image: Path, description: str) -> tuple[dict, str, float]:
    python = os.environ.get("STORY_VISION_PYTHON", str(Path.home() / "venvs/storyboard-vision/bin/python"))
    module = Path(__file__).with_name("vision_worker.py")
    started=time.monotonic()
    try:
        result = subprocess.run([python, str(module), str(image), description], text=True, capture_output=True, timeout=240)
    except subprocess.TimeoutExpired as exc:
        raise NeedsReview("local grounding timed out") from exc
    if result.returncode != 0:
        raise NeedsReview(f"local grounding error: {result.stderr[-1200:]}")
    return _parse_response(result.stdout), result.stdout, round(time.monotonic()-started,3)


def resolve(image: Path, name: str, description: str, evidence_dir: Path, *, verify: bool = True) -> dict:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    answer, raw, whole_seconds = _ask(image, description)
    with Image.open(image) as source:
        w, h = source.size
        point = (round(answer["point_2d"][0]*w/1000), round(answer["point_2d"][1]*h/1000))
        box = tuple(round(n*d/1000) for n, d in zip(answer["bbox_2d"], (w,h,w,h)))
        if verify:
            # A second observation of an independent crop tests coordinate mapping
            # and disambiguates a small target from its parent object.
            margin = max(40, round(max(box[2]-box[0],box[3]-box[1])*.65))
            region = (max(0,box[0]-margin), max(0,box[1]-margin), min(w,box[2]+margin), min(h,box[3]+margin))
            crop_path = evidence_dir / f"{name.replace('.','_')}_crop.png"
            source.crop(region).save(crop_path)
            alternate, alt_raw, crop_seconds = _ask(crop_path, description)
            cw,ch = region[2]-region[0], region[3]-region[1]
            second = (region[0]+round(alternate["point_2d"][0]*cw/1000),region[1]+round(alternate["point_2d"][1]*ch/1000))
            # Same model is not independent semantic verification; agreement is only a sanity check.
            if abs(second[0]-point[0]) > max(22, w*.045) or abs(second[1]-point[1]) > max(22,h*.045):
                raise NeedsReview(f"{name}: crop and whole-image points disagree {point} vs {second}")
        else:
            region, alternate, alt_raw, second, crop_seconds = None, None, None, None, 0
        preview = source.convert("RGB")
        draw = ImageDraw.Draw(preview)
        draw.rectangle(box, outline="#FF00BB", width=max(3,w//200))
        r = max(9,w//65)
        draw.ellipse((point[0]-r,point[1]-r,point[0]+r,point[1]+r), outline="#FFCC00", width=5)
        preview.save(evidence_dir / f"{name.replace('.','_')}_location.jpg", quality=95)
    return {"point":point, "box":box, "description":description, "method":"qwen3-vl-local",
            "seconds":round(whole_seconds+crop_seconds,3),
            "raw":raw, "crop":region, "crop_raw":alt_raw, "crop_point":second,
            "verified_by":"crop agreement only; semantic accuracy requires visual review"}


def derive_edge(source:dict, target:dict, source_key:str, target_key:str)->dict:
    x0,y0,x1,y1=source["box"]
    cx,cy=(x0+x1)/2,(y0+y1)/2
    tx,ty=target["point"]
    dx,dy=tx-cx,ty-cy
    if abs(dx)+abs(dy)<1:raise NeedsReview("derived anchor target coincides with source")
    t=min((x1-cx)/dx if dx>0 else (x0-cx)/dx if dx<0 else float("inf"),
          (y1-cy)/dy if dy>0 else (y0-cy)/dy if dy<0 else float("inf"))
    point=(round(cx+t*dx),round(cy+t*dy))
    return {"point":point,"box":source["box"],"method":"derived geometry: edge_toward",
            "source":source_key,"target":target_key,"source_hash":source.get("source_hash")}
