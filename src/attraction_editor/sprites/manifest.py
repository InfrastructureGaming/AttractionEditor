"""Builds sprite_manifest.json entries for `openrct2-cli sprite build`.

Generalizes generate_rider_manifest.ps1: 3 tab-thumbnail entries, followed by
the core structure's 4 x frames_per_dir frames, followed by 4 x frames_per_dir
frames for each rider-overlay car, every entry anchored per its camera
direction.
"""

from __future__ import annotations

from pathlib import Path

from attraction_editor.model.project import DIRECTIONS, RideProject
from attraction_editor.sprites.scanner import frame_path

THUMBNAIL_COUNT = 3


def build_manifest(project: RideProject) -> list[dict]:
    """Return the manifest entry list for `project`, in the same order
    `openrct2-cli sprite build` will assign image indices: 3 thumbnails,
    then Core (dir0..3 x f0000..{frames_per_dir-1}), then each car in
    project.cars in order, same frame layout.
    """
    entries: list[dict] = []

    def add_frame_set(sprite_dir: str, count: int | None = None) -> None:
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

    # Tab thumbnails reuse the first core frame, dir0 anchor.
    thumb_anchor = project.anchors[0]
    thumb_path = str(frame_path(Path(project.core_sprite_dir), 0, 0)).replace("\\", "/")
    for _ in range(THUMBNAIL_COUNT):
        entries.append({"path": thumb_path, "x": thumb_anchor.x, "y": thumb_anchor.y})

    add_frame_set(project.core_sprite_dir)

    for car in project.cars:
        add_frame_set(car.sprite_dir)

    return entries


def manifest_image_count(project: RideProject) -> int:
    return THUMBNAIL_COUNT + (1 + len(project.cars)) * DIRECTIONS * project.frames_per_dir
