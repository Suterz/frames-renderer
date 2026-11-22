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
