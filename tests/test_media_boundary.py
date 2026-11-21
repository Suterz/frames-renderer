import wave
from pathlib import Path

from PIL import Image

from storyboard_renderer.runner import encode
from storyboard_renderer.schema import Story


def test_muxed_media_near_45_second_boundary(tmp_path):
    story=Story.model_validate({
        "schema_version":"1.0","story_id":"boundary","title":"Boundary",
        "premise":"Probe muxer rounding","signature":"Plain artwork",
        "output":{"width":360,"height":640,"fps":30},
        "audio":{"part":"audio","format":"pcm_s16le","sample_rate":48000,"channels":1},
        "end_ms":44966,
        "cues":[{"id":"first","ms":0,"say":"A."}],
        "panels":[{"id":"P01","scene":"one","op":"new_scene","cue":"first","visual":"Test","refs":[]}]
    })
    png=tmp_path/"plain.png"
    Image.new("RGB",(360,640),"#fff3db").save(png)
    wav=tmp_path/"short.wav"
    with wave.open(str(wav),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000)
        f.writeframes(bytes(96000))
    meta=encode([png],[(0,1349,0)],story,wav,tmp_path/"near.mp4")
    assert meta["expected_video_frames"]==1349
    assert float(meta["ffprobe"]["format"]["duration"])<45
