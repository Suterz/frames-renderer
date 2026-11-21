"""Panel execution, review and bounded repair; no video or narration dependency."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from .compose import compose, controlled_scene, layered_scene, make_cutout, point_of
from .grounding import NeedsReview, derive_edge, resolve
from .schema import Overlay
from .signature import art_only

LEASE = Path(os.environ.get("RENDER_GPU_LEASE", Path.home() / "ai/storyboard-build/v2/gpu.lock"))


def atomic(path, obj):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj, indent=2))
    temp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def evaluate(queries):
    worker = Path(__file__).with_name("multi_review.py")
    python = os.environ.get("STORY_VISION_PYTHON", str(Path.home() / "venvs/storyboard-vision/bin/python"))
    try:
        proc = subprocess.run([python, str(worker)], input=json.dumps(queries), text=True,
                              capture_output=True, check=True, timeout=150)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"vision worker failed: {exc.stderr[-3000:]}") from exc
    answers = json.loads(proc.stdout.splitlines()[-1])
    return [{"query": q, "raw": a} for q, a in zip(queries, answers, strict=True)]


def parsed(record):
    text = record["raw"]
    obj = json.loads(text[text.index("{"):text.rindex("}") + 1])
    if not isinstance(obj, dict):
        raise ValueError("expected structured observation")
    record["observed"] = obj
    return obj


def simple_query(images, question):
    return {"images": images, "prompt": f"{question} Return only JSON with a concise string key \"answer\" and a string key \"reason\". Say unknown if not visible."}


def check_answers(records, specs):
    failures = []
    for rec, spec in zip(records, specs, strict=True):
        got = parsed(rec).get("answer")
        rec["expected"] = spec["expected"]
        if not isinstance(got, str) or got.strip().casefold().rstrip(".") != spec["expected"].strip().casefold().rstrip("."):
            failures.append(f"{spec['question']} expected {spec['expected']!r}; observed {got!r}")
    return failures


def geometry(req, anchors, size, alpha):
    links = [(o["from"], o["to"]) for o in req["overlays"] if o["type"] == "arrow"]
    expected = req["expected_links"]
    if expected is not None and sorted((str(a), str(b)) for a, b in links) != sorted((x["from"], x["to"]) for x in expected):
        raise NeedsReview("rendered directed connection specification differs from the expected topology")
    evidence = []
    for a, b in links:
        start, tip = point_of(a, anchors, size), point_of(b, anchors, size)
        for label, point in [("source", start), ("tip", tip)]:
            x, y = point
            if not (0 <= x < size[0] and 0 <= y < size[1]) or alpha.getpixel((x, y)) == 0:
                raise NeedsReview(f"arrow {label} is outside rasterized arrow layer")
        obstacles = [anchors[k]["box"] for k in req["clear_of"] if k not in (a, b)]
        for box in obstacles:
            x0, y0, x1, y1 = box
            margin = round(size[0] * .01)
            if any(x0-margin <= start[0] + (tip[0]-start[0])*i/400 <= x1+margin and
                   y0-margin <= start[1] + (tip[1]-start[1])*i/400 <= y1+margin for i in range(401)):
                raise NeedsReview(f"arrow {a} → {b} crosses a protected object")
        evidence.append({"from": a, "to": b, "source": start, "tip": tip, "tip_alpha": alpha.getpixel(tuple(tip))})
    return evidence


def run(root, session, job, backend):
    s = json.loads((session / "request.json").read_text())
    req = json.loads((job / "request.json").read_text())
    size = tuple(s["canvas"])
    refs = [root / "references" / f"{key}.png" for key in s["style_ref_ids"]]
    parent = session / "panels" / req["parent_panel_id"] if req["parent_panel_id"] else None
    previous = json.loads((parent / "review.json").read_text()) if parent else None
    ref = parent / "clean.png" if parent else None
    scene_root = previous["scene_root"] if previous else job.name
    report = {"scene_root": scene_root, "parent": req["parent_panel_id"], "attempts": [],
              "legacy_review": s["legacy_input"], "asset_records": {},
              "clean_parent_sha256": sha(ref) if ref else None}
    art = art_only(s["visual_signature"])
    layout = req["layout"]
    feedback = ""
    LEASE.parent.mkdir(parents=True, exist_ok=True)
    with LEASE.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for trial in range(1 + req["retry_budget"]):
            attempt = job / f"attempt-{trial}"
            attempt.mkdir()
            proof = {"attempt": trial, "feedback": feedback}
            report["attempts"].append(proof)
            clean, composed = attempt / "clean.png", attempt / "composed.png"
            overlay, phone = attempt / "overlay.png", attempt / "phone.png"
            stage = "art"
            try:
                if layout:
                    keys = [layout["asset"]] if "asset" in layout else [row["asset"] for row in layout["layers"]]
                    sprites, positions = {}, {}
                    for key in dict.fromkeys(keys):
                        asset = s["assets"][key]
                        fingerprint = digest([art, asset, backend.profile, "cutout-v2.1"])
                        cache = session / "cutouts" / fingerprint
                        cache.mkdir(parents=True, exist_ok=True)
                        cut, record_path = cache / "cut.png", cache / "record.json"
                        reused = record_path.is_file() and cut.is_file()
                        if not reused:
                            raw = cache / "source.png"
                            generated = backend.render(
                                f"{art}\n{asset['visual']}. One complete isolated object, plain white background, no text or shadow.",
                                768, 768, asset["seed"], raw)
                            sprite = make_cutout(raw, cut)
                            local = {}
                            if any(isinstance(v, str) for v in asset["anchors"].values()):
                                backend.free()
                            for name, spec in asset["anchors"].items():
                                if isinstance(spec, str):
                                    a = resolve(cut, f"{key}.{name}", spec, cache / "evidence")
                                    x, y = a["point"]
                                    if not (0 <= x < sprite.width and 0 <= y < sprite.height and sprite.getpixel((x, y))[3] >= 128):
                                        raise NeedsReview(f"{key}.{name}: anchor is not on visible cutout")
                                    local[name] = [x / sprite.width, y / sprite.height]
                                else:
                                    local[name] = spec
                            atomic(record_path, {"positions": local, "cutout_sha256": sha(cut), "backend": generated})
                        details = json.loads(record_path.read_text())
                        if details["cutout_sha256"] != sha(cut):
                            raise RuntimeError("cutout cache hash mismatch")
                        report["asset_records"][key] = {**details, "reused": reused}
                        with Image.open(cut) as sprite:
                            sprites[key] = sprite.convert("RGBA")
                        positions[key] = details["positions"]
                    if "asset" in layout:
                        count = layout["count"]
                        if isinstance(count, str):
                            count = s["values"][count]
                        anchors = controlled_scene(size, sprites[layout["asset"]], count, clean)
                    else:
                        anchors = layered_scene(size, sprites, layout["layers"], positions, clean)
                elif req["op"] == "overlay_only":
                    shutil.copyfile(ref, clean)
                    anchors = dict(previous["anchors"])
                else:
                    prompt = (f"{art}\nStory context: {s['story_context']}\n{req['instruction']}\n"
                              f"Change: {req['change']}. Preserve: {req['keep']}. No written words, numbers, or annotations.")
                    if feedback:
                        prompt += f"\nCorrect these specific defects: {feedback[:700]}"
                    native = (864, 1536) if backend.profile == "flux" else (1440, 2560)
                    proof["backend"] = backend.render(prompt, *native, req["seed"] + trial, clean, ref)
                    anchors = {}
                stage = "clean_review"
                images = [("Approved style reference", str(p)) for p in refs]
                if ref:
                    images.append(("Previous accepted clean image", str(ref)))
                    if scene_root != parent.name:
                        images.append(("Scene root", str(session / "panels" / scene_root / "clean.png")))
                images.append(("New candidate to judge", str(clean)))
                checks = req["clean_checks"]
                queries = [simple_query([images[-1]], c["question"]) for c in checks]
                rubric = not s["legacy_input"] and req["op"] != "overlay_only"
                if rubric:
                    queries.append({"images": images, "prompt":
                        f"Teaching objective: {req['objective']}\nImage instruction: "
                        f"{req['instruction'] if not (layout and req['fallback_layout'] == layout) else 'Judge the exact controlled layout by the teaching objective.'}\n"
                        f"Style: {art}\nRequested change: {req['change']}; unchanged: {req['keep']}.\n"
                        "Judge only the labeled new candidate. Check required subject and actions, fake text/arrows, "
                        "distinctness, palette/outlines/style, focal point and space for graphics. On an edit, check the change, identity, pose, viewpoint and props. "
                        "Do not penalize absence of text to be drawn later. Return only JSON: "
                        '{"observations":"specific visible evidence","defects":[{"kind":"style|continuity|subject|spurious|layout","detail":"specific visible teaching defect"}]}. '
                        "Use an empty defects list if no material defect."})
                if queries:
                    backend.free()
                    proof["pass_a"] = records = evaluate(queries)
                    failures = check_answers(records[:len(checks)], checks)
                    if rubric:
                        defects = parsed(records[-1]).get("defects")
                        if not isinstance(defects, list):
                            raise ValueError("missing defects list")
                        failures.extend(d["detail"] for d in defects)
                    if failures:
                        raise NeedsReview("; ".join(failures))
                stage = "grounding"
                if req["anchors"]:
                    backend.free()
                    w, h = Image.open(clean).size
                    for name, spec in req["anchors"].items():
                        if isinstance(spec, str):
                            found = resolve(clean, name, spec, attempt / "grounding")
                            x, y = found["point"]
                            if not (0 <= x < w and 0 <= y < h):
                                raise NeedsReview(f"{name}: location outside clean image")
                            found["source_point"], found["source_hash"] = found["point"], sha(clean)
                            found["point"] = [round(x * size[0] / w), round(y * size[1] / h)]
                            found["box"] = [round(v * size[i % 2] / (w, h)[i % 2]) for i, v in enumerate(found["box"])]
                            anchors[name] = found
                    for name, spec in req["anchors"].items():
                        if isinstance(spec, dict):
                            anchors[name] = derive_edge(anchors[spec["of"]], anchors[spec["toward"]], spec["of"], spec["toward"])
                stage = "composition"
                overlays = [Overlay.model_validate(o) for o in req["overlays"]]
                compose(clean, overlays, "", s["values"], anchors, size, composed, overlay)
                with Image.open(overlay) as rgba:
                    proof["geometry"] = geometry(req, anchors, size, rgba.getchannel("A"))
                with Image.open(composed) as img:
                    img.resize((360, 640), Image.Resampling.LANCZOS).save(phone)
                stage = "composed_review"
                observation_specs = req["composed_checks"]
                if observation_specs:
                    backend.free()
                    queries = [simple_query([("Composed image", str(p))], c["question"]) for p in (composed, phone) for c in observation_specs]
                    proof["pass_b"] = records = evaluate(queries)
                    failures = check_answers(records, observation_specs * 2)
                    if failures:
                        raise NeedsReview("; ".join(failures))
                report.update(anchors=anchors, clean_sha256=sha(clean), composed_sha256=sha(composed),
                              accepted_attempt=trial)
                for path in (clean, composed, overlay, phone):
                    shutil.copyfile(path, job / path.name)
                atomic(job / "review.json", report)
                return report
            except (NeedsReview, ValueError, KeyError) as exc:
                feedback = str(exc)
                proof.update(stage=stage, defect=feedback)
                for path in (clean, composed, overlay, phone):
                    if path.exists():
                        shutil.copyfile(path, job / path.name)
                atomic(job / "review.json", report)
                if req["fallback_layout"] and not layout:
                    layout = req["fallback_layout"]
                    continue
                if req["op"] == "overlay_only" and not req["anchors"]:
                    break
            finally:
                backend.free()
    raise NeedsReview(feedback or "no candidate passed")
