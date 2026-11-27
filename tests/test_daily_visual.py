import pytest

from storyboard_renderer.daily_visual import documentary, exact
from storyboard_renderer.grounding import NeedsReview


def test_projection_preserves_vertices_across_routes(tmp_path):
    vertices = [[-25, 38], [25, 38], [25, 70], [-25, 70]]
    target = tmp_path / "projection.png"
    report = exact({"operation": "projection", "vertices": vertices}, (360, 640), target)
    proof = report["proof"]
    assert proof["shared_vertices"] == vertices
    mercator, equal_area = proof["projections"].values()
    assert [x for x, _ in mercator] == [x for x, _ in equal_area]
    assert [y for _, y in mercator] != [y for _, y in equal_area]
    assert target.is_file()


def test_documentary_refuses_uncleared_original(tmp_path, monkeypatch):
    monkeypatch.setenv("DAILY_ASSET_CACHE", str(tmp_path))
    monkeypatch.delenv("DAILY_IMAGE_DISCOVERY", raising=False)
    (tmp_path / "catalog.json").write_text('{"earth":{"rights":{"commercial_editorial":false}}}')
    with pytest.raises(NeedsReview, match="rights and attribution"):
        documentary({"subject": "earth"}, (360, 640), tmp_path / "photo.png")
    assert not (tmp_path / "photo.png").exists()
