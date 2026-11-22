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


def largest_component(mask: Image.Image) -> Image.Image:
    """Keep a caller-declared coherent silhouette; preserve enclosed holes."""
    w,h=mask.size
    remaining=bytearray(bool(x) for x in mask.tobytes())
    largest=[]
    for start in range(w*h):
        if not remaining[start]:
            continue
        remaining[start]=0
        component=[start]
        for n in component:
            x,y=n%w,n//w
            for k in (n-1 if x else -1,n+1 if x<w-1 else -1,n-w if y else -1,n+w if y<h-1 else -1):
                if k>=0 and remaining[k]:
                    remaining[k]=0
                    component.append(k)
        if len(component)>len(largest):
            largest=component
    picked=bytearray(w*h)
    for k in largest:
        picked[k]=255
    return Image.frombytes("L",(w,h),bytes(picked))


def make_cutout(source: Path, target: Path, *, keep_largest=False) -> Image.Image:
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
    if keep_largest:
        mask=largest_component(mask)
    bounds=mask.getbbox()
    if bounds is None or (bounds[2]-bounds[0])*(bounds[3]-bounds[1])<rw*rh*.035 or (bounds[2]-bounds[0])*(bounds[3]-bounds[1])>rw*rh*.8:
        raise NeedsReview("cutout foreground appears absent or background has not been removed")
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
        flip_x=layer.get("flip_x",False)
        if type(flip_x) is not bool:
            raise NeedsReview("flip_x must be boolean")
        if flip_x:
            sprite=sprite.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
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
                                  "box":box,"method":"controlled geometry","asset":key,"flip_x":flip_x}
        for anchor,position in asset_anchors.get(key,{}).items():
            if not isinstance(position,list) or len(position)!=2 or any(not isinstance(v,(int,float)) or not 0<=v<=1 for v in position):
                raise ValueError(f"{key}.{anchor}: invalid asset-local normalized anchor")
            px=1-position[0] if flip_x else position[0]
            anchors[f"{name}.{anchor}"]={"point":(round(box[0]+sw*px),round(box[1]+sh*position[1])),
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


GRAPHIC_THEMES = {
    "paper": {"ink":"#482536","accent":"#bf4d31","pale":"#f4ddac","paper":"#fff8ea"},
    "atlas": {"ink":"#173555","accent":"#b74636","pale":"#bddbea","paper":"#edf6f8"},
}


def compose(clean_path: Path, overlays: list, caption: str, values: dict, anchors: dict, size: tuple[int,int], out: Path, overlay_out: Path, *, theme=None):
    image=Image.open(clean_path).convert("RGB").resize(size,Image.Resampling.LANCZOS)
    layer=Image.new("RGBA",size,(0,0,0,0))
    draw=ImageDraw.Draw(layer)
    w,h=size
    palette=GRAPHIC_THEMES.get(theme, GRAPHIC_THEMES["paper"])
    for item in overlays:
        kind=item.type
        if kind=="segment":
            a=point_of(item.source,anchors,size)
            b=point_of(item.to,anchors,size)
            dx,dy=b[0]-a[0],b[1]-a[1]
            length=math.hypot(dx,dy)
            d=item.divisions
            if length < w*.026 or (d and length/d < w*.023):
                raise NeedsReview("segment or tick spacing is too small at phone size")
            half_tick=round(w*.018)
            width=max(2,round(w*.008))
            gap=half_tick+width
            if any(not gap<=x<w-gap or not gap<=y<h-gap for x,y in (a,b)):
                raise NeedsReview("segment outside safe bounds")
            color=palette[item.ink]
            draw.line((a,b),fill=color,width=width)
            if d:
                tx,ty=-dy/length*half_tick,dx/length*half_tick
                for i in range(d+1):
                    x,y=a[0]+dx*i/d,a[1]+dy*i/d
                    draw.line([(round(x-tx),round(y-ty)),(round(x+tx),round(y+ty))],fill=color,width=width)
        elif kind=="shape":
            if item.shape=="polygon":
                points=[(round(x*w),round(y*h)) for x,y in item.vertices]
                draw.polygon(points,fill=palette[item.ink])
                continue
            cx,cy=point_of(item.at,anchors,size)
            rx,ry=item.extent[0]*w/2,item.extent[1]*h/2
            box=(round(cx-rx),round(cy-ry),round(cx+rx),round(cy+ry))
            if box[0]<1 or box[1]<1 or box[2]>=w-1 or box[3]>=h-1:
                raise NeedsReview("shape outside safe bounds")
            if min(box[2]-box[0],box[3]-box[1])<w*.008:
                raise NeedsReview("shape is too small at phone size")
            draw_fn=draw.ellipse if item.shape=="disc" else draw.rectangle
            draw_fn(box,fill=palette[item.ink])
        elif kind in ("text","label"):
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
                preference={None:.048,"question":.060,"support":.041,"value":.063}
                min_pt=max(12,round(w*.028)) if item.role else 28
                max_pt=max(min_pt,round(w*preference[item.role]))
                max_local_width=min(w*.82,2*min(center[0]-w*.07,w*.93-center[0]))
                for pt in range(max_pt,min_pt-1,-1):
                    font=font_for(text,pt)
                    local_bounds=draw.textbbox(center,text,font=font,anchor="mm")
                    if (draw.textlength(text,font=font)<=max_local_width
                        and h*.04<=local_bounds[1] and local_bounds[3]<=h*.84):
                        break
                else:
                    raise NeedsReview(f"instructional text too wide at phone-legible size: {text!r}")
            bounds=draw.textbbox(center,text,font=font,anchor="mm")
            if bounds[0]<w*.06 or bounds[2]>w*.94 or bounds[1]<h*.04 or bounds[3]>h*.84:
                raise NeedsReview(f"text '{text}' outside safe visual region")
            if item.role and not (isinstance(at,str) and at.endswith(".face")):
                p=max(4,round(w*.010))
                q=max(3,round(w*.007))
                bg=palette["ink"] if item.role=="question" else palette["paper"]
                fg=palette["paper"] if item.role=="question" else palette["ink"]
                draw.rounded_rectangle((bounds[0]-p,bounds[1]-q,bounds[2]+p,bounds[3]+q),
                                       radius=max(2,p//2),fill=bg)
                draw.text(center,text,fill=fg,font=font,anchor="mm")
                if item.role=="value":
                    line_y=bounds[3]+q-1
                    draw.line((bounds[0],line_y,bounds[2],line_y),fill=palette["accent"],width=max(2,q//2))
            elif not (isinstance(at,str) and at.endswith(".face")):
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
