# frames-renderer

## V2 standalone frame service

`./bin/start-frame-renderer` starts the v2 API on `127.0.0.1:8788`.
`POST /v2/sessions` accepts `story_context` and `visual_signature`, optionally
`canvas`, `style_ref_ids`, `assets`, `values` and `checks`. Use `POST /v2/assets`
with multipart `image` to store a style reference PNG. Submit panel work to
`POST /v2/sessions/{session_id}/panels` and poll its `status_url` until accepted,
rejected for `needs_review`, or failed. See `bin/demo-repair` for a real request.

Each continuation names its accepted `parent_panel_id`. The API rejects
cross-session references and reuses an identical submission key within a
session. Clean art, composition, overlay, phone preview and review are separate
artifacts; accepted status includes hashes. Visual checks are model
observations, not guarantees. Explicit controlled fallback can replace a
failed drawing without mixing lesson state between sessions. The frame HTTP
workflow has no audio or FFmpeg prerequisite.

The pinned original v1 worktree (`1cd7992`) is kept separately for rollback.
Audio, cue timing and the active encoder now live only in `video-renderer`.

Start ComfyUI with `bin/start-backend` if it is not already running.
The frame store defaults to `~/Videos/frames-renderer` and can be overridden
with `FRAME_STORE`. `GET /ready` checks local ComfyUI and Qwen availability.
`/docs` is the generated contract. `docs/OPERATIONS.md` and `docs/RESULTS.md`
are historical v1 records; follow this README for v2 startup.

On the workstation run `./bin/install-renderer` once for the isolated v2
environment. The historical Python namespace `storyboard_renderer` is retained
for proof utilities; the public distribution and checkout name are independent.

`fallback_layout` and `overlay_repairs` are author-approved alternatives: the
worker can choose them after rejection but cannot invent new numbers or
teaching claims. `focus` crops around an accepted semantic anchor and
transforms it into the new composition; the crop does not override a failed
composed review. A Qwen “accepted” icon can still have distracting details.
