from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import time
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .backends.comfy import ComfyBackend
from .compose import FONT, compose, controlled_scene, layered_scene, make_cutout
from .grounding import NeedsReview, resolve, inspect_relationship, derive_edge
from .schema import Story
from .signature import art_only

ROOT=Path(os.environ.get("STORY_OUTPUT", str(Path.home()/"Videos/storyboard-renderer/jobs")))
COMFY=os.environ.get("STORY_COMFY_URL","http://127.0.0.1:8188")
FFMPEG=os.environ.get("STORY_FFMPEG",str(Path.home()/"ai/tools/media/bin/ffmpeg"))
FFPROBE=os.environ.get("STORY_FFPROBE",str(Path.home()/"ai/tools/media/bin/ffprobe"))
PROFILE=os.environ.get("STORY_PROFILE","flux")
AUDIO_GAIN=float(os.environ.get("STORY_AUDIO_GAIN","0.85"))


def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()


def atomic_json(path:Path,obj:dict):
    temp=path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj,indent=2,default=str))
    temp.replace(path)


def probe_audio(path:Path,story:Story)->tuple[int,int]:
    with wave.open(str(path),"rb") as wav:
        channels,rate,width,n=wav.getnchannels(),wav.getframerate(),wav.getsampwidth(),wav.getnframes()
        if (channels,rate,width)!=(1,48000,2):raise ValueError("audio must be mono 48kHz PCM16 WAV")
        if n<=0 or n>=45*rate:raise ValueError("audio must have content and be strictly shorter than 45s")
        duration=n/rate
        if duration > story.end_ms/1000+1/rate:
            raise ValueError(f"audio runs past authored end: {duration:.3f}s > {story.end_ms/1000:.3f}s")
        return n,rate


def inputs_for_panel(story:Story,p,ref:Path|None,size:tuple[int,int]):
    return {"profile":PROFILE,"signature":art_only(story.signature),"premise":story.premise,"context":story.context,
            "panel":p.visual,"change":p.change,"keep":p.keep,"seed":p.seed,"size":size,
            "reference":sha(ref) if ref else None}


def encode(paths:list[Path],segments:list[tuple[int,int,int]],story:Story,audio:Path,out:Path)->dict:
    started=time.monotonic()
    if not 0<AUDIO_GAIN<=1:
        raise ValueError("STORY_AUDIO_GAIN must be in (0,1]")
    w,h,f=story.output.width,story.output.height,story.output.fps
    n=math.ceil(story.end_ms*f/1000)
    end=n/f
    if end>=45:raise ValueError("rounded encoded duration reaches 45 seconds")
    cmd=[FFMPEG,"-hide_banner","-loglevel","error","-y","-f","rawvideo","-pixel_format","rgb24","-video_size",f"{w}x{h}",
         "-framerate",str(f),"-i","pipe:0","-i",str(audio),"-filter:a",f"volume={AUDIO_GAIN},apad",
         "-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-r",str(f),
         "-c:a","aac","-b:a","160k","-ar","48000","-t",f"{end:.9f}","-frames:v",str(n),"-movflags","+faststart",str(out)]
    proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for start,stop,p in segments:
            with Image.open(paths[p]) as img:
                frame=img.convert("RGB").tobytes()
            for _ in range(start,stop):
                proc.stdin.write(frame)
        proc.stdin.close()
        error=proc.stderr.read().decode(errors="replace")
        code=proc.wait()
    except Exception:
        proc.kill();proc.wait();raise
    if code:raise RuntimeError(f"FFmpeg encode failed: {error[-1200:]}")
    info=subprocess.check_output([FFPROBE,"-v","error","-count_frames","-show_streams","-show_format","-of","json",str(out)],text=True)
    data=json.loads(info)
    streams=data["streams"]
    video=next((x for x in streams if x["codec_type"]=="video"),{})
    sound=next((x for x in streams if x["codec_type"]=="audio"),{})
    if (not video or not sound or video.get("codec_name")!="h264" or sound.get("codec_name")!="aac"
            or video.get("pix_fmt")!="yuv420p" or video.get("avg_frame_rate")!=f"{f}/1"
            or sound.get("sample_rate")!="48000"
            or video.get("width")!=w or video.get("height")!=h or int(video.get("nb_read_frames",0))!=n):
        raise RuntimeError(f"encoded stream verification failed: {video} {sound}")
    if float(data["format"]["duration"])>=45 or max(float(video.get("duration",0)),float(sound.get("duration",0)))>=45:
        raise RuntimeError("muxed output reaches or exceeds 45s")
    subprocess.run([FFMPEG,"-v","error","-i",str(out),"-f","null","-"],check=True,timeout=300)
    return {"expected_video_frames":n,"expected_duration":end,"audio_gain":AUDIO_GAIN,
            "assembly_seconds":round(time.monotonic()-started,3),"ffprobe":data}


def contact_sheet(paths:list[Path],out:Path,ids:list[str]):
    thumbs=[]
    for i,p in enumerate(paths):
        with Image.open(p) as img:thumb=img.convert("RGB").resize((270,480))
        stamp=ImageDraw.Draw(thumb)
        stamp.rectangle((0,0,170,36),fill="#302337")
        stamp.text((8,4),ids[i],font=ImageFont.truetype(FONT,22),fill="white")
        thumbs.append(thumb)
    sheet=Image.new("RGB",(270*len(thumbs),480),"white")
    for i,im in enumerate(thumbs):sheet.paste(im,(i*270,0))
    sheet.save(out,quality=90)


def run(job:Path,status:dict,save_status):
    started=time.monotonic()
    story=Story.model_validate_json((job/"request.json").read_text())
    audio=job/"narration.wav"
    probe_audio(audio,story)
    backend=ComfyBackend(COMFY,PROFILE)
    backend.ready()
    size=(story.output.width,story.output.height)
    art_size=(864,1536) if PROFILE=="flux" else (1440,2560)
    cue_map={c.id:c for c in story.cues}
    manifest={"story_id":story.story_id,"profile":PROFILE,"panels":[],"assets":{},"timeline":[],"revision":1}
    clean_paths, panels, anchor_maps = [],[],[]
    prior_job=ROOT/status["reuse_from"] if status.get("reuse_from") else None
    prior_manifest=None
    if prior_job and (prior_job/"manifest.json").is_file():
        prior_manifest=json.loads((prior_job/"manifest.json").read_text())
    (job/"clean").mkdir(exist_ok=True)
    (job/"composed").mkdir(exist_ok=True)
    (job/"overlays").mkdir(exist_ok=True)
    (job/"evidence").mkdir(exist_ok=True)
    asset_anchor_positions={}
    def generate_asset(key,asset):
        loc=job/"clean"/f"asset_{key}.png"
        cut=job/"clean"/f"asset_{key}_cutout.png"
        arg={"profile":PROFILE,"kind":"generated_cutout","visual":asset.visual,"signature":art_only(story.signature),"seed":asset.seed,"size":(768,768)}
        fingerprint=hashlib.sha256(json.dumps(arg,sort_keys=True).encode()).hexdigest()
        reused=False
        if prior_manifest and prior_manifest.get("assets",{}).get(key,{}).get("fingerprint")==fingerprint:
            previous=prior_job/"clean"/f"asset_{key}.png"
            if previous.exists() and sha(previous)==prior_manifest["assets"][key]["hash"]:
                shutil.copy2(previous,loc);reused=True
        record=None
        if not reused:
            status.update(phase=f"generating asset {key}");save_status(status)
            record=backend.render(
                f"{art_only(story.signature)}\nAn editorial cartoon cutout asset. {asset.visual} "
                "Single centered object on completely flat clean white background; no text, border, other objects or floor shadow.",
                768,768,asset.seed,loc)
        sprite=make_cutout(loc,cut)
        asset_anchor_positions[key]={}
        anchor_records={}
        previous_asset=prior_manifest.get("assets",{}).get(key,{}) if prior_manifest else {}
        for anchor,spec in asset.anchors.items():
            if isinstance(spec,str):
                previous_record=previous_asset.get("anchors",{}).get(anchor,{})
                if (reused and previous_record.get("spec")==spec and previous_record.get("cutout_hash")==sha(cut)
                    and previous_record.get("method")=="qwen3-vl-local"):
                    record_anchor={**previous_record,"reused":True}
                else:
                    backend.free()
                    located=resolve(cut,f"{key}.{anchor}",spec,job/"evidence"/f"asset_{key}")
                    point=located["point"]
                    if (not 0<=point[0]<sprite.width or not 0<=point[1]<sprite.height
                        or sprite.getpixel(tuple(point))[3]<128):
                        raise NeedsReview(f"{key}.{anchor}: local target is outside visible asset")
                    record_anchor={"spec":spec,"method":"qwen3-vl-local","cutout_hash":sha(cut),
                                   "position":[point[0]/sprite.width,point[1]/sprite.height],
                                   "grounding":located,"reused":False}
            else:
                record_anchor={"spec":spec,"method":"caller-defined asset-local",
                               "cutout_hash":sha(cut),"position":spec,"reused":reused}
            asset_anchor_positions[key][anchor]=record_anchor["position"]
            anchor_records[anchor]=record_anchor
        manifest["assets"][key]={"fingerprint":fingerprint,"hash":sha(loc),"cutout":str(cut),
                                 "cutout_hash":sha(cut),"anchors":anchor_records,
                                 "reused":reused,"backend":record}
        return sprite
    generated_assets={}
    for key,asset in story.assets.items():
        generated_assets[key]=generate_asset(key,asset)
    for i,p in enumerate(story.panels):
        status.update(phase=f"panel {p.id}",current_panel=p.id,completed=i);save_status(status)
        clean=job/"clean"/f"{p.id}.png"
        previous=clean_paths[-1] if clean_paths else None
        ref=previous if p.op=="edit_scene" else None
        inputs=inputs_for_panel(story,p,ref,art_size)
        fingerprint=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
        prior=(prior_manifest.get("panels",[])[i] if prior_manifest and len(prior_manifest.get("panels",[]))>i else {})
        prior_clean=prior_job/"clean"/f"{p.id}.png" if prior_job else None
        reused=False
        resolution_fingerprint=None
        if p.op=="overlay_only":
            shutil.copy2(previous,clean);reused=True
        elif prior.get("fingerprint")==fingerprint and prior_clean and prior_clean.is_file() and sha(prior_clean)==prior.get("clean_hash"):
            shutil.copy2(prior_clean,clean);reused=True
        if p.layout:
            if p.op!="new_scene":raise ValueError(f"{p.id}: controlled layout must start a scene")
            if "layers" in p.layout:
                anchors=layered_scene(size,generated_assets,p.layout["layers"],
                                      asset_anchor_positions,clean)
            else:
                key=p.layout["asset"]
                if key not in generated_assets:raise ValueError(f"{p.id}: unknown asset {key}")
                count=p.layout["count"]
                if isinstance(count,str):count=story.values[count]
                anchors=controlled_scene(size,generated_assets[key],int(count),clean)
            # known geometry, not a backend generated scene; asset was generated by GPU
            record=None;reused=False
        elif p.op=="overlay_only":
            anchors={k:v.copy() for k,v in anchor_maps[-1].items()}
            record=None
        else:
            record=None
            if not reused:
                backend_prompt=f"{art_only(story.signature)}\nStory: {story.premise}. {story.context}\n"
                if p.op=="new_scene":backend_prompt+=f"NEW COMPOSITION: {p.visual}. {p.keep}. No baked captions, price numerals, labels or words."
                else:backend_prompt+=f"Edit the provided illustration. Desired result: {p.visual}. Specific requested change: {p.change}. Preserve: {p.keep}. Keep the composition, character identity and every unspecified object stable. No baked captions or text."
                record=backend.render(backend_prompt,*art_size,p.seed,clean,ref)
            grounding_inputs={"source_hash":sha(clean),"anchors":p.model_dump()["anchors"],"visual_checks":p.visual_checks}
            resolution_fingerprint=hashlib.sha256(json.dumps(grounding_inputs,sort_keys=True).encode()).hexdigest()
            prior_checks=prior_manifest.get("visual_checks",{}).get(p.id) if prior_manifest else None
            reuse_grounding=(reused and prior.get("resolution_fingerprint")==resolution_fingerprint
                             and isinstance(prior.get("anchors"),dict)
                             and (not p.visual_checks or prior_checks is not None))
            if reuse_grounding:
                anchors=prior["anchors"]
                if prior_checks:
                    manifest.setdefault("visual_checks",{})[p.id]=prior_checks
            else:
                # Never inherit coordinates after a changed image or changed semantic query.
                anchors={}
                if p.visual_checks:
                    backend.free()
                    for check in p.visual_checks:
                        observed=inspect_relationship(clean,check["question"],check["expected"])
                        manifest.setdefault("visual_checks",{}).setdefault(p.id,[]).append(observed)
                        atomic_json(job/"manifest.json",manifest)
                if p.anchors:
                    backend.free()
                    for key,description in p.anchors.items():
                        if not isinstance(description,str):continue
                        located=resolve(clean,key,description,job/"evidence"/p.id)
                        with Image.open(clean) as img: source_size=img.size
                        sx,sy=size[0]/source_size[0],size[1]/source_size[1]
                        located["source_point"]=located["point"]
                        located["point"]=(round(located["point"][0]*sx),round(located["point"][1]*sy))
                        located["box"]=tuple(round(coord*(sx if j%2==0 else sy)) for j,coord in enumerate(located["box"]))
                        located["source_hash"]=sha(clean)
                        anchors[key]=located
                    for key,formula in p.anchors.items():
                        if isinstance(formula,str):continue
                        if formula.of not in anchors or formula.toward not in anchors:
                            raise NeedsReview(f"{p.id}: cannot derive {key}; base anchors not resolved")
                        anchors[key]=derive_edge(anchors[formula.of],anchors[formula.toward],formula.of,formula.toward)
        # Resolved anchors inherited from a preceding edited panel must be anchored to its clean hash.
        needed=set()
        for overlay in p.overlays:
            for loc in [overlay.at,overlay.source,overlay.to]:
                if isinstance(loc,str) and "." in loc and loc not in ["safe.top","safe.bottom"]:
                    needed.add(loc)
        missing=needed-anchors.keys()
        if missing:
            raise NeedsReview(f"{p.id}: unresolved anchors: {sorted(missing)}; request must declare their descriptions on this panel")
        for key in needed:
            if anchors[key].get("source_hash") and anchors[key]["source_hash"]!=sha(clean):
                raise NeedsReview(f"{p.id}: {key} was not revalidated on edited artwork")
        overlay_path=job/"overlays"/f"{p.id}.png"
        # A panel image includes its overlays but not transient captions.
        composed=job/"composed"/f"{p.id}.png"
        compose(clean,p.overlays,"",story.values,anchors,size,composed,overlay_path)
        clean_paths.append(clean);anchor_maps.append(anchors);panels.append(composed)
        manifest["panels"].append({"id":p.id,"scene":p.scene,"op":p.op,"cue":p.cue,"clean":str(clean),
                                  "clean_hash":sha(clean),"composed":str(composed),"anchors":anchors,
                                  "layout":p.layout,
                                  "reference":str(ref) if ref else None,"reference_hash":sha(ref) if ref else None,
                                  "fingerprint":fingerprint,"resolution_fingerprint":resolution_fingerprint,
                                  "reused":reused,"grounding_reused":bool(reused and resolution_fingerprint and prior.get("resolution_fingerprint")==resolution_fingerprint),
                                  "backend":record})
        atomic_json(job/"manifest.json",manifest)
    contact_sheet(panels,job/"contact-sheet.jpg",[p.id for p in story.panels])
    cues=story.cues
    f=story.output.fps
    end=math.ceil(story.end_ms*f/1000)
    starts=[(c.ms*f+500)//1000 for c in cues]
    panel_starts=[(cue_map[p.cue].ms*f+500)//1000 for p in story.panels]
    captions=[]
    segment=[]
    for i,c in enumerate(cues):
        a=starts[i];b=starts[i+1] if i+1<len(starts) else end
        p=max(j for j,t in enumerate(panel_starts) if t<=a)
        caption=c.caption if c.caption is not None else c.say
        render=job/"composed"/f"frame_{i:02d}.png"
        compose(clean_paths[p],story.panels[p].overlays,caption,story.values,anchor_maps[p],size,render,job/"overlays"/f"{story.panels[p].id}.png")
        captions.append(render);segment.append((a,b,i))
        manifest["timeline"].append({"cue":c.id,"panel":story.panels[p].id,"start_frame":a,"end_frame":b,"hold_frames":b-a,"caption":caption})
    status.update(phase="encoding",completed=len(panels));save_status(status)
    candidate=job/"video.partial.mp4"
    manifest["verification"]=encode(captions,segment,story,audio,candidate)
    candidate.replace(job/"video.mp4")
    manifest["video"]=str(job/"video.mp4")
    manifest["video_hash"]=sha(job/"video.mp4")
    manifest["render_wall_seconds"]=round(time.monotonic()-started,3)
    atomic_json(job/"manifest.json",manifest)
    return manifest
