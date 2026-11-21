from __future__ import annotations

import math
import re
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .grounding import NeedsReview

FONT = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font_for(text:str,size:int)->ImageFont.FreeTypeFont:
    for path in (FONT,FALLBACK_FONT):
        font=ImageFont.truetype(path,size)
        missing=bytes(font.getmask("\u0378"))
        missing_size=font.getmask("\u0378").size
        if all(font.getmask(letter).size!=missing_size or bytes(font.getmask(letter))!=missing for letter in text if not letter.isspace()):
            return font
    raise NeedsReview(f"unsupported glyph in approved instructional text: {text!r}")


def approved_text(template: str, values: dict) -> str:
    def replace(match):
        key = match.group(1)
        if key not in values:
            raise ValueError(f"unknown approved value {key}")
        return str(values[key])
    return re.sub(r"\{([a-zA-Z0-9_]+)\}", replace, template)


def make_cutout(source: Path, target: Path) -> Image.Image:
    """Flood-fill corner-connected pale background, not orange-colored foreground."""
    rgb=Image.open(source).convert("RGB")
    w,h=rgb.size
    pixels=rgb.load()
    corner=pixels[0,0]
    if max(corner)-min(corner)>38 or min(corner)<175:
        raise NeedsReview("cutout background is not light and neutral at top-left")
    reduced=rgb.resize((min(512,w),min(512,h)))
    rw,rh=reduced.size
    px=reduced.load()
    queue=deque([(0,0),(rw-1,0),(0,rh-1),(rw-1,rh-1)])
    outside=bytearray(rw*rh)
    while queue:
        x,y=queue.popleft()
        if not(0<=x<rw and 0<=y<rh):continue
        k=y*rw+x
        if outside[k]:continue
        r,g,b=px[x,y]
        if min(r,g,b)<175 or max(r,g,b)-min(r,g,b)>39:continue
        outside[k]=1
        queue.extend(((x+1,y),(x-1,y),(x,y+1),(x,y-1)))
    # Matte small border is intentionally conservative; never create extra objects.
    mask=Image.new("L",(rw,rh),255)
    mask.putdata([0 if x else 255 for x in outside])
    bounds=mask.getbbox()
    if bounds is None or (bounds[2]-bounds[0])*(bounds[3]-bounds[1])<rw*rh*.035 or (bounds[2]-bounds[0])*(bounds[3]-bounds[1])>rw*rh*.8:
        raise NeedsReview("orange cutout foreground appears absent or background has not been removed")
    cut=reduced.convert("RGBA")
    cut.putalpha(mask)
    cut=cut.crop(bounds)
    cut.save(target)
    return cut


def controlled_scene(size: tuple[int,int], asset: Image.Image, count: int, out: Path) -> dict:
    if count<1 or count>5:
        raise ValueError("controlled row supports 1 to 5 instances")
    w,h=size
    clean=Image.new("RGB",size,"#FFF3DB")
    target_w=min(round(w*.22),round(w*.72/count))
    target_h=round(target_w*asset.height/asset.width)
    if target_h>h*.34: target_h=round(h*.34);target_w=round(target_h*asset.width/asset.height)
    sprite=asset.resize((target_w,target_h),Image.Resampling.LANCZOS)
    centers=[round(w*(i+1)/(count+1)) for i in range(count)]
    y=round(h*.44)
    if count>1 and min(centers[1]-centers[0],w) < target_w+10:
        raise NeedsReview("controlled sprites overlap")
    anchors={}
    for i,x in enumerate(centers,1):
        box=(x-target_w//2,y-target_h//2,x-target_w//2+target_w,y-target_h//2+target_h)
        if box[0]<0 or box[2]>w: raise NeedsReview(f"orange_{i} clipped")
        clean.paste(sprite,box[:2],sprite)
        anchors[f"orange_{i}.center"]={"point":(x,y),"box":box,"method":"controlled geometry"}
        anchors[f"orange_{i}.below"]={"point":(x,box[3]+round(h*.035)),"box":box,"method":"controlled geometry"}
    clean.save(out)
    return anchors


def layered_scene(size:tuple[int,int],assets:dict[str,Image.Image],layers:list[dict],
                  asset_anchors:dict[str,dict[str,list[float]]],out:Path)->dict:
    """Compose different illustrated sprites using stable IDs and transformed local anchors."""
    if not layers or len(layers)>12:
        raise ValueError("controlled layers require 1 to 12 distinct instances")
    w,h=size
    clean=Image.new("RGB",size,"#FFF3DB")
    anchors={}
    placed=[]
    for layer in layers:
        name=layer["id"]
        key=layer["asset"]
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*",name) or any(name==existing for existing,_ in placed):
            raise ValueError(f"invalid or repeated controlled instance ID {name!r}")
        if key not in assets:raise ValueError(f"unknown cutout asset {key}")
        center=layer["center"]
        fraction=layer["width"]
        if (not isinstance(center,list) or len(center)!=2
            or any(not isinstance(v,(int,float)) or not 0<v<1 for v in center)
            or not isinstance(fraction,(int,float)) or not .05<=fraction<=.8):
            raise ValueError(f"{name}: invalid normalized center or width")
        sprite=assets[key]
        sw=round(w*fraction)
        sh=round(sw*sprite.height/sprite.width)
        if "max_height" in layer:
            limit=layer["max_height"]
            if not isinstance(limit,(int,float)) or not .02<=limit<=.8:
                raise ValueError(f"{name}: invalid max_height")
            if sh>h*limit:
                sh=round(h*limit)
                sw=max(1,round(sh*sprite.width/sprite.height))
        box=(round(center[0]*w-sw/2),round(center[1]*h-sh/2),
             round(center[0]*w-sw/2)+sw,round(center[1]*h-sh/2)+sh)
        if box[0]<0 or box[1]<0 or box[2]>w or box[3]>h:
            raise NeedsReview(f"{name}: controlled asset clipped")
        for previous,previous_box in placed:
            intersect=(max(box[0],previous_box[0])<min(box[2],previous_box[2])
                       and max(box[1],previous_box[1])<min(box[3],previous_box[3]))
            if intersect and not layer.get("allow_overlap"):
                raise NeedsReview(f"{name}: overlaps {previous}; choose distinct placement or explicitly allow overlap")
        resized=sprite.resize((sw,sh),Image.Resampling.LANCZOS)
        if resized.getchannel("A").getbbox() is None:raise NeedsReview(f"{name}: asset has no visible pixels")
        clean.paste(resized,box[:2],resized)
        placed.append((name,box))
        anchors[name+".center"]={"point":(round((box[0]+box[2])/2),round((box[1]+box[3])/2)),
                                 "box":box,"method":"controlled geometry","asset":key}
        for anchor,position in asset_anchors.get(key,{}).items():
            if not isinstance(position,list) or len(position)!=2 or any(not isinstance(v,(int,float)) or not 0<=v<=1 for v in position):
                raise ValueError(f"{key}.{anchor}: invalid asset-local normalized anchor")
            anchors[f"{name}.{anchor}"]={"point":(round(box[0]+sw*position[0]),round(box[1]+sh*position[1])),
                                        "box":box,"method":"controlled asset-local geometry","asset":key,
                                        "local_position":position}
    clean.save(out)
    return anchors


def point_of(value, anchors, size):
    if isinstance(value,list) and len(value)==2 and all(0<=x<=1 for x in value):
        return round(size[0]*value[0]),round(size[1]*value[1])
    if isinstance(value,str):
        if value=="safe.top": return (size[0]//2,round(size[1]*.13))
        if value=="safe.bottom":return (size[0]//2,round(size[1]*.72))
        if value in anchors:return anchors[value]["point"]
    raise NeedsReview(f"missing or invalid anchor {value}")


def compose(clean_path: Path, overlays: list, caption: str, values: dict, anchors: dict, size: tuple[int,int], out: Path, overlay_out: Path):
    image=Image.open(clean_path).convert("RGB").resize(size,Image.Resampling.LANCZOS)
    layer=Image.new("RGBA",size,(0,0,0,0))
    draw=ImageDraw.Draw(layer)
    w,h=size
    for item in overlays:
        kind=item.type
        if kind in ("text","label"):
            text=approved_text(item.text or "",values)
            if not text:raise NeedsReview("empty instructional text")
            at=item.at
            if isinstance(at,str) and at.endswith(".face"):
                if at not in anchors: raise NeedsReview(f"unresolved text region {at}")
                x0,y0,x1,y1=anchors[at]["box"]
                center=((x0+x1)//2,(y0+y1)//2)
                max_size=(x1-x0-12,y1-y0-12)
                font=font_for(text,max(44,round(w*.082)))
                for pt in range(round(w*.08),18,-2):
                    candidate=font_for(text,pt)
                    bb=draw.textbbox((0,0),text,font=candidate)
                    if bb[2]-bb[0]<max_size[0] and bb[3]-bb[1]<max_size[1]:
                        font=candidate;break
                else: raise NeedsReview(f"text does not fit {at}")
            else:
                center=point_of(at,anchors,size)
                max_pt=max(28,round(w*.048))
                for pt in range(max_pt,27,-2):
                    font=font_for(text,pt)
                    if draw.textlength(text,font=font)<=w*.82:
                        break
                else:
                    raise NeedsReview(f"instructional text too wide at phone-legible size: {text!r}")
            bounds=draw.textbbox(center,text,font=font,anchor="mm")
            if bounds[0]<w*.06 or bounds[2]>w*.94 or bounds[1]<h*.04 or bounds[3]>h*.84:
                raise NeedsReview(f"text '{text}' outside safe visual region")
            if not (isinstance(at,str) and at.endswith(".face")):
                draw.rounded_rectangle((bounds[0]-15,bounds[1]-12,bounds[2]+15,bounds[3]+12),radius=12,fill="#302337")
                draw.text(center,text,fill="#FFF3DB",font=font,anchor="mm")
            else:draw.text(center,text,fill="#302337",stroke_width=1,font=font,anchor="mm")
        elif kind in ("arrow","marker"):
            end=point_of(item.to or item.at,anchors,size)
            if kind=="marker":
                r=max(12,w//52)
                draw.ellipse((end[0]-r,end[1]-r,end[0]+r,end[1]+r),outline="#302337",width=6)
                draw.ellipse((end[0]-r+4,end[1]-r+4,end[0]+r-4,end[1]+r-4),outline="#F6B940",width=5)
            else:
                start=point_of(item.source,anchors,size)
                dx,dy=end[0]-start[0],end[1]-start[1]
                length=math.hypot(dx,dy)
                if length < w*.04: raise NeedsReview("arrow too short")
                u=(dx/length,dy/length); perp=(-u[1],u[0])
                tip=((end[0],end[1]))
                v1=(end[0]-u[0]*w*.048+perp[0]*w*.023,end[1]-u[1]*w*.048+perp[1]*w*.023)
                v2=(end[0]-u[0]*w*.048-perp[0]*w*.023,end[1]-u[1]*w*.048-perp[1]*w*.023)
                draw.line([start,end],fill="#302337",width=max(15,round(w*.019)),joint="curve")
                draw.line([start,end],fill="#F6B940",width=max(9,round(w*.012)),joint="curve")
                draw.polygon([tip,v1,v2],fill="#F6B940")
                draw.line([v1,tip,v2],fill="#302337",width=max(3,round(w*.005)),joint="curve")
    layer.save(overlay_out)
    image.paste(layer,(0,0),layer)
    if caption:
        caption=approved_text(caption,values)
        cdraw=ImageDraw.Draw(image)
        font=font_for(caption,max(35,round(w*.047)))
        words=caption.split()
        lines=[""]
        for word in words:
            trial=(lines[-1]+" "+word).strip()
            if cdraw.textlength(trial,font=font)>w*.82:
                lines.append(word)
            else:lines[-1]=trial
        if len(lines)>2: raise NeedsReview(f"caption exceeds two lines: {caption}")
        bottom=round(h*.962)
        line_height=round(h*.045)
        top=bottom-(line_height*len(lines)+round(h*.026))
        cdraw.rounded_rectangle((round(w*.065),top,round(w*.935),bottom),radius=22,fill="#302337")
        for i,line in enumerate(lines):
            cdraw.text((w//2,top+round(h*.013)+i*line_height),line,anchor="mt",font=font,fill="#FFF3DB")
    out.parent.mkdir(parents=True,exist_ok=True)
    image.save(out)
