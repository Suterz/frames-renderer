"""Independent source-pixel checks for explicit lesson claims."""
from PIL import Image, ImageChops

from .grounding import NeedsReview


def box_px(box, size):
    return tuple(round(x * size[i % 2]) for i, x in enumerate(box))


def region_claim(clean, overlay, tip, region, rgb, tolerance=32):
    """Check a deterministic target region against the actual source and arrow mask."""
    x, y = tip
    l, t, r, b = box_px(region, clean.size)
    within = l <= x < r and t <= y < b
    if not within or overlay.getpixel(tip) <= 0:
        raise NeedsReview("arrow does not touch the authored target region")
    actual = clean.getpixel(tip)
    if sum(abs(a-b) for a,b in zip(actual,rgb,strict=True)) > tolerance:
        raise NeedsReview("target region not visible at arrow tip in clean source")
    return {"tip":tip,"region_px":[l,t,r,b],"source_rgb":actual}


def movement(before, after, source_box, destination_box, rgb, threshold=.22):
    """Require the same authored object color to vacate and occupy disjoint regions."""
    old = before.convert("RGB")
    new = after.convert("RGB")
    if old.size != new.size or ImageChops.difference(old,new).getbbox() is None:
        raise NeedsReview("claimed action changed only annotation, not the clean scene")
    a,b=box_px(source_box,old.size),box_px(destination_box,old.size)
    if max(a[0],b[0])<min(a[2],b[2]) and max(a[1],b[1])<min(a[3],b[3]):
        raise NeedsReview("movement needs distinct source and destination regions")
    def share(im, box):
        crop=im.crop(box)
        return sum(sum(abs(a-b) for a,b in zip(p,rgb,strict=True)) <= 32 for p in crop.getdata())/(crop.width*crop.height)
    old_source,old_dest=share(old,a),share(old,b)
    new_source,new_dest=share(new,a),share(new,b)
    if min(old_source,new_dest)<threshold or max(old_dest,new_source)>threshold/4:
        raise NeedsReview("claimed object did not visibly move between the two regions")
    return {"source_before":old_source,"source_after":new_source,"destination_before":old_dest,"destination_after":new_dest}


def controlled_transition(before,after,old_anchors,new_anchors,changed,inserted=()):
    """Verify a declared insertion or movement against actual raster patches."""
    snapshots=lambda src:{k.removesuffix(".center"):v for k,v in src.items()
          if k.endswith(".center") and v.get("method")=="controlled geometry" and v.get("asset")}
    a,b=snapshots(old_anchors),snapshots(new_anchors)
    if not a or set(b)-set(a)!=set(inserted) or set(a)-set(b) or not set(changed)<=a.keys():
        raise NeedsReview("controlled transition changed the named instances beyond the declared insertion")
    evidence={}
    for k,old in a.items():
        new=b[k]
        if old["asset"]!=new["asset"] or old.get("flip_x")!=new.get("flip_x"):
            raise NeedsReview(f"{k}: asset identity or orientation changed during movement")
        dx,dy=(new["point"][i]-old["point"][i] for i in range(2))
        before_patch,after_patch=before.crop(tuple(old["box"])),after.crop(tuple(new["box"]))
        if before_patch.size!=after_patch.size or ImageChops.difference(before_patch.convert("RGB"),after_patch.convert("RGB")).getbbox():
            raise NeedsReview(f"{k}: actual drawn cutout changed instead of translating")
        if k in changed:
            if abs(dx)+abs(dy)<max(4,before.size[0]//40):
                raise NeedsReview(f"{k}: missing visible movement")
            evidence[k]={"delta_px":[dx,dy],"source_bbox":old["box"],"destination_bbox":new["box"]}
        elif dx or dy:
            raise NeedsReview(f"{k}: unrelated instance unexpectedly moved")
    if ImageChops.difference(before.convert("RGB"),after.convert("RGB")).getbbox() is None:
        raise NeedsReview("clean layout pixels remained unchanged")
    for key in inserted:
        box=tuple(b[key]["box"])
        before_patch=before.crop(box).convert("RGB")
        after_patch=after.crop(box).convert("RGB")
        if ImageChops.difference(before_patch,after_patch).getbbox() is None:
            raise NeedsReview(f"{key}: declared insertion has no visible new pixels")
        evidence[key]={"inserted_bbox":list(box)}
    return evidence


def count_components(image,region,rgb,minimum,expected,extent_px=None):
    """Count separate actual phone-size silhouettes with a declared fill."""
    phone=image.convert("RGB").resize((360,640),Image.Resampling.LANCZOS)
    l,t,r,b=box_px(region,phone.size)
    crop=phone.crop((l,t,r,b))
    pix=crop.load()
    remaining={(x,y) for y in range(crop.height) for x in range(crop.width)
               if sum(abs(a-b) for a,b in zip(pix[x,y],rgb,strict=True))<=46}
    sizes=[]
    excluded=[]
    while remaining:
        todo=[remaining.pop()]
        for x,y in todo:
            for p in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if p in remaining:
                    remaining.remove(p);todo.append(p)
        if len(todo)>=minimum:
            w=max(x for x,y in todo)-min(x for x,y in todo)+1
            h=max(y for x,y in todo)-min(y for x,y in todo)+1
            if extent_px and any(abs(a-b)>max(3,b*.20) for a,b in zip((w,h),extent_px,strict=True)):
                excluded.append([w,h])
            else:
                sizes.append(len(todo))
    if len(sizes)!=expected:
        raise NeedsReview(f"phone-size raster shows {len(sizes)} visible components, expected {expected}")
    return {"count":len(sizes),"area_px":sorted(sizes),"region_px":[l,t,r,b],"excluded_extents":excluded}


def check_path(image, region, rgb, start, end, connected):
    """Check visible ink continuity within a stated region of the phone raster."""
    phone = image.convert("RGB").resize((360, 640), Image.Resampling.LANCZOS)
    l,t,r,b = box_px(region, phone.size)
    crop = phone.crop((l,t,r,b))
    pix = crop.load()
    ink = {(x,y) for y in range(b-t) for x in range(r-l)
           if sum(abs(a-b) for a,b in zip(pix[x,y],rgb,strict=True)) <= 46}

    def endpoint(p):
        x,y = (round(p[0]*phone.width)-l, round(p[1]*phone.height)-t)
        return {(x+dx,y+dy) for dx in range(-3,4) for dy in range(-3,4)
                if dx*dx+dy*dy<=9 and (x+dx,y+dy) in ink}

    sources, targets = endpoint(start), endpoint(end)
    if not sources or not targets:
        raise NeedsReview("path claim requires both endpoints to remain visibly inked")
    visited=set(sources)
    queue=list(sources)
    for x,y in queue:
        if (x,y) in targets:
            break
        for candidate in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if candidate in ink and candidate not in visited:
                visited.add(candidate)
                queue.append(candidate)
    actual = not visited.isdisjoint(targets)
    if actual != connected:
        raise NeedsReview(f"phone-size path is {'connected' if actual else 'broken'}, expected {'connected' if connected else 'broken'}")
    return {"connected":actual,"region_px":[l,t,r,b],"endpoints":[start,end],
            "endpoint_pixels":[len(sources),len(targets)]}
