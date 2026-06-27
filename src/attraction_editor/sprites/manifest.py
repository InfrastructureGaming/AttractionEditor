"""Builds sprite_manifest.json entries for `openrct2-cli sprite build`.

Generalizes generate_rider_manifest.ps1: 3 tab-thumbnail entries, followed by
the flattened structure's 4 x frames_per_dir frames (the result of
compositing every Layer together - see build.layers.build_composite_frames),
followed by 4 x frames_per_dir frames for each rider-overlay car, every entry
anchored per its camera direction.
"""

from __future__ import annotations

from pathlib import Path

from attraction_editor.model.project import DIRECTIONS, RideProject
from attraction_editor.sprites.scanner import frame_path

THUMBNAIL_COUNT = 3


def build_manifest(
    project: RideProject,
    structure_frame_dir: str | Path,
    thumbnail_path: str | Path | None = None,
) -> list[dict]:
    """Return the manifest entry list for `project`, in the same order
    `openrct2-cli sprite build` will assign image indices: 3 thumbnails,
    then the structure (dir0..3 x f0000..{frames_per_dir-1}, read from
    `structure_frame_dir` - the already-composited Layer stack, not any one
    layer's raw source), then each car in project.cars in order, same frame
    layout.

    `thumbnail_path`, when given, is a pre-fitted 112x112 image (see
    build/thumbnail.py) used for all 3 preview slots and emitted with
    "format": "raw" and offset 0,0. "raw" makes the built sprite flat rather
    than RLE, so it carries G1Flag::hasTransparency and renders through the
    engine's masked New Ride preview path (feathered border, clipped) instead
    of the broken full-frame fallback; offset 0,0 because that masked draw
    aligns the sprite to the mask's top-left and ignores the sprite's own
    offset (the centering is baked into the raster). When None, the slots fall
    back to a copy of composited structure frame 0 at the dir0 anchor - the
    legacy behaviour that renders incorrectly in-game, kept only so a
    thumbnail-less manifest still has the right image count (real builds always
    pass thumbnail_path - see build/sprite_builder.py).
    """
    entries: list[dict] = []

    def add_frame_set(sprite_dir: str | Path, count: int | None = None) -> None:
        n = count if count is not None else project.frames_per_dir
        for direction in range(DIRECTIONS):
            anchor = project.anchors[direction]
            for frame in range(n):
                entries.append(
                    {
                        "path": str(frame_path(Path(sprite_dir), direction, frame)).replace("\\", "/"),
                        "x": anchor.x,
                        "y": anchor.y,
                    }
                )

    if thumbnail_path is not None:
        thumb_path = str(Path(thumbnail_path)).replace("\\", "/")
        for _ in range(THUMBNAIL_COUNT):
            entries.append({"path": thumb_path, "x": 0, "y": 0, "format": "raw"})
    else:
        # Legacy fallback: reuse the first composited structure frame, dir0 anchor.
        thumb_anchor = project.anchors[0]
        thumb_path = str(frame_path(Path(structure_frame_dir), 0, 0)).replace("\\", "/")
        for _ in range(THUMBNAIL_COUNT):
            entries.append({"path": thumb_path, "x": thumb_anchor.x, "y": thumb_anchor.y})

    add_frame_set(structure_frame_dir)

    for car in project.cars:
        add_frame_set(car.sprite_dir)

    return entries


def manifest_image_count(project: RideProject) -> int:
    return THUMBNAIL_COUNT + (1 + len(project.cars)) * DIRECTIONS * project.frames_per_dir
