"""Paired controls: a correctly rendered arrow can still point at the wrong part."""
import pytest
from PIL import Image,ImageDraw

from storyboard_renderer.claims import region_claim,movement
from storyboard_renderer.grounding import NeedsReview


def test_adjacent_part_rejected_even_when_both_parts_are_gold():
    src=Image.new("RGB",(100,100),"white")
    d=ImageDraw.Draw(src)
    d.rectangle((25,22,48,38),fill=(195,150,62))
    d.rectangle((25,40,48,68),fill=(195,150,62))
    mask=Image.new("L",src.size)
    for tip in ((36,33),(36,48)):
        ImageDraw.Draw(mask).line(((80,30),tip),fill=255,width=3)
    assert region_claim(src,mask,(36,33),(.25,.22,.49,.39),(195,150,62))
    with pytest.raises(NeedsReview,match="does not touch"):
        region_claim(src,mask,(36,48),(.25,.22,.49,.39),(195,150,62))


def test_moving_annotation_is_not_motion_even_with_changed_composite():
    old=Image.new("RGB",(100,100),"white");after=old.copy()
    token=(25,90,160)
    ImageDraw.Draw(old).rectangle((15,30,30,45),fill=token)
    ImageDraw.Draw(after).rectangle((60,30,75,45),fill=token)
    boxes=(.15,.30,.31,.46),(.60,.30,.76,.46)
    assert movement(old,after,*boxes,token)
    with pytest.raises(NeedsReview,match="only annotation"):
        movement(old,old.copy(),*boxes,token)
    decoy=old.copy()
    ImageDraw.Draw(decoy).rectangle((60,30,75,45),fill="red")
    with pytest.raises(NeedsReview,match="did not visibly move"):
        movement(old,decoy,*boxes,token)


def test_exact_label_next_to_wide_diagram_fits_its_own_safe_region(tmp_path):
    from storyboard_renderer.compose import compose
    from storyboard_renderer.schema import Overlay
    raw=tmp_path/"raw.png";Image.new("RGB",(1080,1920),"white").save(raw)
    label=Overlay(type="text",at=[.78,.66],text="2 DISTANCES",role="value")
    dest=tmp_path/"out.png"; mask=tmp_path/"mask.png"
    compose(raw,[label],"",{}, {},(1080,1920),dest,mask,theme="paper")
    assert Image.open(mask).getchannel("A").getbbox()[2]<1020


def test_value_caption_above_subtitle_reserve_resizes_vertically(tmp_path):
    from storyboard_renderer.compose import compose
    from storyboard_renderer.schema import Overlay
    raw=tmp_path/"raw.png";Image.new("RGB",(1080,1920),"white").save(raw)
    label=Overlay(type="text",at=[.5,.82],text="12 SQUARE UNITS",role="value")
    compose(raw,[label],"",{}, {},(1080,1920),tmp_path/"out.png",tmp_path/"ink.png")
    assert (tmp_path/"out.png").is_file()


def test_named_ticks_detected_over_colored_area_but_not_if_overpainted(tmp_path):
    from storyboard_renderer.compose import compose
    from storyboard_renderer.schema import Overlay
    from storyboard_renderer.fact_evidence import inspect_facts
    sz=(1080,1920)
    base=Image.new("RGB",sz,"#edf6f8")
    source=tmp_path/"source.png";base.save(source)
    paint=Overlay(type="shape",shape="rect",at=[.5,.4],extent=[.55,.3],ink="accent")
    tick=Overlay(type="segment",fact="tick",to=[.36,.49],ink="ink",**{"from":[.36,.29]})
    out=tmp_path/"out.png"
    for glyphs in ([paint,tick],[paint,tick,paint]):
        compose(source,glyphs,"",{}, {},sz,out,tmp_path/"mask.png",theme="atlas")
        if len(glyphs)==2:
            assert inspect_facts(base,out,glyphs,{}, {},sz,"atlas",tmp_path)["tick"]["visible_fraction"]>.95
        else:
            with pytest.raises(NeedsReview,match="obscured"):
                inspect_facts(base,out,glyphs,{}, {},sz,"atlas",tmp_path)


def test_translated_cutout_retains_exact_pixels_and_fixes_annotation_only(tmp_path):
    from storyboard_renderer.compose import layered_scene
    from storyboard_renderer.claims import controlled_transition
    assets={"shape":Image.new("RGBA",(30,50),(200,10,0,255))}
    fixed={"id":"reference","asset":"shape","center":[.7,.6],"width":.12}
    def draw(path,x):
        return layered_scene((360,640),assets,[fixed,{"id":"subject","asset":"shape","center":[x,.4],"width":.14}],{},path)
    a=tmp_path/"a.png";b=tmp_path/"b.png"
    old=draw(a,.25);new=draw(b,.40)
    with Image.open(a) as start,Image.open(b) as end:
        assert controlled_transition(start,end,old,new,["subject"])["subject"]["delta_px"]==[54,0]
        with pytest.raises(NeedsReview,match="missing visible movement"):
            controlled_transition(start,start,old,old,["subject"])
        with pytest.raises(NeedsReview,match="actual drawn cutout changed"):
            controlled_transition(start,start,old,new,["subject"])


def test_count_preserves_separation_and_rejects_an_extra_counter():
    from storyboard_renderer.claims import count_components
    a=Image.new("RGB",(360,640),"white")
    ink=(185,60,30)
    draw=ImageDraw.Draw(a)
    for x in (90,150,210):
        draw.ellipse((x,200,x+18,218),fill=ink)
    assert count_components(a,(.14,.2,.85,.5),ink,80,3)["count"]==3
    draw.ellipse((252,200,270,218),fill=ink)
    with pytest.raises(NeedsReview,match="4 visible"):
        count_components(a,(.14,.2,.85,.5),ink,80,3)
