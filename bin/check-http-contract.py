#!/usr/bin/env python3
"""Read-only requests except for intentionally rejected POSTs; no inference started."""
import json
from pathlib import Path
import httpx

root=Path("examples/unit-price")
base=json.loads((root/"story.json").read_text())
base["signature"]=(root/"signature.md").read_text()
audio=(root/"narration.wav").read_bytes()
url="http://127.0.0.1:8787/renders"
cases=[]
for label,change in [
    ("exactly-45-seconds",lambda s:s.update(end_ms=45000)),
    ("rounds-to-45-seconds",lambda s:s.update(end_ms=44999)),
    ("unknown-previous-panel",lambda s:s["panels"][1].update(refs=["NOPE"])),
    ("unknown-cue",lambda s:s["panels"][1].update(cue="NOPE")),
    ("wrong-quantity",lambda s:s["values"].update(each_minor=199)),
]:
    request=json.loads(json.dumps(base));change(request)
    r=httpx.post(url,data={"story":json.dumps(request)},files={"audio":("narration.wav",audio,"audio/wav")})
    cases.append({"name":label,"status":r.status_code,"detail":r.text[:300]})
    assert r.status_code==422, cases[-1]
request=json.loads(json.dumps(base))
request["end_ms"]=8000
request["panels"]=request["panels"][:2]
request["cues"]=[c for c in request["cues"] if c["ms"]<8000]
r=httpx.post(url,data={"story":json.dumps(request)},files={"audio":("narration.wav",audio,"audio/wav")})
cases.append({"name":"audio-outlasts-video","status":r.status_code,"detail":r.text[:300]})
assert r.status_code==422,cases[-1]
print(json.dumps(cases,indent=2))
