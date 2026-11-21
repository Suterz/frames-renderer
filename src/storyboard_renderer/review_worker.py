"""Short-lived local visual review; returns a proposed answer, not a guarantee."""
import sys
import torch
from pathlib import Path
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor

image,question=sys.argv[1:3]
root=str(Path.home()/"ai/models/vision/qwen3-vl-8b")
model=Qwen3VLForConditionalGeneration.from_pretrained(root,torch_dtype=torch.bfloat16,device_map="auto",attn_implementation="sdpa")
processor=AutoProcessor.from_pretrained(root)
messages=[{"role":"user","content":[{"type":"image","image":image},
          {"type":"text","text":"Inspect the illustrated scene carefully. "+question+
           " Answer only a JSON object with string keys 'answer' and 'reason'. "
           "If a relation is ambiguous, write 'unknown' instead of guessing."}]}]
inputs=processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=True,return_tensors="pt")
inputs={k:v.to(model.device) if hasattr(v,"to") else v for k,v in inputs.items()}
with torch.inference_mode():
    tokens=model.generate(**inputs,max_new_tokens=135,do_sample=False)
print(processor.decode(tokens[0][inputs["input_ids"].shape[1]:],skip_special_tokens=True))
