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


def controlled_transition(before,after,old_anchors,new_anchors,changed):
    """Verify existing recognizable cutouts move, with unchanged scale and orientation."""
    snapshots=lambda src:{k.removesuffix(".center"):v for k,v in src.items()
          if k.endswith(".center") and v.get("method")=="controlled geometry" and v.get("asset")}
    a,b=snapshots(old_anchors),snapshots(new_anchors)
    if not a or a.keys()!=b.keys() or not set(changed)<=a.keys():
        raise NeedsReview("controlled movement requires the same named instances before and after")
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
    return evidence
