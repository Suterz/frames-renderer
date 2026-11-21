import json
import wave

import pytest
from PIL import Image

from storyboard_renderer import runner
from storyboard_renderer.backends.comfy import BackendError
from storyboard_renderer.schema import Story


def test_second_backend_failure_preserves_first_panel_and_never_publishes(tmp_path, monkeypatch):
    request={
        "schema_version":"1.0","story_id":"error-test","title":"Backend failure",
        "premise":"Two independent scenes","signature":"Art only, no lettering",
        "output":{"width":360,"height":640,"fps":30},
        "audio":{"part":"audio","format":"pcm_s16le","sample_rate":48000,"channels":1},
        "end_ms":2000,
        "cues":[{"id":"one","ms":0,"say":"First."},{"id":"two","ms":1000,"say":"Second."}],
        "panels":[
            {"id":"P01","scene":"first","op":"new_scene","cue":"one","visual":"One apple.","refs":[]},
            {"id":"P02","scene":"second","op":"new_scene","cue":"two","visual":"One pear.","refs":[]}
        ]
    }
    story=Story.model_validate(request)
    (tmp_path/"request.json").write_text(story.model_dump_json())
    with wave.open(str(tmp_path/"narration.wav"),"wb") as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000)
        wav.writeframes(bytes(48000*2))
    monkeypatch.setattr(runner,"ROOT",tmp_path.parent)
    monkeypatch.setattr(runner.ComfyBackend,"ready",lambda self:{"status":"ready"})
    calls=[]
    def fake_render(self,prompt,width,height,seed,out,ref=None):
        calls.append(out)
        if len(calls)==2:raise BackendError("injected second-panel inference failure")
        out.parent.mkdir(parents=True,exist_ok=True)
        Image.new("RGB",(width,height),"#fff3db").save(out)
        return {"mock":True}
    monkeypatch.setattr(runner.ComfyBackend,"render",fake_render)
    with pytest.raises(BackendError,match="injected second-panel"):
        runner.run(tmp_path,{},lambda state:None)
    assert (tmp_path/"clean/P01.png").is_file()
    assert json.loads((tmp_path/"manifest.json").read_text())["panels"][0]["id"]=="P01"
    assert not (tmp_path/"video.mp4").exists()
