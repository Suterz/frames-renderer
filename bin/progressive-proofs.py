#!/usr/bin/env python3
"""Standalone, artifact-producing acceptance trials for semantic grounding."""
from __future__ import annotations
import json,sys,traceback
from pathlib import Path
from PIL import Image
from storyboard_renderer.backends.comfy import ComfyBackend
from storyboard_renderer.compose import compose
from storyboard_renderer.grounding import NeedsReview, resolve
from storyboard_renderer.schema import Overlay
from storyboard_renderer.frame_engine import sha
from storyboard_renderer.signature import art_only

profile=sys.argv[1] if len(sys.argv)>1 else "flux"
root=Path.home()/"Videos/storyboard-renderer/progressive"
root.mkdir(parents=True,exist_ok=True)
signature=art_only(Path("examples/unit-price/signature.md").read_text())
backend=ComfyBackend("http://127.0.0.1:8188",profile)
width,height=864,1536
report=[]
def trial(level,label,instruction,seed,targets,graphics):
    d=root/f"level-{level}-{label}";d.mkdir(parents=True,exist_ok=True)
    raw=d/"clean.png"
    config={"profile":profile,"signature":signature,"visual":instruction,"seed":seed,"native":[width,height],"targets":targets,"overlays":graphics}
    (d/"request.json").write_text(json.dumps(config,indent=2))
    result={"level":level,"label":label,"image":str(raw),"seed":seed,"failure":None}
    try:
        result["backend"]=backend.render(signature+"\n"+instruction,width,height,seed,raw)
        backend.free()
        anchors={}
        for name,query in targets.items():
            located=resolve(raw,name,query,d/"grounding")
            located["source_sha256"]=sha(raw)
            located["point"]=(round(located["point"][0]*1080/width),round(located["point"][1]*1920/height))
            anchors[name]=located
        over=[Overlay.model_validate(x) for x in graphics]
        compose(raw,over,"",{},anchors,(1080,1920),d/"annotated.png",d/"overlay.png")
        result["anchors"]=anchors
    except NeedsReview as exc:
        result["failure"]=f"needs_review: {exc}"
    except Exception as exc:
        result["failure"]=f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    (d/"result.json").write_text(json.dumps(result,indent=2,default=str))
    report.append({k:v for k,v in result.items() if k in ("level","label","failure","image")})
    print(json.dumps(report[-1]),flush=True)

trial(1,"apple-left","Exactly one large red cartoon apple, at the LEFT side of a clean ivory poster, one small leaf, no other objects, plum bold outline, lots of space to right.",153,{"apple.center":"center of the single red apple fruit body"},[{"type":"marker","at":"apple.center"}])
trial(1,"apple-right","Exactly one large red cartoon apple, at the RIGHT side of a clean ivory poster, one small leaf, no other objects, plum bold outline, lots of space to left.",791,{"apple.center":"center of the single red apple fruit body"},[{"type":"marker","at":"apple.center"}])
trial(2,"apple-left-basket-right","One red apple at far LEFT and one open wicker basket at far RIGHT on an uncluttered ivory paper background. Separate visible silhouettes, plump red apple, clearly open dark oval inside basket top. No other fruit.",303,
      {"apple.center":"center of the one red apple","basket.center":"center of the one wicker basket"},[{"type":"arrow","from":"apple.center","to":"basket.center"}])
trial(2,"basket-left-apple-right","One open wicker basket at far LEFT and one red apple at far RIGHT on an uncluttered ivory paper background. Separate visible silhouettes, clearly open dark oval inside basket top. No other fruit.",992,
      {"apple.center":"center of the one red apple at right","basket.center":"center of the one wicker basket at left"},[{"type":"arrow","from":"apple.center","to":"basket.center"}])
trial(3,"basket-opening","One open wicker basket at far RIGHT and two distinct fruits at left, a red apple nearer the basket and a yellow pear further from the basket. Dark visible oval basket OPENING with roomy clear rim. Ivory background.",89,
      {"apple.center":"center of the red apple nearer the basket","basket.opening":"a point inside the dark visible empty opening between the top rim of the wicker basket"},[{"type":"arrow","from":"apple.center","to":"basket.opening"}])
# Negative probe tests behavior if a target is not present. An incorrect confident detection is a defect.
negative=root/"level-3-absent-target";negative.mkdir(exist_ok=True)
try:
    source=root/"level-1-apple-left"/"clean.png"
    answer=resolve(source,"purple.knot","the purple knot attached to a price tag, which might not exist",negative)
    status={"failure":"absent target accepted","answer":answer}
except NeedsReview as exc:status={"result":"correctly declined absent target","reason":str(exc)}
(negative/"result.json").write_text(json.dumps(status,indent=2,default=str))
report.append({"level":3,"label":"absent-target","failure":status.get("failure")})
(root/"summary.json").write_text(json.dumps(report,indent=2))
