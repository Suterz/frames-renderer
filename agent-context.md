# Frames renderer

## Current baseline

- Standalone frame service with verified FLUX new-scene/reference-edit workflows, controlled composition, and bounded repair. Production stays pinned to `deployed/v2`.
- The new-scene/edit parity and raster suite passes 32 tests. The paired circuit and trail controls close a visible path and withhold the broken version.
- Semantic part targeting on generated artwork can still be ambiguous. Use controlled geometry for exact counts, parts, and movements where practical.
- Resume from the integration handoff in `story-generator/agent-context.md`. Branch from `main`; compare identical requests and preserve known-good behavior before promotion.

## Decisions, newest first

- **Consolidation:** retained the linear renderer history and checked the actual workflow snapshots. Archived the four duplicated narration files by SHA-256 instead of relying on WAVs in the frame checkout. Gallery: `Historical renderer examples/INDEX.md`.
- **Reproducibility:** pinned ComfyUI, model files, and isolated environments. A real FLUX edit reused its accepted parent clean PNG; red turned green, geometry stayed stable, and an exact overlay was added (`tested/fresh-install-2026-11-26`).
- **Path and precise parts:** connected and broken phone-raster paths distinguish the original circuit regression and a trail transfer (`c07e0d7`). Authored polygons made exact endpoints practical (`72eb918`); the revised requests are separate from the earlier generated-art refusals. Gallery: `v4/v4.5 - Saved rounds and rehearsal/REVIEW.md`.
- **Counts, motion, prediction and repair:** require pixels on the intended part, surviving clues, visible component counts, and actual cutout translation or insertion. Same-color neighboring parts and unchanged layouts fail; approved same-art overlay repairs work. `a30c5f1` excludes underline-shaped components without accepting extra round tokens.
- **Generated art and cutouts:** preserve the clean reference across edits; repeat generated cutouts for exact instances. Opt-in matte cleanup removes debris without filling the open-basket aperture (`a116950`). Generated part disambiguation still sometimes refuses a plausible endpoint.
- **Standalone V2 and rollback:** frame sessions became audio-independent; caption timing and MP4 ownership moved to video. Preserve V2 deployment and the detached `rollback/v1` monolith.
