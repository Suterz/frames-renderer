"""Prove a named, controlled graphic actually survives into the phone raster."""
from PIL import Image,ImageChops
from .compose import compose
from .grounding import NeedsReview


def phone(im):
    return im.convert("RGB").resize((360,640),Image.Resampling.LANCZOS)


def inspect_facts(base, composed, overlays, values, anchors, size, theme, dest):
    required=[o for o in overlays if o.fact]
    if not required:
        return {}
    if len({o.fact for o in required})!=len(required):
        raise NeedsReview("named visual facts must be unique in each panel")
    with Image.open(composed) as im:
        actual=phone(im)
    source=dest/"fact-base.png"
    base.save(source)
    results={}
    for index,o in enumerate(overlays):
        if not o.fact:
            continue
        view=dest/f"fact-{o.fact}.png"
        bg_file=dest/"fact-prefix.png"
        # Use the actual layout *under this mark*. Sampling only over blank
        # paper invents different anti-aliased edge colors over filled regions.
        compose(source,overlays[:index],"",values,anchors,size,bg_file,dest/"fact-prefix-mask.png",theme=theme)
        with Image.open(bg_file) as im:
            bg=phone(im)
        compose(source,overlays[:index+1],"",values,anchors,size,view,dest/f"fact-{o.fact}-mask.png",theme=theme)
        with Image.open(view) as im:
            expected=phone(im)
        box=ImageChops.difference(expected,bg).getbbox()
        if not box:
            raise NeedsReview(f"visual fact {o.fact} has no visible pixels")
        changed=kept=0
        for a,b,c in zip(expected.crop(box).getdata(),bg.crop(box).getdata(),actual.crop(box).getdata()):
            if sum(abs(x-y) for x,y in zip(a,b))>=46:
                changed+=1
                if sum(abs(x-y) for x,y in zip(a,c))<=38:
                    kept+=1
        if changed<16 or kept<changed*.83:
            raise NeedsReview(f"visual fact {o.fact} is obscured or too small at phone size")
        results[o.fact]={"bbox":list(box),"visible_fraction":round(kept/changed,3),"type":o.type}
    return results
