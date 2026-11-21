"""Local Qwen visual evaluator; one model load for several independent questions."""
import json
import sys
from pathlib import Path

import torch
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

request = json.load(sys.stdin)
root = str(Path.home() / "ai/models/vision/qwen3-vl-8b")
processor = AutoProcessor.from_pretrained(root, local_files_only=True)
model = Qwen3VLForConditionalGeneration.from_pretrained(
    root, dtype=torch.bfloat16, device_map="auto", attn_implementation="sdpa", local_files_only=True
)
answers = []
for query in request:
    content = []
    for role, image in query["images"]:
        content.extend([{"type": "text", "text": role}, {"type": "image", "image": image}])
    content.append({"type": "text", "text": query["prompt"]})
    inputs = processor.apply_chat_template([{"role": "user", "content": content}], tokenize=True,
                                           add_generation_prompt=True, return_dict=True, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        tokens = model.generate(**inputs, do_sample=False, max_new_tokens=380)
    answers.append(processor.decode(tokens[0][inputs.input_ids.shape[1]:], skip_special_tokens=True))
print(json.dumps(answers), flush=True)
