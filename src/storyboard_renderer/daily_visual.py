"""Daily visual routes. Documentary assets are admitted only by a trusted rights catalog."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, ImageOps

from .compose import font_for
from .grounding import NeedsReview


def asset_root():
    return Path(os.getenv("DAILY_ASSET_CACHE", Path.home() / "ai/autonomous-daily/approved-assets"))


def subject_path(root, subject):
    key = hashlib.sha256(subject.encode()).hexdigest()
    return root / f"approved-{key}.json"


def approve_discovery(visual):
    if not visual.get("discovery"):
        return
    root = asset_root()
    target = subject_path(root, visual["subject"])
    with NamedTemporaryFile(mode="w", dir=root, delete=False) as pending:
        json.dump({"rights": visual["rights"], "phone_sha256": visual["phone_sha256"]}, pending)
    Path(pending.name).replace(target)


def label(draw, text, x, y, size, width):
    font = font_for(text, size)
    if draw.textlength(text, font=font) > width:
        raise NeedsReview(f"exact graphic label does not fit: {text}")
    draw.text((x, y), text, font=font, fill="#202c37")


def exact(data, size, target):
    w, h = size
    image = Image.new("RGB", size, "#faf6ed")
    draw = ImageDraw.Draw(image)
    operation = data.get("operation")
    if operation == "bars":
        rows, unit = data.get("rows"), data.get("unit")
        if not isinstance(rows, list) or not 2 <= len(rows) <= 5 or not isinstance(unit, str) or not unit:
            raise NeedsReview("bars need two to five labeled values and a unit")
        for row in rows:
            if (not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str) or not row[0]
                    or type(row[1]) not in (int, float) or not math.isfinite(row[1]) or not 0 <= row[1] <= 1e12):
                raise NeedsReview("invalid label or nonnegative bar value")
        if len({row[0] for row in rows}) != len(rows):
            raise NeedsReview("bar labels must distinguish the values")
        scale = max(value for _, value in rows)
        if not scale:
            raise NeedsReview("all values are zero; there is no positive bar scale")
        for i, (name, value) in enumerate(rows):
            y = round(h * (.18 + .12*i))
            label(draw, f"{name}: {value} {unit}", w*.08, y, round(w*.043), w*.84)
            if value:
                draw.rectangle((w*.08, y+h*.042, w*(.08+.84*value/scale), y+h*.069), fill="#126c83")
        proof = {"rows": rows, "unit": unit, "shared_max": scale}
    elif operation == "projection":
        vertices = data.get("vertices")
        if not isinstance(vertices, list) or not 3 <= len(vertices) <= 64:
            raise NeedsReview("projection requires one shared polygon")
        for point in vertices:
            if (not isinstance(point, list) or len(point) != 2
                    or not all(type(v) in (int, float) and math.isfinite(v) for v in point)
                    or not -175 <= point[0] <= 175 or not -80 <= point[1] <= 80):
                raise NeedsReview("projection coordinates outside the supported domain")
        if max(x for x, _ in vertices) - min(x for x, _ in vertices) >= 180:
            raise NeedsReview("antimeridian crossings require a split polygon")
        radians = [(math.radians(x), math.radians(y)) for x, y in vertices]
        projections = (
            ("Mercator", [(x, math.asinh(math.tan(y))) for x, y in radians]),
            ("Cylindrical equal-area", [(x, math.sin(y)) for x, y in radians]),
        )
        for i, (name, points) in enumerate(projections):
            y = h*(.15+.34*i)
            label(draw, name, w*.08, y, round(w*.044), w*.84)
            rect = (w*.08, y+h*.05, w*.92, y+h*.29)
            draw.rectangle(rect, outline="#516275", width=3)
            mapped = [(w*.5 + x*w*.13, y+h*.17 - v*h*.045) for x, v in points]
            if len(set((round(x*360/w), round(y*640/h)) for x, y in mapped)) < 3:
                raise NeedsReview("projected polygon is too small to distinguish at phone size")
            draw.polygon(mapped, fill="#126c83")
        proof = {"shared_vertices": vertices, "projections": dict(projections)}
    else:
        raise NeedsReview(f"unsupported exact visual operation: {operation!r}")
    image.save(target)
    return {"route": "exact", "operation": operation, "proof": proof}


def documentary(data, size, target):
    root = asset_root()
    catalog = root / "catalog.json"
    subject = data.get("subject")
    if not isinstance(subject, str):
        raise NeedsReview("authentic visual requires a documentary catalog subject")
    entry = json.loads(catalog.read_text()).get(subject) if catalog.exists() else None
    previous = subject_path(root, subject)
    if not entry and previous.exists():
        entry = json.loads(previous.read_text())
    discovery = None
    route = "reuse"
    if not entry and os.getenv("DAILY_IMAGE_DISCOVERY"):
        root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=root) as folder:
            try:
                process = subprocess.run([os.environ["DAILY_IMAGE_DISCOVERY"], subject, folder],
                                         check=True, timeout=60, capture_output=True, text=True)
                discovery = json.loads(process.stdout)
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                raise NeedsReview("documentary search did not return a verifiable item") from error
            target.with_name("image-discovery.json").write_text(json.dumps(discovery))
            if "error" in discovery:
                raise NeedsReview(f"documentary search: {discovery['error']}")
            image_hash = discovery["rights"]["sha256"]
            if re.fullmatch(r"[a-f0-9]{64}", image_hash) is None:
                raise NeedsReview("broker did not return a valid original hash")
            candidate = Path(folder) / image_hash
            if hashlib.sha256(candidate.read_bytes()).hexdigest() != image_hash:
                raise NeedsReview("retrieved original differs from provider receipt")
            candidate.replace(root / image_hash)
        entry = discovery
        route = "retrieved"
    if not entry:
        raise NeedsReview(f"no cleared original for authentic visual: {subject}")
    rights = entry.get("rights", {})
    required = ("page", "file", "creator", "credit", "basis", "rights_page", "checked", "sha256")
    if (rights.get("commercial_editorial") is not True or rights.get("resize") is not True
            or not all(isinstance(rights.get(k), str) and rights[k] for k in required)
            or any(urlsplit(rights[k]).scheme != "https" for k in ("page", "file", "rights_page"))
            or len(rights["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in rights["sha256"])):
        raise NeedsReview("documentary original lacks verifiable editorial rights and attribution")
    original = root / rights["sha256"]
    if not original.exists() and os.getenv("DAILY_ASSET_FETCH_PROGRAM"):
        # Rights approval precedes acquisition. The broker writes only its output
        # file and cannot select a different original.
        with NamedTemporaryFile(dir=root) as pending:
            try:
                subprocess.run([os.environ["DAILY_ASSET_FETCH_PROGRAM"], rights["file"], pending.name],
                               check=True, timeout=35, capture_output=True)
                if hashlib.sha256(Path(pending.name).read_bytes()).hexdigest() != rights["sha256"]:
                    raise NeedsReview("retrieved original differs from the rights record")
                os.link(pending.name, original)
                route = "retrieved"
            except FileExistsError:
                pass
            except (OSError, subprocess.SubprocessError) as error:
                raise NeedsReview(f"cleared documentary original is inaccessible: {subject}") from error
    if not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest() != rights["sha256"]:
        raise NeedsReview("cleared original absent or its hash changed")
    with Image.open(original) as decoded:
        if (decoded.format not in ("JPEG", "PNG") or decoded.width * decoded.height > 30_000_000
                or min(decoded.size) < 480):
            raise NeedsReview("original dimensions or format unsuitable")
        oriented = ImageOps.exif_transpose(decoded)
        if oriented.convert("RGBA").getchannel("A").getextrema()[0] != 255:
            raise NeedsReview("documentary photograph contains transparency")
        w, h = size
        image = Image.new("RGB", size, "#faf6ed")
        photo = ImageOps.contain(oriented.convert("RGB"), (round(w*.90), round(h*.55)))
        if min(photo.width*360/w, photo.height*640/h) < 110:
            raise NeedsReview("documentary photograph is too small in portrait composition")
        placement = ((w-photo.width)//2, round(h*.18))
        ImageOps.contain(oriented.convert("RGB"), (900, 900)).save(target.with_name("documentary-original-preview.png"))
        image.paste(photo, placement)
        image.save(target)
        return {"route": route, "subject": subject, "rights": rights, "placement": [*placement, *photo.size],
                "discovery": discovery,
                "decoded_dimensions": list(decoded.size), "transform": "fit without crop; EXIF orientation applied"}
