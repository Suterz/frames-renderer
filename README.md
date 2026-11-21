# storyboard-renderer
Renders structured storyboards into narrated MP4 videos using an external illustration service.

## First working release

The author supplies a prepared educational storyboard, reusable visual signature,
WAV narration, and speech-synchronized cue times. A local ComfyUI instance owns GPU
illustration and real image-conditioned editing. This server owns ordered panels,
scene continuity, local Qwen3-VL semantic placement (or exact controlled layout),
readable graphics, captions, audio, MP4 encoding, and retrieval.

On `zelio-server`, after installing the external models and isolated environments
in `~/ai` and `~/venvs`:

```bash
cd ~/git/storyboard-renderer
./bin/start-backend                       # terminal 1, 127.0.0.1:8188
./bin/start-renderer                      # terminal 2, 127.0.0.1:8787
curl -fsS http://127.0.0.1:8787/ready
ID=$(./bin/submit-example examples/unit-price)
curl -sS "http://127.0.0.1:8787/renders/$ID"
curl -f "http://127.0.0.1:8787/renders/$ID/video" -o "$HOME/Videos/unit-price.mp4"
```

The submission helper reads `signature.md` into the actual multipart JSON upload;
the audio is uploaded, not referenced through a caller-local filename. A CLI
client can disconnect immediately after POST; status and artifacts are durable.
Use `./bin/submit-example examples/signal-flow` for a different subject using
the same server. An optional second argument is a prior job ID to reuse matching
clean artwork and anchors on revision.
`./bin/submit-example examples/fruit-route` demonstrates a third, shorter
controlled-layout request with two different GPU-generated cutouts and a named
basket-opening anchor grounded once on the generated asset.

The primary demo includes real GPU-generated portrait art, a semantic tag-to-bag
arrow without authored pixel coordinates, a true reference-conditioned expression
edit, three independently composed copies of a GPU-generated fruit cutout, exact
$6 ÷ 3 = $2 arithmetic, and a 25–27-second vertical H.264/AAC export. The second
example explains a button/controller/lamp path, including a lamp-state edit.

See [operations](docs/OPERATIONS.md) for the request contract, backend and
operating details, and [assets and licensing](docs/ASSETS.md) for the commercial-use
provenance. The completed MP4, clean PNGs, placement evidence, contact sheet and
manifest live in `~/Videos/storyboard-renderer/jobs/<id>/`, outside Git.

**Limits:** Storyboards and facts are approved upstream; local vision grounding
is a fallible proposal, so unresolved objects cause `needs_review`. A user must
review semantics and listen to narration before publication. No paid service,
runtime story-writing agent, GitHub access, Instagram account, database or
always-on TTS server is used.
