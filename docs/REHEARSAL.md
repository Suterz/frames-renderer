# Isolated FLUX installation

Test target: Ubuntu 24.04 x86-64, Python 3.12.3, CUDA-capable NVIDIA driver.
The selected ComfyUI revision is `a277b5bf213e8a44fa34817b7770b54f86ef4cea`
(`v0.46.0`); the FLUX paths need no third-party ComfyUI nodes. Install Ubuntu
Noto Sans and DejaVu fonts and make `uv` and an `hf` CLI available. Big model
files stay under an external root. For a user-space install:

```sh
./bin/install-locked "$ROOT"
python3 -B bin/model-assets.py locks/models.json "$ROOT/models" --download --hf "$HF_BIN"
python3 -B bin/model-assets.py locks/models.json "$ROOT/models"
./bin/start-rehearsal-comfy "$ROOT"
```

In another terminal:

```sh
FRAME_PORT=8892 FRAME_STORE="$ROOT/frame-store" \
  FRAME_PYTHON="$ROOT/venvs/frames-renderer/bin/python" \
  STORY_COMFY_URL=http://127.0.0.1:8193 \
  STORY_VISION_PYTHON="$ROOT/venvs/storyboard-vision/bin/python" \
  STORY_VISION_MODEL="$ROOT/models/vision/qwen3-vl-8b" \
  ./bin/start-frame-renderer
curl -fsS http://127.0.0.1:8892/ready
```

The actual request is at `/openapi.json`; create a session at `POST /v2/sessions`,
then submit panels to `POST /v2/sessions/{sid}/panels`. The response supplies the
status and artifact URLs. The companion video rehearsal is a real new-scene,
clean-reference edit and overlay sequence.

`workflows/comfy/flux2-*.api.json` are static API snapshots. The adapter
constructs the actual graph with prompt, size, seed, and uploaded reference and
records that graph and hash per attempt. `new_scene` uses FLUX at 864×1536;
cutouts reuse the generator workflow at 768×768 before matte extraction,
session caching and placement. `edit_scene` loads the accepted parent's
**clean** image, adds its latent as the FLUX reference, and gets a separate
clean-review check. `overlay_only` copies the clean art. Session `style_ref_ids`
refer to previously uploaded PNGs used as review references.

Grounding and clean/composed review prompts live in `frame_engine.py` and the
vision workers. ComfyUI unloads weights before local Qwen-VL review. Pillow
composes labels, counts, scale marks and arrows; accepted artifacts and phone
checks are tied to the candidate. Failed requests keep the candidate trail and
return `needs_review` for ambiguous teaching evidence. Keep a shared
`RENDER_GPU_LEASE` when running alongside other local pipeline processes.
