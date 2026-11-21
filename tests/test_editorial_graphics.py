"""Regression: arrows with rings are not a ruler; arrows are not data bars."""
from PIL import Image
import pytest

from storyboard_renderer.compose import compose
from storyboard_renderer.grounding import NeedsReview
from storyboard_renderer.schema import Overlay


def render(tmp_path, items):
    src = tmp_path/"clean.png"
    Image.new("RGB",(360,640),"#fff8e8").save(src)
    dst = tmp_path/"out.png"
    mask = tmp_path/"mask.png"
    compose(src, [Overlay.model_validate(o) for o in items], "", {}, {}, (360,640), dst, mask, theme="atlas")
    return Image.open(mask).getchannel("A")


def test_symmetric_ticks_not_arrowheads(tmp_path):
    alpha = render(tmp_path,[{"type":"segment","from":[.2,.5],"to":[.8,.5],"divisions":2}])
    assert [alpha.getpixel((x,326)) for x in (72,180,288)] == [255]*3
    assert [alpha.getpixel((x,326)) for x in (125,231)] == [0]*2
    assert alpha.getpixel((282,329)) == 0


def test_bar_has_flat_ends_and_proportional_length(tmp_path):
    alpha = render(tmp_path,[{"type":"shape","shape":"rect","at":[.35,.45],"extent":[.30,.06]},
                             {"type":"shape","shape":"rect","at":[.5,.65],"extent":[.60,.06]}])
    runs = [sum(alpha.getpixel((x,y))>0 for x in range(360)) for y in (288,416)]
    assert abs(2*runs[0]-runs[1])<=1
    assert alpha.getpixel((72,278))==255


def test_graphic_cannot_clip_or_fake_tiny_ticks(tmp_path):
    with pytest.raises(NeedsReview,match="outside"):
        render(tmp_path,[{"type":"shape","shape":"rect","at":[.02,.5],"extent":[.20,.08]}])
    with pytest.raises(NeedsReview,match="phone"):
        render(tmp_path,[{"type":"segment","from":[.2,.5],"to":[.23,.5],"divisions":8}])


def test_signature_roles_do_not_require_old_clients_to_change(tmp_path):
    a = render(tmp_path,[{"type":"text","at":[.5,.2],"text":"COMPARE","role":"question"},
                         {"type":"text","at":[.5,.5],"text":"3 FOR $6","role":"value"},
                         {"type":"text","at":[.5,.7],"text":"OLD DEFAULT"}])
    assert a.getbbox()
