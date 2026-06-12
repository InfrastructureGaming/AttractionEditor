"""Shared fixture: a RideProject matching the shipped TiltAWhirl project,
used to validate the generalized pipeline against known-good output."""

from __future__ import annotations

from pathlib import Path

from attraction_editor.model.project import CarConfig, DirectionAnchor, RideProject

TILT_A_WHIRL_DIR = Path("G:/GAME DESIGN/OPENRCT2/OpenRCT Custom Rides/TiltAWhirl")

# Locked-in per-direction anchors (see project_flat_ride memory, confirmed 2026-06-12).
ANCHORS = [
    DirectionAnchor(-138, -77),
    DirectionAnchor(-137, -95),
    DirectionAnchor(-112, -95),
    DirectionAnchor(-112, -77),
]


def make_tilt_a_whirl_project(project_dir: Path = TILT_A_WHIRL_DIR) -> RideProject:
    return RideProject(
        id="openrct2dev.ride.tilt_a_whirl",
        name="Tilt-A-Whirl",
        description="A spinning circular platform with independently rotating gondola cars.",
        category="thrill",
        frames_per_dir=128,
        sprite_width=122,
        sprite_height_negative=85,
        sprite_height_positive=85,
        anchors=list(ANCHORS),
        core_sprite_dir="Frames/Core",
        cars=[CarConfig(name=f"Car{i}", sprite_dir=f"Frames/Riders/Car{i}") for i in range(7)],
        body_colour="bright_red",
        trim_colour="white",
        project_dir=project_dir,
    )
