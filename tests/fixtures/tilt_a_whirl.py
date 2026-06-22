"""Shared fixture: a RideProject matching the shipped TiltAWhirl project,
used to validate the generalized pipeline against known-good output."""

from __future__ import annotations

from pathlib import Path

from attraction_editor.model.project import (
    AnimationPhase,
    AnimationProgram,
    CarConfig,
    ColourScheme,
    DirectionAnchor,
    Layer,
    RideProject,
)

TILT_A_WHIRL_DIR = Path("G:/GAME DESIGN/OPENRCT2/OpenRCT Custom Rides/TiltAWhirl")

# Locked-in per-direction anchors (see project_flat_ride memory, confirmed 2026-06-12).
ANCHORS = [
    DirectionAnchor(-138, -77),
    DirectionAnchor(-137, -95),
    DirectionAnchor(-112, -95),
    DirectionAnchor(-112, -77),
]

# Matches the flatRideAnimation programs in object.json: three distinct,
# non-overlapping 128-frame ranges within the combined 384-frame Core_Anim_0
# sequence - Start (0-127) -> Spin (128-255, repeat until rotations done) ->
# End (256-383). Confirmed against the real asset directory 2026-06-22.
PROGRAMS = [
    AnimationProgram(
        name="Normal",
        phases=[
            AnimationPhase(name="Start", frame_start=0, frame_count=128, ticks_per_frame=3, next_phase=1),
            AnimationPhase(
                name="Spin",
                frame_start=128,
                frame_count=128,
                ticks_per_frame=1,
                next_phase=2,
                repeat_until_rotations_complete=True,
            ),
            AnimationPhase(name="End", frame_start=256, frame_count=128, ticks_per_frame=3, is_final_phase=True),
        ],
    ),
]


def make_tilt_a_whirl_project(project_dir: Path = TILT_A_WHIRL_DIR) -> RideProject:
    return RideProject(
        id="openrct2dev.ride.tilt_a_whirl",
        name="Tilt-A-Whirl",
        description="A spinning circular platform with independently rotating gondola cars.",
        category="thrill",
        frames_per_dir=384,
        sprite_width=122,
        sprite_height_negative=85,
        sprite_height_positive=85,
        anchors=list(ANCHORS),
        layers=[
            Layer(name="Core_Static_0", sprite_dir="Frames/Core_Static_0", kind="static"),
            Layer(name="Core_Anim_0", sprite_dir="Frames/Core_Anim_0", kind="animated", dither_algorithm="floyd_steinberg"),
        ],
        cars=[CarConfig(name=f"Car{i}", sprite_dir=f"Frames/Riders/Car{i}") for i in range(7)],
        programs=list(PROGRAMS),
        # Renamed from the old body_colour="bright_red"/trim_colour="white" pair -
        # old body_colour actually fed the Trim zone, old trim_colour fed Tertiary.
        colour_schemes=[ColourScheme(trim_colour="bright_red", tertiary_colour="white")],
        project_dir=project_dir,
    )
