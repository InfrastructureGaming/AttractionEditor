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
class AnimationPhase:
    """One phase of an animation program: a time-indexed run through
    [frame_start, frame_start + frame_count) of the ride's combined sprite
    sheet, each frame held for ticks_per_frame ticks.

    Mirrors FlatRideAnimationPhase (RideData.h): next_phase is the phase
    index (within the same program) to advance to when this phase ends.
    repeat_until_rotations_complete replays this phase (NumRotations++) until
    NumRotations >= ride.rotations, then advances to next_phase.
    is_final_phase (when not repeating) ends the program -> Status::arriving.
    """

    name: str
    frame_start: int
    frame_count: int
    ticks_per_frame: int = 1
    next_phase: int = 0
    repeat_until_rotations_complete: bool = False
    is_final_phase: bool = False


@dataclass
class AnimationProgram:
    """A selectable animation program: an ordered/looping graph of phases.

    Mirrors FlatRideAnimationProgram (RideData.h). An empty
    RideProject.programs list means legacy single-program, 3-phase
    Start/Loop/End behaviour (FlatRideRotationDescriptor.Programs == nullptr)."""

    name: str
    phases: list[AnimationPhase] = field(default_factory=list)


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
    # Multi-phase/multi-program animation (see AnimationProgram). Empty = legacy
    # single-program, 3-phase Start/Loop/End behaviour; frames_per_dir is then the
    # per-phase frame count as before. Non-empty = frames_per_dir is the TOTAL
    # combined frame count across every phase of every program.
    programs: list[AnimationProgram] = field(default_factory=list)
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
        programs = [
            AnimationProgram(name=p["name"], phases=[AnimationPhase(**ph) for ph in p["phases"]])
            for p in data.pop("programs", [])
        ]
        return cls(
            anchors=anchors,
            cars=cars,
            programs=programs,
            project_dir=path.parent,
            **data,
        )
