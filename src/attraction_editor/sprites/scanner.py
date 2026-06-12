"""Discovers and validates the dir{0-3}_f{NNNN}.png frame sets used by the
rotation-family sprite layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from attraction_editor.model.project import DIRECTIONS, RideProject


class FrameSetError(Exception):
    """Raised when a sprite directory doesn't match the expected frame layout."""


@dataclass
class FrameSetInfo:
    sprite_dir: Path
    frames_per_dir: int
    width: int
    height: int


def frame_path(sprite_dir: Path, direction: int, frame: int) -> Path:
    return sprite_dir / f"dir{direction}_f{frame:04d}.png"


def scan_frame_set(sprite_dir: Path, frames_per_dir: int) -> FrameSetInfo:
    """Verify that sprite_dir contains dir0..3_f0000..{frames_per_dir-1}.png,
    all with the same dimensions, and return that common size.

    Raises FrameSetError on any missing frame or dimension mismatch.
    """
    width: int | None = None
    height: int | None = None

    for direction in range(DIRECTIONS):
        for frame in range(frames_per_dir):
            path = frame_path(sprite_dir, direction, frame)
            if not path.is_file():
                raise FrameSetError(f"Missing frame: {path}")

            with Image.open(path) as img:
                w, h = img.size

            if width is None:
                width, height = w, h
            elif (w, h) != (width, height):
                raise FrameSetError(
                    f"Dimension mismatch in {sprite_dir}: {path.name} is {w}x{h}, "
                    f"expected {width}x{height}"
                )

    assert width is not None and height is not None
    return FrameSetInfo(sprite_dir=sprite_dir, frames_per_dir=frames_per_dir, width=width, height=height)


def scan_project(project: RideProject) -> dict[str, FrameSetInfo]:
    """Scan the core sprite set and every car's rider-overlay set.

    Returns a dict mapping "Core" / car.name -> FrameSetInfo. Raises
    FrameSetError on the first problem found.
    """
    if project.project_dir is None:
        raise FrameSetError("RideProject.project_dir is not set")

    results: dict[str, FrameSetInfo] = {}

    core_dir = project.project_dir / project.core_sprite_dir
    results["Core"] = scan_frame_set(core_dir, project.frames_per_dir)

    for car in project.cars:
        car_dir = project.project_dir / car.sprite_dir
        results[car.name] = scan_frame_set(car_dir, project.frames_per_dir)

    return results
