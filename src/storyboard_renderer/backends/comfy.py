from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

import httpx
from PIL import Image


class BackendError(RuntimeError):
    pass


def flux_graph(prompt: str, width: int, height: int, seed: int, filename: str | None = None) -> dict:
    def node(name, **inputs):
        return {"class_type": name, "inputs": inputs}
    graph = {
        "1": node("UNETLoader", unet_name="flux-2-klein-4b.safetensors", weight_dtype="default"),
        "2": node("CLIPLoader", clip_name="qwen_3_4b.safetensors", type="flux2", device="default"),
        "3": node("VAELoader", vae_name="flux2-vae.safetensors"),
        "4": node("CLIPTextEncode", clip=["2", 0], text=prompt),
        "5": node("ConditioningZeroOut", conditioning=["4", 0]),
        "6": node("EmptyFlux2LatentImage", width=width, height=height, batch_size=1),
        "7": node("Flux2Scheduler", steps=4, width=width, height=height),
        "8": node("RandomNoise", noise_seed=seed),
        "9": node("KSamplerSelect", sampler_name="euler"),
        "10": node("CFGGuider", model=["1", 0], positive=["4", 0], negative=["5", 0], cfg=1.0),
        "11": node("SamplerCustomAdvanced", noise=["8", 0], guider=["10", 0], sampler=["9", 0], sigmas=["7", 0], latent_image=["6", 0]),
        "12": node("VAEDecode", samples=["11", 0], vae=["3", 0]),
        "13": node("SaveImage", images=["12", 0], filename_prefix="storyboard"),
    }
    if filename:
        graph["14"] = node("LoadImage", image=filename)
        graph["15"] = node("VAEEncode", pixels=["14", 0], vae=["3", 0])
        graph["16"] = node("ReferenceLatent", conditioning=["4", 0], latent=["15", 0])
        graph["17"] = node("ReferenceLatent", conditioning=["5", 0], latent=["15", 0])
        graph["10"]["inputs"].update(positive=["16", 0], negative=["17", 0])
    return graph


def hidream_graph(prompt: str, width: int, height: int, seed: int, filename: str | None = None) -> dict:
    def node(name, **inputs):
        return {"class_type": name, "inputs": inputs}
    graph = {
        "1": node("CheckpointLoaderSimple", ckpt_name="hidream_o1_image_bf16.safetensors"),
        "2": node("ModelNoiseScale", model=["1", 0], noise_scale=8),
        "3": node("HiDreamO1PatchSeamSmoothing", model=["2", 0], strength=1.0, start_percent=0.8, end_percent=1.0, pattern="single_shift", passes="ramp_2_4", blend="median"),
        "4": node("CLIPTextEncode", clip=["1", 1], text=prompt),
        "5": node("CLIPTextEncode", clip=["1", 1], text=""),
        "6": node("EmptyHiDreamO1LatentImage", width=width, height=height, batch_size=1),
        "7": node("BasicScheduler", model=["2", 0], scheduler="normal", steps=50, denoise=1.0),
        "8": node("KSamplerSelect", sampler_name="dpmpp_2m_sde_gpu"),
        "9": node("SamplerCustom", model=["3", 0], positive=["4", 0], negative=["5", 0], sampler=["8", 0], sigmas=["7", 0], latent_image=["6", 0], add_noise=True, noise_seed=seed, cfg=5.0),
        "10": node("VAEDecode", samples=["9", 0], vae=["1", 2]),
        "11": node("SaveImage", images=["10", 0], filename_prefix="storyboard"),
    }
    if filename:
        graph["12"] = node("LoadImage", image=filename)
        graph["13"] = node("HiDreamO1ReferenceImages", positive=["4", 0], negative=["5", 0], **{"images.image_1": ["12", 0]})
        graph["9"]["inputs"].update(positive=["13", 0], negative=["13", 1])
    return graph


class ComfyBackend:
    def __init__(self, url: str, profile: str = "flux"):
        self.url = url.rstrip("/")
        self.profile = profile

    def ready(self) -> dict:
        with httpx.Client(timeout=8) as client:
            response = client.get(f"{self.url}/system_stats")
            response.raise_for_status()
            return response.json()

    def free(self) -> None:
        with httpx.Client(timeout=20) as client:
            client.post(f"{self.url}/free", json={"unload_models": True, "free_memory": True}).raise_for_status()

    def render(self, instruction: str, width: int, height: int, seed: int, out: Path, ref: Path | None = None) -> dict:
        start = time.monotonic()
        with httpx.Client(timeout=120, follow_redirects=False) as client:
            filename = None
            if ref:
                if not ref.is_file():
                    raise BackendError(f"reference missing: {ref}")
                with ref.open("rb") as image:
                    upload = client.post(
                        f"{self.url}/upload/image",
                        files={"image": (f"{uuid.uuid4().hex}.png", image, "image/png")},
                        data={"overwrite": "false"},
                    )
                upload.raise_for_status()
                filename = upload.json()["name"]
            if self.profile == "flux":
                graph = flux_graph(instruction, width, height, seed, filename)
                output_node = "13"
                workflow_version = "flux2-klein-4b-bf16-v1"
            elif self.profile == "hidream":
                graph = hidream_graph(instruction, width, height, seed, filename)
                output_node = "11"
                workflow_version = "hidream-o1-full-bf16-v1"
            else:
                raise BackendError(f"unsupported profile: {self.profile}")
            response = client.post(f"{self.url}/prompt", json={"prompt": graph, "client_id": uuid.uuid4().hex})
            if response.status_code != 200:
                raise BackendError(f"Comfy graph rejected: {response.text[:1800]}")
            prompt_id = response.json()["prompt_id"]
            deadline = time.monotonic() + 1800
            while time.monotonic() < deadline:
                time.sleep(1.5)
                history = client.get(f"{self.url}/history/{prompt_id}")
                history.raise_for_status()
                record = history.json().get(prompt_id)
                if record:
                    status = record.get("status", {})
                    if status.get("status_str") == "error" or status.get("completed") is False:
                        raise BackendError(f"Comfy error in {prompt_id}: {str(status)[:1500]}")
                    images = record.get("outputs", {}).get(output_node, {}).get("images", [])
                    if not images:
                        raise BackendError(f"Comfy {prompt_id} finished without image in output {output_node}: {str(status)[:1000]}")
                    info = images[0]
                    data = client.get(f"{self.url}/view", params={"filename": info["filename"], "subfolder": info.get("subfolder", ""), "type": info["type"]})
                    data.raise_for_status()
                    out.parent.mkdir(parents=True, exist_ok=True)
                    temp = out.with_suffix(".partial.png")
                    temp.write_bytes(data.content)
                    with Image.open(temp) as image:
                        image.verify()
                    # Comfy may embed prompt/job metadata that changes across otherwise
                    # pixel-identical renders. Preserve actual RGB pixels losslessly,
                    # strip transport metadata, and keep the exact graph in the manifest.
                    with Image.open(temp) as image:
                        clean = image.convert("RGB")
                        clean.load()
                    clean.save(temp, format="PNG", optimize=False)
                    temp.replace(out)
                    return {"profile": self.profile, "workflow_version": workflow_version,
                            "graph_sha256": hashlib.sha256(json.dumps(graph,sort_keys=True).encode()).hexdigest(),
                            "prompt_id": prompt_id, "graph": graph, "reference_upload": filename,
                            "seconds": round(time.monotonic()-start, 3)}
        raise BackendError(f"Comfy job {prompt_id} timed out")
