#!/usr/bin/env python3
"""Standalone local grounding: source.png 'the apple' output_folder."""
import json
import sys
from pathlib import Path
from storyboard_renderer.grounding import resolve
src,name,folder=sys.argv[1],sys.argv[2],sys.argv[3]
result=resolve(Path(src),name,name,Path(folder))
print(json.dumps(result,indent=2))
