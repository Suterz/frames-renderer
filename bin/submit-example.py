#!/usr/bin/env python3
"""Reads signature.md, uploads JSON and narration to the public HTTP API."""
import copy
import json
import sys
import urllib.request
from pathlib import Path

import httpx

root=Path(sys.argv[1] if len(sys.argv)>1 else "examples/unit-price").resolve()
data=json.loads((root/"story.json").read_text())
data["signature"]=(root/"signature.md").read_text()
fields={"story":json.dumps(data)}
if len(sys.argv)>2:
    fields["reuse_from"]=sys.argv[2]
with (root/"narration.wav").open("rb") as wav:
    response=httpx.post("http://127.0.0.1:8787/renders",
                        data=fields,
                        files={"audio":("narration.wav",wav,"audio/wav")},
                        timeout=120)
response.raise_for_status()
print(response.json()["id"])
