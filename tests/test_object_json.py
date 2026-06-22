"""Tests for build/object_json.py: images range, flatRideAnimation block,
colour_schemes_block (properties.carColours), and update_object_json (all
three in one pass)."""

from __future__ import annotations

import json

import pytest

from attraction_editor.build.object_json import (
    colour_schemes_block,
    flat_ride_animation_block,
    images_range_string,
    update_object_json,
)
from attraction_editor.model.project import AnimationPhase, AnimationProgram, ColourScheme
from tests.fixtures.synthetic import make_synthetic_project
from tests.fixtures.tilt_a_whirl import TILT_A_WHIRL_DIR, make_tilt_a_whirl_project


def test_images_range_string_synthetic(tmp_path):
    project = make_synthetic_project(tmp_path)

    assert images_range_string(project) == "$LGX:images.dat[0..10]"


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_images_range_string_tilt_a_whirl():
    project = make_tilt_a_whirl_project()

    assert images_range_string(project) == "$LGX:images.dat[0..12290]"


def test_flat_ride_animation_block_empty_programs(tmp_path):
    project = make_synthetic_project(tmp_path)
    assert project.programs == []

    assert flat_ride_animation_block(project) is None


def test_flat_ride_animation_block_structure(tmp_path):
    project = make_synthetic_project(tmp_path, num_cars=3)
    project.programs = [
        AnimationProgram(
            name="Normal",
            phases=[
                AnimationPhase(name="Start", frame_start=0, frame_count=2, ticks_per_frame=3, next_phase=1),
                AnimationPhase(name="Loop", frame_start=0, frame_count=2, ticks_per_frame=1, next_phase=2,
                               repeat_until_rotations_complete=True),
                AnimationPhase(name="End", frame_start=0, frame_count=2, ticks_per_frame=3, is_final_phase=True),
            ],
        ),
    ]

    block = flat_ride_animation_block(project)

    assert block is not None
    assert block["framesPerDir"] == project.frames_per_dir
    assert block["riderFrameStride"] == 3
    assert len(block["programs"]) == 1
    phases = block["programs"][0]["phases"]
    assert len(phases) == 3

    assert phases[0] == {"startFrame": 0, "endFrame": 1, "ticksPerFrame": 3, "nextPhase": 1}
    assert phases[1] == {"startFrame": 0, "endFrame": 1, "ticksPerFrame": 1, "nextPhase": 2,
                         "repeatUntilRotationsComplete": True}
    assert phases[2] == {"startFrame": 0, "endFrame": 1, "ticksPerFrame": 3, "isFinalPhase": True}


def test_flat_ride_animation_block_omits_false_flags(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.programs = [
        AnimationProgram(
            name="P",
            phases=[AnimationPhase(name="Only", frame_start=0, frame_count=2, is_final_phase=True)],
        ),
    ]

    phase = flat_ride_animation_block(project)["programs"][0]["phases"][0]

    assert "repeatUntilRotationsComplete" not in phase
    assert "resetRotationsOnEntry" not in phase
    assert "nextPhase" not in phase  # omitted when isFinalPhase


def test_flat_ride_animation_block_end_frame_inclusive(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.programs = [
        AnimationProgram(
            name="P",
            phases=[AnimationPhase(name="Only", frame_start=10, frame_count=128, is_final_phase=True)],
        ),
    ]

    phase = flat_ride_animation_block(project)["programs"][0]["phases"][0]

    assert phase["startFrame"] == 10
    assert phase["endFrame"] == 137  # 10 + 128 - 1


def test_flat_ride_animation_block_invalidation_bounds(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.sprite_width = 200  # *2 = 400, capped to 255
    project.programs = [
        AnimationProgram(
            name="P", phases=[AnimationPhase(name="O", frame_start=0, frame_count=2, is_final_phase=True)]
        )
    ]

    block = flat_ride_animation_block(project)

    assert block["invalidationHalfWidth"] == 255  # capped


def test_colour_schemes_block_single_scheme(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.colour_schemes = [ColourScheme(trim_colour="bright_red", tertiary_colour="white")]

    assert colour_schemes_block(project) == [[["bright_red", "bright_red", "white"]]]


def test_colour_schemes_block_multiple_presets(tmp_path):
    """Matches rct2.ride.twist1.json's carColours shape: a list of presets,
    each preset a one-element list wrapping a [Body, Trim, Tertiary] triple."""
    project = make_synthetic_project(tmp_path)
    project.colour_schemes = [
        ColourScheme(trim_colour="moss_green", tertiary_colour="yellow"),
        ColourScheme(trim_colour="white", tertiary_colour="light_blue"),
        ColourScheme(trim_colour="bright_red", tertiary_colour="white"),
    ]

    block = colour_schemes_block(project)

    assert block == [
        [["moss_green", "moss_green", "yellow"]],
        [["white", "white", "light_blue"]],
        [["bright_red", "bright_red", "white"]],
    ]


def test_update_object_json_writes_car_colours(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.colour_schemes = [
        ColourScheme(trim_colour="moss_green", tertiary_colour="yellow"),
        ColourScheme(trim_colour="bright_red", tertiary_colour="white"),
    ]

    (tmp_path / "object.json").write_text(
        json.dumps({"id": project.id, "images": [], "objectType": "ride", "properties": {"type": "flat_ride_generic"}}),
        encoding="utf-8",
    )

    updated = update_object_json(project)

    assert updated["properties"]["carColours"] == [
        [["moss_green", "moss_green", "yellow"]],
        [["bright_red", "bright_red", "white"]],
    ]
    # Existing properties keys survive alongside the new carColours.
    assert updated["properties"]["type"] == "flat_ride_generic"


def test_update_object_json_preserves_other_fields(tmp_path):
    project = make_synthetic_project(tmp_path)

    original = {
        "id": project.id,
        "authors": ["OpenRCT2 Dev Fork"],
        "version": "1.0",
        "objectType": "ride",
        "properties": {"type": "synthetic", "category": "thrill"},
        "images": ["$LGX:images.dat[0..999]"],
        "strings": {"name": {"en-GB": "Synthetic"}},
    }
    (tmp_path / "object.json").write_text(json.dumps(original, indent=4), encoding="utf-8")

    updated = update_object_json(project)

    assert updated["images"] == ["$LGX:images.dat[0..10]"]
    assert updated["properties"]["type"] == original["properties"]["type"]
    assert updated["properties"]["category"] == original["properties"]["category"]
    assert updated["properties"]["carColours"] == [[["bright_red", "bright_red", "white"]]]
    assert updated["strings"] == original["strings"]
    assert "flatRideAnimation" not in updated  # no programs => not written

    on_disk = json.loads((tmp_path / "object.json").read_text(encoding="utf-8"))
    assert on_disk == updated


def test_update_object_json_writes_flat_ride_animation(tmp_path):
    project = make_synthetic_project(tmp_path, num_cars=2)
    project.programs = [
        AnimationProgram(
            name="Normal",
            phases=[AnimationPhase(name="Only", frame_start=0, frame_count=2, is_final_phase=True)],
        ),
    ]

    (tmp_path / "object.json").write_text(
        json.dumps({"id": project.id, "images": [], "objectType": "ride",
                    "properties": {"type": "flat_ride_generic"}}),
        encoding="utf-8",
    )

    updated = update_object_json(project)

    assert "flatRideAnimation" in updated
    block = updated["flatRideAnimation"]
    assert block["framesPerDir"] == project.frames_per_dir
    assert block["riderFrameStride"] == 2

    on_disk = json.loads((tmp_path / "object.json").read_text(encoding="utf-8"))
    assert on_disk["flatRideAnimation"] == block


def test_update_object_json_preserves_manual_invalidation_bounds(tmp_path):
    """Manually-tuned invalidation bounds in existing object.json survive a rebuild."""
    project = make_synthetic_project(tmp_path)
    project.programs = [
        AnimationProgram(
            name="P", phases=[AnimationPhase(name="O", frame_start=0, frame_count=2, is_final_phase=True)]
        )
    ]

    existing_json = {
        "id": project.id,
        "images": [],
        "objectType": "ride",
        "properties": {"type": "flat_ride_generic"},
        "flatRideAnimation": {
            "framesPerDir": 99,            # stale — will be overwritten
            "riderFrameStride": 99,        # stale — will be overwritten
            "invalidationHalfWidth": 200,  # manually tuned — must be preserved
            "invalidationHeightAbove": 180,
            "invalidationHeightBelow": 160,
            "programs": [],                # stale — will be overwritten
        },
    }
    (tmp_path / "object.json").write_text(json.dumps(existing_json), encoding="utf-8")

    updated = update_object_json(project)
    block = updated["flatRideAnimation"]

    # Structural fields regenerated from project model
    assert block["framesPerDir"] == project.frames_per_dir
    assert block["riderFrameStride"] == 0  # num_cars=0 for synthetic default

    # Manually-tuned bounds preserved
    assert block["invalidationHalfWidth"] == 200
    assert block["invalidationHeightAbove"] == 180
    assert block["invalidationHeightBelow"] == 160
