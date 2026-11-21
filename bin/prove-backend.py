#!/usr/bin/env python3
"""Actual GPU reference edit using its immediately generated PNG."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path
from storyboard_renderer.backends.comfy import ComfyBackend
from storyboard_renderer.signature import art_only

profile=sys.argv[1] if len(sys.argv)>1 else "hidream"
label=sys.argv[2] if len(sys.argv)>2 else profile
out=Path.home()/"Videos/storyboard-renderer/comparison"/label
out.mkdir(parents=True,exist_ok=True)
backend=ComfyBackend("http://127.0.0.1:8188",profile)
signature=art_only((Path("examples/unit-price/signature.md")).read_text())
prompt=f"{signature}\nExactly one large red apple on a clean ivory paper background. One small green leaf. Blunt plum ink outline, expressive distinct shape, elegant editorial cutout, vertical poster composition. No lettering, no other fruit."
before=out/"first-cartoon.png"
after=out/"reference-edit.png"
one=backend.render(prompt,864,1536,43,before)
edit=f"{signature}\nEdit the provided illustration of a single red apple: change ONLY the fruit body to bright golden yellow. Keep the single green leaf, apple outline, stem, exact apple position and size, camera, background and ink style unchanged. No words or additional objects."
two=backend.render(edit,864,1536,44,after,before)
record={"profile":profile,"first":one,"edit":two,"source_sha256":hashlib.sha256(before.read_bytes()).hexdigest(),"edited_sha256":hashlib.sha256(after.read_bytes()).hexdigest()}
(out/"gpu-proof.json").write_text(json.dumps(record,indent=2))
print(f"GPU_PROOF_DONE {profile} {before} {after}",flush=True)
