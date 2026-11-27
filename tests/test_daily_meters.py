from PIL import Image, ImageChops

from storyboard_renderer.daily_visual import exact


def test_meter_focus_changes_only_the_selected_reading(tmp_path):
    meters = [{"object": name, "readings": [
        {"label": "Energy returned", "display": value, "focus": False},
        {"label": "Energy put in", "display": "?", "focus": False},
    ]} for name, value in (("Battery A", "75 kWh"), ("Battery B", "48 kWh"))]
    before, after = (tmp_path / f"{name}.png" for name in ("before", "after"))
    exact({"operation": "meters", "meters": meters}, (720, 1280), before)
    meters[1]["readings"][0]["focus"] = True
    result = exact({"operation": "meters", "meters": meters}, (720, 1280), after)
    with Image.open(before) as a, Image.open(after) as b:
        change = ImageChops.difference(a, b).getbbox()
    assert change and change[0] > 360
    assert change[3] < 540  # The next reading starts at 563 px.
    assert all(meter["readings"][1]["display"] == "?" for meter in result["proof"]["meters"])
