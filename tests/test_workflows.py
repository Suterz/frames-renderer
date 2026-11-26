import json
from pathlib import Path

import pytest

from storyboard_renderer.backends.comfy import flux_graph


@pytest.mark.parametrize(("mode", "reference"), (("new-scene", None), ("edit-scene", "REFERENCE.png")))
def test_versioned_flux_template_matches_submitted_graph(mode, reference):
    root = Path(__file__).resolve().parents[1]
    template = root / "workflows/comfy" / f"flux2-klein-bf16.{mode}.api.json"
    graph = flux_graph("INJECT_AUTHOR_SIGNATURE_AND_VISUAL_INSTRUCTION", 864, 1536, 42, reference)
    assert json.loads(template.read_text()) == graph
