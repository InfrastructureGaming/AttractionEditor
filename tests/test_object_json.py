"""Tests for build/object_json.py: images range, flatRideAnimation block,
colour_schemes_block (properties.carColours), cars_block, and
write_object_json (the full-file orchestrator)."""

from __future__ import annotations

import json

import pytest

from attraction_editor.build.object_json import (
    cars_block,
    colour_schemes_block,
    custom_ride_manifest,
    flat_ride_animation_block,
    images_range_string,
    invalidation_bounds,
    write_object_json,
)
from attraction_editor.model.project import AnimationPhase, AnimationProgram, ColourScheme, DirectionAnchor
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


def test_invalidation_bounds_derives_height_from_centred_anchor(tmp_path):
    """A dead-centre anchor (y = -sprite_height/2) should split height/2
    above and below, same as the old fixed negative/positive fields would
    have for a centred sprite."""
    project = make_synthetic_project(tmp_path)
    project.sprite_height = 60
    project.anchors = [DirectionAnchor(x=0, y=-30) for _ in range(4)]

    _half_width, height_above, height_below = invalidation_bounds(project)

    assert height_above == 60  # 30 * 2
    assert height_below == 60  # (60 - 30) * 2


def test_invalidation_bounds_takes_the_max_across_directions(tmp_path):
    """heightAbove/heightBelow are project-wide (object.json has one value,
    not one per direction) - must cover whichever direction's anchor sits
    least centred, not just direction 0."""
    project = make_synthetic_project(tmp_path)
    project.sprite_height = 100
    project.anchors = [
        DirectionAnchor(x=0, y=-50),  # centred: above=50, below=50
        DirectionAnchor(x=0, y=-20),  # origin near the top: above=20, below=80
        DirectionAnchor(x=0, y=-80),  # origin near the bottom: above=80, below=20
        DirectionAnchor(x=0, y=-50),
    ]

    _half_width, height_above, height_below = invalidation_bounds(project)

    assert height_above == 160  # max(50, 20, 80, 50) * 2 = 80 * 2
    assert height_below == 160  # max(50, 80, 20, 50) * 2 = 80 * 2


def test_invalidation_bounds_clamps_negative_extents_to_zero(tmp_path):
    """An anchor placed outside the sprite's bounds (an authoring mistake,
    or an origin point deliberately off-canvas) must not produce a
    negative invalidation extent."""
    project = make_synthetic_project(tmp_path)
    project.sprite_height = 50
    project.anchors = [DirectionAnchor(x=0, y=20) for _ in range(4)]  # origin above the image entirely

    _half_width, height_above, height_below = invalidation_bounds(project)

    assert height_above == 0  # -anchor.y = -20, clamped
    assert height_below == 140  # (50 + 20) * 2 = 140, unaffected


def test_invalidation_bounds_derives_width_from_anchor_x_too(tmp_path):
    """Width must get the same anchor-derived treatment as height - a
    sprite_width * 2 shortcut ignores asymmetric anchors the same way the
    old fixed negative/positive height split did before that was fixed."""
    project = make_synthetic_project(tmp_path)
    project.sprite_width = 100
    project.anchors = [
        DirectionAnchor(x=-50, y=0),  # centred: left=50, right=50
        DirectionAnchor(x=-20, y=0),  # origin near the left edge: left=20, right=80
        DirectionAnchor(x=-80, y=0),  # origin near the right edge: left=80, right=20
        DirectionAnchor(x=-50, y=0),
    ]

    half_width, _above, _below = invalidation_bounds(project)

    assert half_width == 160  # max(left=80, right=80) * 2 = 80 * 2


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


def test_cars_block_derives_sprite_dims_and_hardcodes_colour_flags(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.car_tab_offset = -20
    project.car_tab_scale = 0.5
    project.car_num_seats = 24
    project.car_visual = 1
    project.car_draw_order = 6

    block = cars_block(project)

    assert block["rotationFrameMask"] == project.rotation_frame_mask
    # spacing/mass deliberately omitted - confirmed against Ride.cpp that
    # the engine only reads them for tracked-ride train validation, which
    # is skipped entirely once carsPerFlatRide is set.
    assert "spacing" not in block
    assert "mass" not in block
    assert block["tabOffset"] == -20
    assert block["tabScale"] == 0.5
    assert block["numSeats"] == 24
    assert block["carVisual"] == 1
    assert block["drawOrder"] == 6
    assert block["frames"] == {"flat": True}
    assert block["recalculateSpriteBounds"] is True
    # Both flags must always be true - Tertiary recolouring silently fails
    # to apply in-game without hasAdditionalColour2, even though carColours
    # specifies one (see RideObject.cpp's enableTrimColour/enableTertiaryColour).
    assert block["hasAdditionalColour1"] is True
    assert block["hasAdditionalColour2"] is True
    # spriteWidth/spriteHeightNegative/Positive come from _sprite_extents,
    # not authored directly - same derivation invalidation_bounds uses.
    left, right, above, below = (
        max(0, max(-a.x for a in project.anchors)),
        max(0, max(project.sprite_width + a.x for a in project.anchors)),
        max(0, max(-a.y for a in project.anchors)),
        max(0, max(project.sprite_height + a.y for a in project.anchors)),
    )
    assert block["spriteWidth"] == max(left, right)
    assert block["spriteHeightNegative"] == above
    assert block["spriteHeightPositive"] == below


def test_write_object_json_creates_file_from_scratch(tmp_path):
    """The whole point of this rewrite: no pre-existing object.json template
    is required any more - this used to be a hard FileNotFoundError."""
    project = make_synthetic_project(tmp_path)
    project.colour_schemes = [
        ColourScheme(trim_colour="moss_green", tertiary_colour="yellow"),
        ColourScheme(trim_colour="bright_red", tertiary_colour="white"),
    ]
    assert not (tmp_path / "object.json").exists()

    written = write_object_json(project)

    assert written["id"] == project.id
    assert written["objectType"] == "ride"
    assert written["sourceGame"] == "custom"
    assert written["authors"] == project.authors
    assert written["version"] == project.version
    # Always "flat_ride_generic" - this project's own modular flat-ride
    # object type, built specifically so a flatRideAnimation block can drive
    # the whole ride without needing its own hardcoded engine ride-type.
    assert written["properties"]["type"] == "flat_ride_generic"
    assert written["properties"]["category"] == project.category
    assert "rotationMode" not in written["properties"]  # only matters without flatRideAnimation
    assert written["properties"]["carsPerFlatRide"] == 1
    assert written["properties"]["carColours"] == [
        [["moss_green", "moss_green", "yellow"]],
        [["bright_red", "bright_red", "white"]],
    ]
    assert written["properties"]["cars"] == cars_block(project)
    assert written["strings"]["name"] == {"en-GB": project.name}
    assert written["strings"]["description"] == {"en-GB": project.description}

    on_disk = json.loads((tmp_path / "object.json").read_text(encoding="utf-8"))
    assert on_disk == written


def test_write_object_json_is_authoritative_for_existing_fields(tmp_path):
    """Unlike the old update_object_json, this regenerates *every* field
    (except invalidation bounds) from the project model on every build -
    an existing file's properties.type/category/strings are overwritten to
    match the project, not preserved verbatim."""
    project = make_synthetic_project(tmp_path)
    project.capacity_text = "24 passengers"

    original = {
        "id": project.id,
        "authors": ["Someone Else"],
        "version": "0.1",
        "objectType": "ride",
        "properties": {"type": "stale_type", "category": "stale_category", "rotationMode": 1},
        "images": ["$LGX:images.dat[0..999]"],
        "strings": {"name": {"en-GB": "Stale Name"}},
    }
    (tmp_path / "object.json").write_text(json.dumps(original, indent=4), encoding="utf-8")

    written = write_object_json(project)

    assert written["images"] == ["$LGX:images.dat[0..10]"]
    assert written["authors"] == project.authors
    assert written["version"] == project.version
    assert written["properties"]["type"] == "flat_ride_generic"
    assert written["properties"]["category"] == project.category
    assert "rotationMode" not in written["properties"]  # stale value removed, not preserved
    assert written["strings"]["name"] == {"en-GB": project.name}
    assert written["strings"]["capacity"] == {"en-GB": "24 passengers"}
    assert "flatRideAnimation" not in written["properties"]  # no programs => not written

    on_disk = json.loads((tmp_path / "object.json").read_text(encoding="utf-8"))
    assert on_disk == written


def test_write_object_json_nests_flat_ride_animation_under_properties(tmp_path):
    """Regression test for a real bug found while authoring this: the
    engine (RideObject.cpp, confirmed against both Freestyle/Troika's real
    object.json) reads flatRideAnimation from inside "properties", not at
    the JSON's top level - the old code wrote it top-level, which the
    engine would never have found."""
    project = make_synthetic_project(tmp_path, num_cars=2)
    project.programs = [
        AnimationProgram(
            name="Normal",
            phases=[AnimationPhase(name="Only", frame_start=0, frame_count=2, is_final_phase=True)],
        ),
    ]

    written = write_object_json(project)

    assert "flatRideAnimation" not in written
    assert "flatRideAnimation" in written["properties"]
    block = written["properties"]["flatRideAnimation"]
    assert block["framesPerDir"] == project.frames_per_dir
    assert block["riderFrameStride"] == 2

    on_disk = json.loads((tmp_path / "object.json").read_text(encoding="utf-8"))
    assert on_disk["properties"]["flatRideAnimation"] == block


def test_write_object_json_preserves_manual_invalidation_bounds(tmp_path):
    """Manually-tuned invalidation bounds in an existing object.json survive
    a rebuild - the one field write_object_json doesn't unconditionally
    regenerate."""
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
        "properties": {
            "type": "flat_ride_generic",
            "flatRideAnimation": {
                "framesPerDir": 99,            # stale — will be overwritten
                "riderFrameStride": 99,        # stale — will be overwritten
                "invalidationHalfWidth": 200,  # manually tuned — must be preserved
                "invalidationHeightAbove": 180,
                "invalidationHeightBelow": 160,
                "programs": [],                # stale — will be overwritten
            },
        },
    }
    (tmp_path / "object.json").write_text(json.dumps(existing_json), encoding="utf-8")

    written = write_object_json(project)
    block = written["properties"]["flatRideAnimation"]

    # Structural fields regenerated from project model
    assert block["framesPerDir"] == project.frames_per_dir
    assert block["riderFrameStride"] == 0  # num_cars=0 for synthetic default

    # Manually-tuned bounds preserved
    assert block["invalidationHalfWidth"] == 200
    assert block["invalidationHeightAbove"] == 180
    assert block["invalidationHeightBelow"] == 160


def test_custom_ride_manifest_parkobj_field_is_the_object_id_not_a_filename(tmp_path):
    """Regression test for the actual bug report: CustomRideLoader.cpp's
    "parkobj" field is looked up against the object repository by id
    (RideObject's own "id"), not matched against a filename - a manifest
    with "parkobj": "<name>.parkobj" registers the ride but its vehicle
    object silently fails to load."""
    project = make_synthetic_project(tmp_path)

    manifest = custom_ride_manifest(project)

    assert manifest["name"] == project.name
    assert manifest["parkobj"] == project.id
    assert not manifest["parkobj"].endswith(".parkobj")


def test_custom_ride_manifest_includes_description_and_first_author(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.description = "A spinning ride."
    project.authors = ["Jack", "Custom Rides Inc."]

    manifest = custom_ride_manifest(project)

    assert manifest["description"] == "A spinning ride."
    assert manifest["author"] == "Jack"  # only the first - CustomRideLoader reads a single string


def test_custom_ride_manifest_omits_empty_description_and_authors(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.description = ""
    project.authors = []

    manifest = custom_ride_manifest(project)

    assert "description" not in manifest
    assert "author" not in manifest


def test_custom_ride_manifest_ratings_default_matches_engine_fallback(tmp_path):
    """Untouched rating_* fields must be behaviourally identical to omitting
    "ratings" entirely - CustomRideLoader.cpp falls back to excitement
    3/intensity 2/nausea 1 when the key is absent."""
    project = make_synthetic_project(tmp_path)

    manifest = custom_ride_manifest(project)

    assert manifest["ratings"] == {"excitement": 3, "intensity": 2, "nausea": 1}


def test_custom_ride_manifest_includes_custom_ratings(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.rating_excitement = 7
    project.rating_intensity = 6
    project.rating_nausea = 4

    manifest = custom_ride_manifest(project)

    assert manifest["ratings"] == {"excitement": 7, "intensity": 6, "nausea": 4}


def test_custom_ride_manifest_omits_cost_when_zero(tmp_path):
    """CustomRideLoader.cpp only applies a build-cost override when cost > 0
    - 0 must mean "use the engine's own default", not "free"."""
    project = make_synthetic_project(tmp_path)
    assert project.build_cost == 0

    manifest = custom_ride_manifest(project)

    assert "cost" not in manifest


def test_custom_ride_manifest_includes_cost_when_set(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.build_cost = 1500

    manifest = custom_ride_manifest(project)

    assert manifest["cost"] == 1500
