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


def build_manifest(project: RideProject, structure_frame_dir: str | Path) -> list[dict]:
    """Return the manifest entry list for `project`, in the same order
    `openrct2-cli sprite build` will assign image indices: 3 thumbnails,
    then the structure (dir0..3 x f0000..{frames_per_dir-1}, read from
    `structure_frame_dir` - the already-composited Layer stack, not any one
    layer's raw source), then each car in project.cars in order, same frame
    layout.
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

    # Tab thumbnails reuse the first composited structure frame, dir0 anchor.
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
