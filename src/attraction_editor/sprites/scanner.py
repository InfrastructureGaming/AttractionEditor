"""Discovers and validates the dir{0-3}_f{NNNN}.png frame sets used by the
rotation-family sprite layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from attraction_editor.model.project import DIRECTIONS, Layer, RideProject


class FrameSetError(Exception):
    """Raised when a sprite directory doesn't match the expected frame layout."""


@dataclass
class FrameSetInfo:
    sprite_dir: Path
    frames_per_dir: int
    width: int
    height: int


def frame_path(sprite_dir: Path, direction: int, frame: int) -> Path:
    """Animated-layer/car frame file: one of frames_per_dir per direction."""
    return sprite_dir / f"dir{direction}_f{frame:04d}.png"


def static_frame_path(sprite_dir: Path, direction: int) -> Path:
    """Static-layer frame file: exactly one per direction. Reuses frame_path's
    dir{d}_f0000.png naming (just frame 0) rather than a separate filename
    convention - a renderer exports the same way whether a layer animates or
    not, so there's no reason to require a different name for the one case
    where there's only a single frame."""
    return frame_path(sprite_dir, direction, 0)


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


def scan_static_layer(sprite_dir: Path) -> FrameSetInfo:
    """Verify that sprite_dir contains dir0..3.png, all with the same
    dimensions, and return that common size (frames_per_dir=1: a static
    layer has nothing to animate, so there's exactly one frame per direction).

    Raises FrameSetError on any missing file or dimension mismatch.
    """
    width: int | None = None
    height: int | None = None

    for direction in range(DIRECTIONS):
        path = static_frame_path(sprite_dir, direction)
        if not path.is_file():
            raise FrameSetError(f"Missing frame: {path}")

        with Image.open(path) as img:
            w, h = img.size

        if width is None:
            width, height = w, h
        elif (w, h) != (width, height):
            raise FrameSetError(
                f"Dimension mismatch in {sprite_dir}: {path.name} is {w}x{h}, expected {width}x{height}"
            )

    assert width is not None and height is not None
    return FrameSetInfo(sprite_dir=sprite_dir, frames_per_dir=1, width=width, height=height)


def scan_layer(project_dir: Path, layer: Layer, frames_per_dir: int) -> FrameSetInfo:
    """Dispatch to scan_frame_set (animated) or scan_static_layer (static)
    for `layer`, resolving its sprite_dir relative to `project_dir`."""
    layer_dir = project_dir / layer.sprite_dir
    if layer.kind == "static":
        return scan_static_layer(layer_dir)
    return scan_frame_set(layer_dir, frames_per_dir)


def scan_project(project: RideProject) -> dict[str, FrameSetInfo]:
    """Scan every structure layer and every car's rider-overlay set.

    Returns a dict mapping layer.name / car.name -> FrameSetInfo. Raises
    FrameSetError on the first problem found, or if layers disagree on
    sprite dimensions (compositing requires every layer to share one canvas
    size per direction).
    """
    if project.project_dir is None:
        raise FrameSetError("RideProject.project_dir is not set")

    results: dict[str, FrameSetInfo] = {}

    reference_size: tuple[int, int] | None = None
    reference_name: str | None = None
    for layer in project.layers:
        info = scan_layer(project.project_dir, layer, project.frames_per_dir)
        results[layer.name] = info
        size = (info.width, info.height)
        if reference_size is None:
            reference_size, reference_name = size, layer.name
        elif size != reference_size:
            raise FrameSetError(
                f"Layer {layer.name!r} is {size[0]}x{size[1]}, but layer {reference_name!r} "
                f"is {reference_size[0]}x{reference_size[1]} - all layers must share one canvas "
                "size per direction so they can be composited together"
            )

    for car in project.cars:
        car_dir = project.project_dir / car.sprite_dir
        results[car.name] = scan_frame_set(car_dir, project.frames_per_dir)

    return results
