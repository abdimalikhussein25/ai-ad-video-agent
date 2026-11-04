from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

STYLES = ("hook", "feature", "proof", "offer", "cta")


@dataclass
class Brief:
    product: str
    description: str
    audience: str = "everyone"
    price: str | None = None
    offer: str | None = None
    cta: str = "Order now"
    contact: str | None = None
    language: str = "en"  # "en" or "so"
    brand_color: str = "#14382d"
    accent_color: str = "#f2a93b"
    duration: int = 20  # seconds, target

    @classmethod
    def load(cls, path: str | Path) -> "Brief":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        brief = cls(**known)
        brief.validate()
        return brief

    def validate(self) -> None:
        if not self.product.strip() or not self.description.strip():
            raise ValueError("brief needs a product and a description")
        if self.language not in ("en", "so"):
            raise ValueError("language must be 'en' or 'so'")
        if not 8 <= self.duration <= 60:
            raise ValueError("duration must be 8–60 seconds")
        for c in (self.brand_color, self.accent_color):
            if not (c.startswith("#") and len(c) == 7):
                raise ValueError(f"colour {c!r} must look like #RRGGBB")


@dataclass
class Scene:
    style: str
    headline: str
    subtext: str = ""
    voiceover: str = ""
    seconds: float = 3.0

    def __post_init__(self):
        if self.style not in STYLES:
            raise ValueError(f"unknown scene style {self.style!r}")
        self.headline = self.headline.strip()[:60]
        self.subtext = self.subtext.strip()[:90]
        self.seconds = float(max(1.5, min(8.0, self.seconds)))


@dataclass
class Script:
    scenes: list[Scene] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return sum(s.seconds for s in self.scenes)

    @classmethod
    def from_dict(cls, data: dict) -> "Script":
        scenes = [Scene(**{k: v for k, v in s.items() if k in Scene.__dataclass_fields__}) for s in data["scenes"]]
        if not 3 <= len(scenes) <= 8:
            raise ValueError("a script needs 3–8 scenes")
        if scenes[-1].style != "cta":
            raise ValueError("the last scene must be a call to action")
        return cls(scenes)

    def to_dict(self) -> dict:
        return {"scenes": [s.__dict__ for s in self.scenes]}
