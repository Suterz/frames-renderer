#!/usr/bin/env python3
"""Authoring-only local TTS: derive cue onsets from the same speech chunks saved to WAV."""
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

from piper import PiperVoice
from piper.config import SynthesisConfig

folder=Path(sys.argv[1]).resolve()
data=json.loads((folder/"story.json").read_text())
if data["story_id"]=="one-bag-three-oranges":
    sentences=[
        ("q","Mara spots a six-dollar tag."),
        ("ask","Is that for one orange?"),
        ("tied","The tag is tied to the whole bag."),
        ("total","Six dollars is the total."),
        ("think","So what would just one orange cost?"),
        ("three","There are three oranges inside."),
        ("divide","Share the six dollars equally across all three."),
        ("each","That's two dollars per orange."),
        ("name","The price for one?"),
        (None,"That's the unit price.")
    ]
elif data["story_id"]=="button-controller-lamp":
    sentences=[
        ("first","Press a button."),
        ("send","The controller receives a signal,"),
        ("on","and then it switches the lamp on."),
        ("detail","The button doesn't power the lamp directly."),
        ("last","It tells the controller what to do.")
    ]
elif data["story_id"]=="apple-into-basket":
    sentences=[
        ("start","An apple sits beside a basket."),
        ("arrow","A precise arrow points into the opening, not at the rim.")
    ]
else:raise ValueError("authoring script supports the bundled example recordings only")
voice=PiperVoice.load(str(Path.home()/"ai/voices/ljspeech-high/ljspeech.onnx"),include_alignments=True)
rate=voice.config.sample_rate
offset=0
cue_ms={}
phonemes={}
silence=round(rate*.12)
raw=folder/"voice-raw.wav"
with wave.open(str(raw),"wb") as wav:
    wav.setframerate(rate);wav.setsampwidth(2);wav.setnchannels(1)
    for i,(cue,text) in enumerate(sentences):
        if cue:cue_ms[cue]=round(offset*1000/rate)
        parts=list(voice.synthesize(text,syn_config=SynthesisConfig(length_scale=1.18),include_alignments=True))
        if len(parts)!=1:raise RuntimeError(f"expected one sentence chunk for {text!r}; got {len(parts)}")
        chunk=parts[0]
        if not chunk.phoneme_alignments:raise RuntimeError("phoneme alignment unavailable for this voice")
        if data["story_id"]=="one-bag-three-oranges" and cue=="tied":
            spaces=0
            prefix=0
            for alignment in chunk.phoneme_alignments:
                if alignment.phoneme==" ":
                    spaces+=1
                    if spaces==5:
                        cue_ms["bag"]=round((offset+prefix+alignment.num_samples)*1000/rate)
                        break
                prefix+=int(alignment.num_samples)
            if "bag" not in cue_ms:raise RuntimeError("cannot align the mid-sentence bag reveal")
        if data["story_id"]=="button-controller-lamp" and cue=="on":
            spaces=0
            prefix=0
            for alignment in chunk.phoneme_alignments:
                if alignment.phoneme==" ":
                    spaces+=1
                    if spaces==5:
                        cue_ms["lamp"]=round((offset+prefix+alignment.num_samples)*1000/rate)
                        break
                prefix+=int(alignment.num_samples)
            if "lamp" not in cue_ms:raise RuntimeError("cannot align the lamp state change to its spoken word")
        wav.writeframes(chunk.audio_int16_bytes)
        offset+=len(chunk.audio_int16_bytes)//2
        if i<len(sentences)-1:
            wav.writeframes(bytes(silence*2))
            offset+=silence
media=Path.home()/"ai/tools/media/bin"
subprocess.run([str(media/"ffmpeg"),"-hide_banner","-loglevel","error","-y","-i",str(raw),
                "-ac","1","-ar","48000","-acodec","pcm_s16le",str(folder/"narration.wav")],check=True)
for c in data["cues"]:
    if c["id"] not in cue_ms:raise ValueError(f"missing recording cue {c['id']}")
    c["ms"]=cue_ms[c["id"]]
duration=offset/rate
data["end_ms"]=round((duration+2.35)*1000)
if data["end_ms"]>=30000:raise ValueError("example recording exceeded 29 second target")
(folder/"story.json").write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n")
(folder/"transcript.txt").write_text(" ".join(x[1] for x in sentences)+"\n")
(folder/"cue-evidence.json").write_text(json.dumps({"method":"Piper alignment from exact synthesized chunks","voice":"LJSpeech high ONNX","length_scale":1.18,"sentence_silence":0.12,"cues_ms":cue_ms,"speech_seconds":duration,"end_ms":data["end_ms"]},indent=2))
print(json.dumps({"speech_seconds":round(duration,3),"video_end_seconds":data["end_ms"]/1000,"cues_ms":cue_ms},indent=2))
