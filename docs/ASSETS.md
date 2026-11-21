# Locally run components and licensing evidence

The episode contains original generated illustrations and approved code-rendered text. No stock illustration pack, cloud generation account or music track is used. Preserve exact model hashes in job manifests and the external tool directories.

| Component | Purpose | Source and terms |
| --- | --- | --- |
| HiDream-O1-Image **Full** BF16 Comfy repack | Art comparison only, not a Dev model | MIT, publisher's model card https://huggingface.co/HiDream-ai/HiDream-O1-Image ; exact tested repack https://huggingface.co/Comfy-Org/HiDream-O1-Image/tree/7b75f4cd7e757d55d9bd1d30fb40375fb446f38c/checkpoints |
| FLUX.2 [klein] **4B BF16** | Art comparison and provisional renderer profile | Apache-2.0, https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/tree/e7b7dc27f91deacad38e78976d1f2b499d76a294 |
| FLUX.2 Klein encoder/VAE | Required by ComfyUI graph | https://huggingface.co/Comfy-Org/flux2-klein-4B/tree/5b3abca5c0dc1ecd4eaf3340868d09063fc1c965/split_files ; verify upstream Qwen and VAE Apache-2.0 terms |
| Qwen3-VL-8B-Instruct | Local object grounding and source review | Apache-2.0, https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct/tree/0c351dd01ed87e9c1b53cbc748cba10e6187ff3b |
| LJSpeech high Piper voice | Offline narrator, CPU authoring | Public domain, explicitly stated by voice creator https://brycebeattie.com/files/tts/ ; `ljspeech.onnx` and matching `.onnx.json` outside Git |
| Piper authoring software | Offline WAV preparation, not renderer service | GPL-3.0-or-later, https://github.com/OHF-Voice/piper1-gpl |
| Noto Sans Bold | Renderer labels, approved numbers and captions | SIL OFL-1.1, Ubuntu `fonts-noto-core` and https://github.com/notofonts/latin-greek-cyrillic |
| DejaVu Sans Bold | Font fallback for `→` and other glyphs missing from the installed Noto face | Ubuntu `fonts-dejavu-core` ships the Bitstream Vera/DejaVu font license; commercial use is permitted subject to the font software's notice/redistribution terms. Source: `/usr/share/doc/fonts-dejavu-core/copyright`. Runtime checks font glyphs before drawing; copies of the font are not committed or embedded in the video. |
| ComfyUI | External illustration process | GPL-3.0, https://github.com/Comfy-Org/ComfyUI, installed separately from this project |
| FFmpeg / ffprobe | User-space MP4 encoding and decoding | conda-forge GPL build including `libx264`; comply with its redistributed license obligations, installed outside Git |

The factual claim “unit price is cost per item when count is the comparison unit” follows the United Kingdom Competition and Markets Authority overview: https://competitionandmarkets.blog.gov.uk/2024/01/30/a-short-guide-to-unit-pricing/ . The example’s $6 and three oranges are invented; arithmetic is verified using integer cents.
