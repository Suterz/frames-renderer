# Operating the local renderer

All paths and commands below are on **zelio-server**, not the OpenCode laptop. There are two localhost processes and one detached CPU grounding helper per unique generated image. Do not expose the development endpoints to the internet.

## Setup

- The workstation already has the exact external components recorded in
  `docs/COMPONENTS.json`. To reproduce on a fresh compatible Ubuntu/4090 host,
  with `uv` at `~/.local/bin/uv`, run these **one-time user-space installers**
  from the repo checkout. They only write to `~/ai`, `~/venvs` and
  `~/.cache`, not the project Git repository, driver or system Python:

  ```bash
  cd ~/git/storyboard-renderer
  ./bin/install-media
  ./bin/install-backend
  ./bin/install-vision
  ./bin/install-voice
  ./bin/install-renderer
  ```

  The full HiDream weights are downloaded for the documented quality comparison;
  normal selected production uses the FLUX.2 4B files. If an installation is
  interrupted, inspect its process/log and existing outputs before resuming.
  Check current model licenses and exact file hashes before any commercial
  deployment.

- External backend and weights: `~/ai/ComfyUI`, `~/ai/models`; renderer source: `~/git/storyboard-renderer`.
- Separate environments: `~/venvs/comfy-storyboard`, `~/venvs/storyboard-renderer`, `~/venvs/storyboard-vision`, `~/venvs/storyboard-voice`.
- User-space encoder/decoder: `~/ai/tools/media/bin/ffmpeg` and `ffprobe`.
- Voice ONNX: `~/ai/voices/ljspeech-high/ljspeech.onnx`.
- The profile is `STORY_PROFILE=flux` or `STORY_PROFILE=hidream`. Backend-specific checkpoint names and graph nodes stay in `backends/comfy.py`. One server process, one serial worker. Changing profile means restarting the renderer, not editing a storyboard.
- `workflows/comfy/*.api.json` are versioned, API-format snapshots for both
  generation and one-reference editing. The adapter injects actual prompts,
  seeds, native dimensions and uploaded reference filenames at runtime; each
  job manifest saves the exact submitted graph and backend prompt ID. The
  original Comfy templates under `workflows/comfy/upstream-*.json` are UI
  workflow references, not directly submitted by the HTTP adapter.

Run in two terminals or detached named tmux sessions:

```bash
cd ~/git/storyboard-renderer
./bin/start-backend
STORY_PROFILE=flux ./bin/start-renderer
curl -fsS http://127.0.0.1:8787/ready
```

`/ready` checks process dependencies. Actual image quality and semantic correctness require review.

## Submitting

```bash
cd ~/git/storyboard-renderer
ID=$(./bin/submit-example examples/unit-price)
curl -sS "http://127.0.0.1:8787/renders/$ID"
curl -f "http://127.0.0.1:8787/renders/$ID/video" -o "$HOME/Videos/unit-price.mp4"
```

The helper loads `signature.md` into the JSON request. With already-expanded JSON use multipart:

```bash
curl -sS http://127.0.0.1:8787/renders \
  -F 'story=<request.json' -F 'audio=@narration.wav;type=audio/wav'
```

The HTTP client can exit immediately; files under `~/Videos/storyboard-renderer/jobs/<id>/` hold its status, source illustrations, grounding diagnostics, overlays, composed panels, contact sheet, submitted audio, manifest and completed video.

### Operations and grounding

`new_scene` generates artwork or composes a controlled layout from illustrated cutouts. `overlay_only` copies the clean PNG and draws only declared layers. `edit_scene` uploads the preceding clean PNG as an actual reference; the clean file never includes a caption or arrow. On edits, declared visual anchors are grounded again. `anchors` map semantic names to descriptions. The model returns normalized 0–1000 coordinates on the source or crop; the renderer saves the observation and conversion. Failed crop agreement or unresolvable targets yield `needs_review` with diagnostics rather than an arbitrary arrow.

Controlled layouts instantiate individual illustrated cutouts with known anchor transforms. They are appropriate for exact counts and diagrams. Qwen3-VL is a local short-lived grounding helper and runs sequentially with the image generator; it is **not** an independent guarantee of semantic correctness. If exact targets are ambiguous, switch to a controlled layout or request review.

For different cutouts, a `new_scene` may use `layout.layers` rather than a
repeated `layout.asset/count`. For example, the following **request fragment**
uses no hand-entered final-canvas arrow coordinates:

```json
{
  "assets": {
    "apple": {"kind":"generated_cutout","visual":"one red apple on flat white"},
    "basket": {
      "kind":"generated_cutout",
      "visual":"one open wicker basket with visible dark opening on flat white",
      "anchors":{"opening":"a point inside the visible dark basket opening"}
    }
  },
  "panels": [{
    "id":"P01","scene":"fruit","op":"new_scene","cue":"start",
    "visual":"Place the apple beside the basket","refs":[],
    "layout":{"layers":[
      {"id":"apple_2","asset":"apple","center":[0.23,0.5],"width":0.2},
      {"id":"basket","asset":"basket","center":[0.72,0.5],"width":0.28}
    ]},
    "overlays":[{"type":"arrow","from":"apple_2.center","to":"basket.opening"}]
  }]
}
```

The local vision helper resolves `basket.opening` **once on the actual cutout**,
stores source hash/query/point, then the layer transform maps it when the basket
is moved or resized. A caller may alternatively supply a normalized asset-local
point `[0.5,0.2]` after checking that reusable cutout; this is a definition
relative to one asset, not a fresh pixel annotation for each panel. A missing
asset, clipped layer, unauthorized overlap or ambiguous part returns a clear
failure/`needs_review`. Layer-list order is compositing order. The example
`examples/unit-price` uses the simpler row to instantiate exactly three
oranges; generated `new_scene` shots use Qwen on the full illustration.

Timeline: cumulative authored cue milliseconds become integer frame indices exactly once. Last frame and audio end are checked against the strict `<45s` rule. Audio is uploaded; caller machine paths are never used. Narration is input, not a server TTS call.

The encoder applies a conservative `STORY_AUDIO_GAIN=0.85` by default before
AAC muxing to leave headroom for near-full-scale TTS recordings; the exact
gain appears in each manifest. It does not modify cue timestamps or shorten
the narration.

To reuse validated clean art without overwriting an existing job, supply `reuse_from` as a multipart field containing its prior job ID. A changed signature, seed, instruction, settings or reference hash invalidates reuse. Timing changes reuse all clean art but recompose and encode.

## Limits

- Renderer assumes one locally hosted inference backend and one GPU job at a time.
- Readable captions, labels, numbers and arrows are drawn by the renderer.
- Image placement is machine-proposed, constrained and logged; visual review remains essential for unfamiliar or occluded objects.
- A locally generated voice can decode and meet a timeline without proving it sounds pleasant. Final listening belongs to the owner.
- No runtime planner, cloud calls, web frontend, database, public binding, automatic publication or authentication.
