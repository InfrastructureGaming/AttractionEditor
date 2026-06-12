"""Data model for a rotation-family ride project (.ridepkg.json)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DIRECTIONS = 4


@dataclass
class DirectionAnchor:
    x: int
    y: int


@dataclass
class CarConfig:
    name: str
    sprite_dir: str  # path relative to project_dir, e.g. "Frames/Riders/Car0"


@dataclass
class RideProject:
    """A rotation-family ride: animated core structure plus N rider-overlay cars,
    each rendered as 4 directions x frames_per_dir frames."""

    id: str
    name: str
    description: str
    category: str
    frames_per_dir: int
    sprite_width: int
    sprite_height_negative: int
    sprite_height_positive: int
    anchors: list[DirectionAnchor]
    core_sprite_dir: str  # path relative to project_dir, e.g. "Frames/Core"
    cars: list[CarConfig] = field(default_factory=list)
    body_colour: str = "white"
    trim_colour: str = "white"
    output_name: str = ""
    deploy_dir: str | None = None
    openrct2_cli_path: str | None = None

    project_dir: Path | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if len(self.anchors) != DIRECTIONS:
            raise ValueError(f"RideProject requires exactly {DIRECTIONS} anchors, got {len(self.anchors)}")
        if not self.output_name:
            self.output_name = self.id

    @property
    def rotation_frame_mask(self) -> int:
        return self.frames_per_dir - 1

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("project_dir")
        return data

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=4), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> RideProject:
        data = json.loads(path.read_text(encoding="utf-8"))
        anchors = [DirectionAnchor(**a) for a in data.pop("anchors")]
        cars = [CarConfig(**c) for c in data.pop("cars", [])]
        return cls(
            anchors=anchors,
            cars=cars,
            project_dir=path.parent,
            **data,
        )
