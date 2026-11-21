# First-release evidence and review boundaries

This document distinguishes automated checks, OpenCode image inspection, and the
owner's pending **listening** review. Raw artifacts and job manifests are under
`~/Videos/storyboard-renderer/jobs/` on `zelio-server`. The desktop progress
gallery is on **the XPS laptop**, not the GPU workstation.

## Selected local illustrator

- **FLUX.2 [klein] 4B BF16** in ComfyUI is the default renderer profile.
- **HiDream-O1-Image Full BF16** was actually generated and reference-edited on
  the RTX 4090. The first matched unit-price opening omitted the shopkeeper
  and depicted four decorative fruits. Its genuine edit could not create the
  requested facial change. A bounded correction added the character but wrote
  `WITHOUT FRUIT` on the bag, fabricated tag text and baked in arrows.
  These are educational accuracy failures; a complete HiDream episode was
  **not** produced or represented as a comparable finished sequence.
- FLUX's initial apple scene and yellow-apple conditioned edit were cleaner
  and better preserved the subject. The successful narrated FLUX unit-price
  and different signal-flow sequences are the actual sequence-level evidence.
  HiDream could be revisited for a different editorial niche. Speed was
  measured separately, not used to disqualify quality.

| Level | What was tested | Evidence and failure/correction |
| --- | --- | --- |
| 1 One object | Two independently generated apples left and right | Local Qwen located both without hand-authored pixels; direct sampling at each marker found red fruit-body pixels and images were inspected. |
| 2 Distinct objects | Apple→basket; reversed arrangement | Semantic direction reversed correctly with the composition. The initial arrow touched the basket rim, **not its opening**; whole-object success must not be called a successful part-level pointing test. |
| 3 Similar objects/parts | Apple, pear distractor and basket; absent knot query; new second seed | First opening arrowhead landed inside the basket but its path crossed an occluding pear—**whole path not approved**. A nonexistent purple price-tag knot was declined. On a new seed/composition, pear sat below the apple-to-opening segment, red source pixel was verified, detected pear box did not intersect the segment, and the arrowhead visibly landed inside the opening at phone size. Both attempts are preserved in the gallery. |
| 4 Continuity | Two real uploaded-PNG-conditioned edits (color and character), then caption/arrow-only panels | Full HiDream edit leaked scene changes. FLUX color and lamp edits preserve recognizable scene; unit-price edit needed one corrected prompt to avoid an angry brow. Actual source PNGs for arrow/graphic panels had unchanged clean hashes and **zero changed RGB pixels outside overlay masks**. |
| 5 Exact graphics | `$6` on a tagged bag, three cloned orange cutouts, `$6 ÷ 3 = $2 each` | Integer cents assertion `600 = 3×200`; three distinct known layer instances and an independent orange-color connected-component count of three. Noto lacked `→`, caught as tofu in the first transfer MP4; generic glyph fallback to installed DejaVu corrected it. |
| 6 Complete episode | Five-panel unit-price example through `POST /renders` | 1080×1920, H.264/AAC, 30 fps, **776 encoded video frames**, 25.866667 s. A mid-sentence arrow reveals at frame 174, genuine expression edit, deliberate cut, last frame decoded and source/MP4 verified. First output exposed angry character/caption defects; revised job fixed these, preserving accepted art. Owner listening pending. |
| 7 New subject | Button→controller→lamp via the **same API and generic code** | First opening incorrectly pre-painted arrows; art-only signature and no-baked-arrow visual check fixed that. First full output turned lamp on too late; second adds a phoneme-aligned `lamp` cue; lampshade grounding after edit corrected Qwen whole-lamp ambiguity. Corrected 13.333333 s MP4 has **400 encoded video frames**, glow reveal at frame 146, exact label/arrows, final frame decoded. Owner listening pending. |

## HTTP, media, and failure checks

- A client got `202` and disconnected; later `GET /renders/{id}` succeeded and
  `GET /renders/{id}/video` returned an MP4 matching the job's SHA-256.
- Invalid requests returned `422`: unknown references/cues, incorrect exact
  arithmetic, exactly `45000 ms`, `44999 ms` rounding up to 45 seconds, and
  audio outlasting the authored end.
- A physically inaccessible backend produced a failed job and `409` for video.
  A separate injection test fails on the **second** scene after the first
  accepted PNG, preserving the completed PNG/manifest and producing no MP4.
- A near-limit encoded media test produces **1349 video frames**, probes and
  decodes the MP4, and checks the actual container remains strictly below 45 s.
- A valid new request changed only the final hold by 500 ms, with `reuse_from`.
  The output gained exactly **15 encoded video frames** (776→791), all clean
  hashes remained identical, there were **zero new GPU illustration calls**,
  and the last decoded frame was intact.
- A third HTTP integration job (`4d51a92b0db3424c999eae0dc02656a5`)
  generated **two different illustrated cutouts**, grounded a named
  `basket.opening` point on the actual isolated basket, and transformed that
  asset-local point to a controlled layout's final canvas. Its arrow tip
  visibly lands inside the opening; no final pixel coordinate was supplied.
  Source artwork remains identical across the overlay reveal; the 9.1 s
  H.264/AAC MP4 has **273 encoded video frames** and a complete last frame.
  A synthetic repositioning test moves the basket and verifies the opening
  follows its transform. This is an additional controlled-layout capability
  check, distinct from the two full-topic lessons.
- A **fourth HTTP request** (`6592bbb4368d4eba85a6f70b46aa57a9`) moved
  and resized that *actual generated basket asset* using structured layout
  values only. Its inherited asset-local Qwen opening point moved from
  `(777,864)` to `(841,870)` in final-canvas pixels and the arrow still
  ended inside the dark opening. Cutout hashes matched the original job.
  Wall time **2.404 s**, no new GPU generation or Qwen grounding. The XPS
  progress gallery v1.2 contains the inspected before/after and resultant MP4.
- Full MP4 verification probes H.264/AAC streams, CFR and frame count, decodes
  every frame for errors, and extracts encoded video frames immediately before
  and after selected cue boundaries. Source PNGs—not lossy MP4 frames—are used
  for exact-pixel overlay claims.
- The authoring voice is the public-domain LJSpeech high Piper ONNX. The
  resulting track was probed/decoded and showed a non-silent signal. **Audio
  naturalness, pronunciation and perceived speech-picture alignment have not
  been heard by this agent and require the owner's listening check.**

## Runtime accounting

On this workstation, initial model setup, installs and downloads overlapped
with application development. The backend setup/download session ran
**13:54:23–14:01:50 local time (7 m 27 s)**; voice setup took approximately
**7 s**, the local Qwen download/setup **2 m 20 s**, and user-space media setup
approximately **12 s**, overlapping the backend work rather than adding to it.
Component hashes, sizes and versions are in [`COMPONENTS.json`](COMPONENTS.json).
GPU call measurements from the first apple proof: HiDream Full **22.55 s
generation / 60.06 s reference edit**; FLUX 4B BF16 **4.55 s generation /
4.52 s reference edit** at 864×1536. On the later matched HiDream one-bag
pair: **22.765 s / 60.273 s**, sampled peak **17,976 MiB** VRAM.

- A **fresh**, no-`reuse_from` episode (`571b239eab0e4358a5597e9b3469dee5`),
  after restarting both services with `HF_HUB_OFFLINE=1` and
  `TRANSFORMERS_OFFLINE=1`, measured **77.228 s** between worker start and
  success. It made **three real image backend calls**: illustrated orange
  cutout **4.523 s**, opening scene **3.017 s**, reference edit **6.025 s**.
  Remaining time covers local Qwen review/grounding, layout, caption/video
  assembly, and verification. The reviewed episode is linked from
  `~/Videos/storyboard-renderer/demo`.
- A previously accepted episode changed **only** its ending by half a second
  (`92491378b36849978467bd0560c19020`), finished in **8.9 s**,
  produced 15 extra encoded video frames and **zero** new GPU image calls.
- The two-distinct-cutout mini-job measured **17.586 s** wall time. Separate
  stages recorded apple GPU generation **1.581 s**, basket GPU generation
  **1.562 s**, local Qwen basket-part grounding **11.956 s**, and media
  assembly/probe/decode **1.67 s**. It exposes the current vision-load cost
  rather than hiding it inside a model benchmark.
- Failed/declined attempts are preserved. The first two rejected unit-price
  jobs took **44.68 s** and **41.63 s**, exposing a two-bag error and
  ambiguous tag-edge query. The first signal-flow draft succeeded
  technically in **54.65 s** but baked arrows into art. Later revisions
  revealed a missing glyph, late lamp-on cue and whole-lamp-part ambiguity;
  the corrected transfer job (`b79d50f8c15046da887570799ccf53c0`)
  completed in **50.81 s**, reusing accepted illustration. Manual image
  review and art-direction edits were not separately timed: these job
  durations are **not** the total editorial iteration time.

**The measured ordinary episode is below the 20-minute benchmark**, but this
is one workstation/example, not a verified 10–20/day throughput guarantee.
Correct scene meaning and safe placement take priority over speed.
