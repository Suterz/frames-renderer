from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing import Literal
import math


class Output(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: Literal[24, 25, 30] = 30

    @model_validator(mode="after")
    def aspect(self):
        if self.width < 360 or self.height < 640 or self.width > 2160 or self.height > 3840 or self.width % 2 or self.height % 2 or self.width * 16 != self.height * 9:
            raise ValueError("output must be even, 9:16 and between 360x640 and 2160x3840")
        return self


class Cue(BaseModel):
    id: str
    ms: int = Field(ge=0)
    say: str = ""
    caption: str | None = None


class Overlay(BaseModel):
    type: Literal["text", "arrow", "marker", "label", "segment", "shape"]
    text: str | None = None
    at: str | list[float] | None = None
    source: str | list[float] | None = Field(default=None, alias="from")
    to: str | list[float] | None = None
    divisions: int | None = Field(default=None, ge=1, le=32)
    shape: Literal["rect","disc","polygon"] | None = None
    extent: tuple[float,float] | None = None
    vertices: list[tuple[float,float]] | None = Field(default=None,max_length=24)
    ink: Literal["ink","accent","pale"] = "ink"
    role: Literal["question","value","support"] | None = None
    fact: str | None = Field(default=None, pattern=r"^[a-zA-Z][\w.-]{0,63}$")
    part_target: str | None = Field(default=None,min_length=3,max_length=200)
    part_relation: Literal["touch_surface","inside_region"] = "touch_surface"
    target_region: tuple[float,float,float,float] | None = None
    target_rgb: tuple[int,int,int] | None = None

    @model_validator(mode="after")
    def valid_graphic(self):
        if (self.part_target or self.target_region or self.target_rgb) and self.type!="arrow":
            raise ValueError("part claims apply to arrows")
        if bool(self.target_region)!=bool(self.target_rgb):
            raise ValueError("deterministic part checking requires a region and source color")
        if self.target_region:
            l,t,r,b=self.target_region
            if not (0<=l<r<=1 and 0<=t<b<=1 and all(0<=v<=255 for v in self.target_rgb)):
                raise ValueError("invalid authored target region or RGB")
        if self.type == "shape":
            if self.shape=="polygon":
                if not self.vertices or len(self.vertices)<3 or not all(.02<=x<=.98 and .02<=y<=.98 for x,y in self.vertices):
                    raise ValueError("polygon needs three to twenty-four in-bounds vertices")
                area=abs(sum(x*ny-y*nx for (x,y),(nx,ny) in zip(self.vertices,self.vertices[1:]+self.vertices[:1])))/2
                if area<.0003:
                    raise ValueError("polygon silhouette too small or degenerate")
            elif not self.shape or not self.extent or not all(0 < v <= .9 for v in self.extent):
                raise ValueError("shape needs a valid normalized extent")
        if self.type == "segment" and (self.source is None or self.to is None):
            raise ValueError("segment needs distinct endpoints")
        return self


class Asset(BaseModel):
    kind: Literal["generated_cutout"]
    visual: str
    seed: int = 7
    anchors: dict[str,str | list[float]] = Field(default_factory=dict)
    keep_largest_component: bool = False

    @model_validator(mode="after")
    def asset_anchor_coordinates(self):
        for key,position in self.anchors.items():
            if not key:
                raise ValueError("asset anchor name must not be blank")
            if isinstance(position,str):
                if not position.strip():raise ValueError(f"asset anchor {key!r} has no visual query")
            elif len(position)!=2 or any(not 0<=v<=1 for v in position):
                raise ValueError(f"asset anchor {key!r} needs two normalized numbers in [0,1]")
            elif self.keep_largest_component:
                raise ValueError("matte cleanup can recrop the asset; request semantic anchors instead of fixed local coordinates")
        return self


class DerivedAnchor(BaseModel):
    derive: Literal["edge_toward"]
    of: str
    toward: str


class Panel(BaseModel):
    id: str
    scene: str
    op: Literal["new_scene", "edit_scene", "overlay_only"]
    cue: str
    visual: str
    change: str = ""
    keep: str = ""
    refs: list[str] = Field(default_factory=list)
    overlays: list[Overlay] = Field(default_factory=list)
    seed: int = 42
    # A teaching card can instantiate an approved cutout at exact known positions.
    layout: dict | None = None
    # Generated artwork: object/part descriptions are interpreted by the local grounding model.
    anchors: dict[str, str | DerivedAnchor] = Field(default_factory=dict)
    visual_checks: list[dict[str, str]] = Field(default_factory=list)


class Story(BaseModel):
    schema_version: Literal["1.0"]
    story_id: str
    title: str
    premise: str
    context: str = ""
    signature: str
    output: Output
    audio: dict
    end_ms: int = Field(gt=0)
    cues: list[Cue]
    panels: list[Panel]
    values: dict[str, str | int] = Field(default_factory=dict)
    assets: dict[str, Asset] = Field(default_factory=dict)
    checks: list[dict[str, str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def verify(self):
        if not self.signature.strip() or not self.panels:
            raise ValueError("signature and panels must not be empty")
        for check in self.checks:
            if check.get("kind") != "equal_groups":
                raise ValueError(f"unsupported exact-data check: {check.get('kind')}")
            try:
                total=self.values[check["total_minor"]]
                count=self.values[check["count"]]
                each=self.values[check["each_minor"]]
            except KeyError as exc:
                raise ValueError(f"unknown exact-data reference {exc}") from exc
            if not all(type(n) is int and n>0 for n in (total,count,each)) or total!=count*each:
                raise ValueError("equal_groups: total must equal count * each in integer minor units")
        f = self.output.fps
        n = math.ceil(self.end_ms * f / 1000)
        if self.end_ms >= 45000 or n / f >= 45:
            raise ValueError("video must be strictly shorter than 45 seconds after frame rounding")
        ids = [c.id for c in self.cues]
        if len(ids) != len(set(ids)) or self.cues[0].ms != 0:
            raise ValueError("cue IDs must be unique and first cue must start at zero")
        times = [c.ms for c in self.cues]
        if times != sorted(times) or len(set((t * f + 500) // 1000 for t in times)) != len(times) or times[-1] >= self.end_ms:
            raise ValueError("cue times must increase with distinct encoded frame boundaries before end_ms")
        seen, scenes = set(), set()
        for i, p in enumerate(self.panels):
            if p.id in seen:
                raise ValueError(f"duplicate panel ID {p.id}")
            if p.cue not in ids:
                raise ValueError(f"{p.id}: unknown cue {p.cue}")
            if i == 0 and (p.op != "new_scene" or p.cue != ids[0]):
                raise ValueError("first panel must be new_scene at first cue")
            if p.op == "new_scene":
                if p.scene in scenes or p.refs:
                    raise ValueError(f"{p.id}: new_scene requires new scene ID and no references")
                scenes.add(p.scene)
            else:
                previous = self.panels[i-1]
                if p.scene != previous.scene or p.refs != [previous.id]:
                    raise ValueError(f"{p.id}: continuation must reference immediately preceding panel in same scene")
            for key, desc in p.anchors.items():
                if not key.strip():
                    raise ValueError(f"{p.id}: anchor names must not be blank")
                if isinstance(desc,str) and not desc.strip():
                    raise ValueError(f"{p.id}: anchor descriptions must not be blank")
                if isinstance(desc,DerivedAnchor) and (desc.of==key or desc.toward==key or desc.of not in p.anchors or desc.toward not in p.anchors):
                    raise ValueError(f"{p.id}: derived anchor {key} has missing/circular local reference")
            if p.layout:
                if p.op!="new_scene" or (("asset" in p.layout)==("layers" in p.layout)):
                    raise ValueError(f"{p.id}: controlled layout must be a new_scene with either a repeated asset or layers")
                if "asset" in p.layout:
                    if p.layout["asset"] not in self.assets:
                        raise ValueError(f"{p.id}: unknown controlled asset {p.layout['asset']}")
                    count=p.layout.get("count")
                    if isinstance(count,str):
                        if count not in self.values:raise ValueError(f"{p.id}: unknown controlled count {count}")
                        count=self.values[count]
                    if type(count) is not int or not 1<=count<=5:
                        raise ValueError(f"{p.id}: controlled repeat count must be an integer 1..5")
                else:
                    layers=p.layout["layers"]
                    if not isinstance(layers,list) or not 1<=len(layers)<=12:
                        raise ValueError(f"{p.id}: controlled layers must have 1..12 entries")
                    names=set()
                    for layer in layers:
                        if not isinstance(layer,dict) or layer.get("asset") not in self.assets:
                            raise ValueError(f"{p.id}: controlled layer has unknown asset")
                        if not isinstance(layer.get("id"),str) or layer["id"] in names:
                            raise ValueError(f"{p.id}: controlled layers require unique string IDs")
                        names.add(layer["id"])
                        c=layer.get("center")
                        v=layer.get("width")
                        if (not isinstance(c,list) or len(c)!=2 or
                            any(not isinstance(n,(int,float)) or not 0<n<1 for n in c) or
                            not isinstance(v,(int,float)) or not .05<=v<=.8):
                            raise ValueError(f"{p.id}: layer {layer['id']}: invalid center/width")
            for check in p.visual_checks:
                if not check.get("question") or not check.get("expected"):
                    raise ValueError(f"{p.id}: visual_check requires question and expected")
            seen.add(p.id)
        cue_ms = {c.id: c.ms for c in self.cues}
        bounds = [(cue_ms[p.cue] * f + 500) // 1000 for p in self.panels]
        if bounds != sorted(bounds) or len(bounds) != len(set(bounds)) or bounds[-1] >= n:
            raise ValueError("panel holds must each contain at least one video frame")
        return self
