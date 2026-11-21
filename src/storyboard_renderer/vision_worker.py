"""Short-lived local Qwen3-VL process; never calls a hosted inference endpoint."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import torch
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor

model_dir = str(Path.home() / "ai/models/vision/qwen3-vl-8b")
picture, query = sys.argv[1:3]
model = Qwen3VLForConditionalGeneration.from_pretrained(model_dir, torch_dtype=torch.bfloat16, device_map="auto", attn_implementation="sdpa")
processor = AutoProcessor.from_pretrained(model_dir)
instruction = (
    "Locate exactly this target in the illustration: " + query + ". "
    "Return ONLY one JSON object with keys visible (boolean), reason (brief), "
    "bbox_2d ([x1,y1,x2,y2]), point_2d ([x,y]). "
    "Use 0..1000 normalized coordinates relative to THIS image. "
    "The point must be inside the specifically named visible object or part, not the center of its parent. "
    "If absent, obscured or uncertain set visible=false and use bbox_2d=[0,0,1,1], point_2d=[0,0]."
)
messages=[{"role":"user","content":[{"type":"image","image":picture},{"type":"text","text":instruction}]}]
inputs=processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors="pt")
inputs={k:v.to(model.device) if hasattr(v,"to") else v for k,v in inputs.items()}
with torch.inference_mode():
    generated=model.generate(**inputs,max_new_tokens=170,do_sample=False)
out=generated[0][inputs["input_ids"].shape[1]:]
print(processor.decode(out,skip_special_tokens=True),flush=True)
