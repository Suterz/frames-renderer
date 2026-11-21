import pytest
from PIL import Image

from storyboard_renderer.compose import layered_scene
from storyboard_renderer.frame_api import Panel, Session
from storyboard_renderer.frame_engine import geometry
from storyboard_renderer.grounding import NeedsReview


def test_audio_independent_contract():
    s = Session(story_context="one orange", visual_signature="plum ink")
    assert "audio" not in s.model_dump()
    p = dict(key="A", op="edit_scene", scene_id="scene", objective="test", instruction="change expression")
    with pytest.raises(ValueError, match="require one"):
        Panel(**p)


def test_compose_checks_direction_and_raster():
    a = {"a.center": {"point": [80, 100]}, "b.center": {"point": [260, 100]}}
    alpha = Image.new("L", (360, 640), 0)
    req = {"overlays": [{"type": "arrow", "from": "a.center", "to": "b.center"}],
           "expected_links": [{"from": "b.center", "to": "a.center"}], "clear_of": []}
    with pytest.raises(NeedsReview, match="topology"):
        geometry(req, a, alpha.size, alpha)
    req["expected_links"] = None
    with pytest.raises(NeedsReview, match="rasterized"):
        geometry(req, a, alpha.size, alpha)


def test_tall_sprite_preserves_aspect_and_local_anchor_when_capped(tmp_path):
    img = Image.new("RGBA", (24, 120), "#342672")
    a = layered_scene((360, 640), {"a": img}, [{"id": "one", "asset": "a", "center": [.5, .15],
                      "width": .4, "max_height": .15}], {"a": {"tip": [.5, .1]}}, tmp_path / "out.png")
    x0, y0, x1, y1 = a["one.center"]["box"]
    assert y1 - y0 == 96 and x1 - x0 == 19
    assert a["one.tip"]["point"] == (180, 58) or a["one.tip"]["point"] == (181, 58)
