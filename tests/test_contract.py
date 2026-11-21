import json
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from storyboard_renderer.compose import compose, controlled_scene, layered_scene, font_for
from storyboard_renderer.grounding import derive_edge
from storyboard_renderer.schema import Story, Overlay

EXAMPLE=Path(__file__).resolve().parents[1]/"examples/unit-price/story.json"


def data():
    return json.loads(EXAMPLE.read_text())


def test_exact_duration_boundary():
    valid=data()
    valid["end_ms"]=44966
    Story.model_validate(valid)
    for ms in (44999,45000):
        invalid=data()
        invalid["end_ms"]=ms
        with pytest.raises(ValueError,match="45 seconds"):
            Story.model_validate(invalid)


def test_reject_unknown_reference_and_bad_order():
    invalid=data()
    invalid["panels"][1]["refs"]=["P99"]
    with pytest.raises(ValueError,match="immediately preceding"):
        Story.model_validate(invalid)
    invalid=data()
    invalid["panels"][1]["cue"]="missing"
    with pytest.raises(ValueError,match="unknown cue"):
        Story.model_validate(invalid)


def test_overlay_pixel_identical_outside_mask(tmp_path):
    clean=tmp_path/"clean.png"
    Image.new("RGB",(360,640),"#fff3db").save(clean)
    before=tmp_path/"before.png"; after=tmp_path/"after.png"
    layer=tmp_path/"layer.png"
    compose(clean,[],"",{}, {},(360,640),before,tmp_path/"empty.png")
    compose(clean,[Overlay(type="arrow",**{"from":[.17,.28],"to":[.7,.42]})],"",{}, {},(360,640),after,layer)
    a=Image.open(before).convert("RGB");b=Image.open(after).convert("RGB")
    diff=ImageChops.difference(a,b)
    mask=Image.open(layer).getchannel("A").point(lambda x:255 if x else 0)
    assert diff.getbbox() is not None
    inverse=mask.point(lambda x:0 if x else 255)
    assert ImageChops.multiply(diff.convert("L"),inverse).getbbox() is None


def test_controlled_layout_exact_instances(tmp_path):
    sprite=Image.new("RGBA",(100,100),(255,130,10,255))
    p=tmp_path/"scene.png"
    anchors=controlled_scene((1080,1920),sprite,3,p)
    assert sorted(k for k in anchors if k.endswith(".center"))==["orange_1.center","orange_2.center","orange_3.center"]
    assert len({anchors[k]["point"] for k in anchors if k.endswith(".center")})==3


def test_missing_glyph_uses_known_available_font():
    assert "DejaVuSans-Bold" in font_for("BUTTON → LAMP",52).path
    assert "NotoSans-Bold" in font_for("$6 ÷ 3 = $2",52).path
    from storyboard_renderer.grounding import NeedsReview
    with pytest.raises(NeedsReview,match="unsupported glyph"):
        font_for("Unmapped \U0010ffff",52)


def test_derived_tag_edge_and_no_manual_coordinates():
    story=Story.model_validate(data())
    derived=story.panels[0].anchors["tag.exit"]
    assert derived.derive=="edge_toward"
    anchor=derive_edge({"point":(820,800),"box":(750,740,890,910),"source_hash":"hash"},
                       {"point":(430,1030)},derived.of,derived.toward)
    assert anchor["point"][0]==750
    assert 740<=anchor["point"][1]<=910
    assert anchor["method"].startswith("derived geometry")


def test_long_instructional_label_shrinks_instead_of_clipping(tmp_path):
    clean=tmp_path/"clean.png"
    Image.new("RGB",(1080,1920),"#fff3db").save(clean)
    compose(clean,[Overlay(type="text",text="BUTTON   →   CONTROLLER   →   LAMP",at="safe.top")],
            "",{},{},(1080,1920),tmp_path/"ok.png",tmp_path/"label-layer.png")
    assert (tmp_path/"ok.png").exists()


def test_asset_local_named_anchor_follows_repositioned_basket(tmp_path):
    apple=Image.new("RGBA",(100,100),(241,60,50,255))
    basket=Image.new("RGBA",(100,130),(174,107,57,255))
    assets={"apple":apple,"basket":basket}
    specifications={"basket":{"opening":[.5,.2]}}
    layers=[{"id":"apple_2","asset":"apple","center":[.22,.5],"width":.2},
            {"id":"basket","asset":"basket","center":[.73,.5],"width":.28}]
    first=layered_scene((1080,1920),assets,layers,specifications,tmp_path/"first.png")
    assert "basket.opening" in first and "apple_2.center" in first
    assert first["basket.opening"]["point"][0]==first["basket.center"]["point"][0]
    compose(tmp_path/"first.png",[Overlay(type="arrow",**{"from":"apple_2.center","to":"basket.opening"})],
        "",{},first,(1080,1920),tmp_path/"arrow.png",tmp_path/"arrow-layer.png")
    layers[1]["center"]=[.78,.5]
    second=layered_scene((1080,1920),assets,layers,specifications,tmp_path/"second.png")
    assert second["basket.opening"]["point"][0]-first["basket.opening"]["point"][0]==round(.05*1080)
    assert first["basket.opening"]["point"][1]==second["basket.opening"]["point"][1]


def test_invalid_controlled_asset_rejected_before_gpu_call():
    invalid=data()
    invalid["panels"][3]["layout"]["asset"]="unknown"
    with pytest.raises(ValueError,match="unknown controlled asset"):
        Story.model_validate(invalid)
