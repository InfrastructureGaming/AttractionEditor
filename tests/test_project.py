"""Round-trip serialization tests for AnimationPhase/AnimationProgram
(RideProject.programs), the model additions for the multi-phase/multi-program
animation system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from attraction_editor.model.project import AnimationPhase, AnimationProgram, ColourScheme, Layer, RideProject
from tests.fixtures.synthetic import make_synthetic_project


def _make_programs() -> list[AnimationProgram]:
    return [
        AnimationProgram(
            name="Normal",
            phases=[
                AnimationPhase(name="Start", frame_start=0, frame_count=8, next_phase=1),
                AnimationPhase(
                    name="Loop",
                    frame_start=8,
                    frame_count=16,
                    ticks_per_frame=2,
                    next_phase=2,
                    repeat_until_rotations_complete=True,
                ),
                AnimationPhase(name="End", frame_start=24, frame_count=8, is_final_phase=True),
            ],
        ),
    ]


def test_programs_round_trip_through_to_dict(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.programs = _make_programs()

    data = project.to_dict()

    assert data["programs"][0]["name"] == "Normal"
    assert data["programs"][0]["phases"][1]["repeat_until_rotations_complete"] is True
    assert data["programs"][0]["phases"][2]["is_final_phase"] is True


def test_programs_round_trip_through_save_and_load(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.programs = _make_programs()

    path = tmp_path / "project.ridepkg.json"
    project.save(path)

    loaded = type(project).load(path)

    assert loaded.programs == project.programs


def test_play_reverse_round_trips_through_save_and_load(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    programs = _make_programs()
    programs[0].phases[2].play_reverse = True  # the "End" phase plays reversed
    project.programs = programs

    path = tmp_path / "project.ridepkg.json"
    project.save(path)

    loaded = type(project).load(path)

    assert loaded.programs[0].phases[2].play_reverse is True
    assert loaded.programs[0].phases[0].play_reverse is False  # unset stays default


def test_load_back_compat_for_phases_without_play_reverse(tmp_path: Path):
    """A project saved before play_reverse existed has no play_reverse key on
    any phase - each must load with the default (False), not error."""
    project = make_synthetic_project(tmp_path)
    project.programs = _make_programs()
    data = project.to_dict()
    for program in data["programs"]:
        for phase in program["phases"]:
            phase.pop("play_reverse")
    path = tmp_path / "legacy.ridepkg.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = RideProject.load(path)

    assert all(not phase.play_reverse for phase in loaded.programs[0].phases)


def test_bonus_value_round_trips_clamps_and_back_compat(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    assert project.bonus_value == 35  # default matches the flat_ride_generic RTD

    project.bonus_value = 70
    path = tmp_path / "project.ridepkg.json"
    project.save(path)
    assert RideProject.load(path).bonus_value == 70

    # Out-of-range values clamp to 0..BONUS_VALUE_MAX on load.
    data = project.to_dict()
    data["bonus_value"] = 500
    clamp_path = tmp_path / "clamp.ridepkg.json"
    clamp_path.write_text(json.dumps(data), encoding="utf-8")
    assert RideProject.load(clamp_path).bonus_value == RideProject.BONUS_VALUE_MAX

    # A project saved before bonus_value existed defaults to 35.
    data.pop("bonus_value")
    legacy = tmp_path / "legacy.ridepkg.json"
    legacy.write_text(json.dumps(data), encoding="utf-8")
    assert RideProject.load(legacy).bonus_value == 35


def test_load_ignores_unknown_keys(tmp_path: Path):
    """A project saved while an experimental field existed that was later
    reverted (e.g. shuffle_load_order) must still load - unknown keys are
    dropped, not fatal."""
    project = make_synthetic_project(tmp_path)
    data = project.to_dict()
    data["shuffle_load_order"] = True  # a field that no longer exists on RideProject
    data["some_future_field"] = 123
    path = tmp_path / "legacy.ridepkg.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = RideProject.load(path)  # must not raise

    assert loaded.id == project.id
    assert not hasattr(loaded, "shuffle_load_order")


def test_upkeep_cost_round_trips_clamps_and_back_compat(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    assert project.upkeep_cost == 50  # default matches flat_ride_generic base

    project.upkeep_cost = 200
    path = tmp_path / "project.ridepkg.json"
    project.save(path)
    assert RideProject.load(path).upkeep_cost == 200

    data = project.to_dict()
    data["upkeep_cost"] = 9000  # clamps to UPKEEP_COST_MAX
    clamp_path = tmp_path / "clamp.ridepkg.json"
    clamp_path.write_text(json.dumps(data), encoding="utf-8")
    assert RideProject.load(clamp_path).upkeep_cost == RideProject.UPKEEP_COST_MAX

    data.pop("upkeep_cost")  # pre-feature project -> default 50
    legacy = tmp_path / "legacy.ridepkg.json"
    legacy.write_text(json.dumps(data), encoding="utf-8")
    assert RideProject.load(legacy).upkeep_cost == 50


def test_colour_scheme_body_colour_round_trips_and_back_compat(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.colour_schemes = [ColourScheme(trim_colour="white", tertiary_colour="white", body_colour="dark_blue")]
    path = tmp_path / "project.ridepkg.json"
    project.save(path)
    assert RideProject.load(path).colour_schemes[0].body_colour == "dark_blue"

    # A scheme saved before body_colour existed loads as None.
    data = project.to_dict()
    for cs in data["colour_schemes"]:
        cs.pop("body_colour")
    legacy = tmp_path / "legacy.ridepkg.json"
    legacy.write_text(json.dumps(data), encoding="utf-8")
    assert RideProject.load(legacy).colour_schemes[0].body_colour is None


def test_layer_zone_pass_dir_round_trips_and_back_compat(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.layers[0].zone_pass_dir = "Frames/Core"  # masks alongside the beauty frames
    path = tmp_path / "project.ridepkg.json"
    project.save(path)

    loaded = type(project).load(path)
    assert loaded.layers[0].zone_pass_dir == "Frames/Core"

    # A layer saved before the field existed loads with the default (None).
    data = project.to_dict()
    for layer in data["layers"]:
        layer.pop("zone_pass_dir")
    legacy = tmp_path / "legacy.ridepkg.json"
    legacy.write_text(json.dumps(data), encoding="utf-8")
    assert RideProject.load(legacy).layers[0].zone_pass_dir is None


def test_breakdowns_round_trip_through_save_and_load(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.breakdowns = ["safetyCutOut", "vehicleMalfunction"]

    path = tmp_path / "project.ridepkg.json"
    project.save(path)

    loaded = type(project).load(path)

    assert loaded.breakdowns == ["safetyCutOut", "vehicleMalfunction"]


def test_load_back_compat_for_projects_without_breakdowns(tmp_path: Path):
    """A project saved before breakdowns existed defaults to ["safetyCutOut"] -
    exactly what FlatRideGenericRTD gave it before - so rebuilding is a no-op."""
    project = make_synthetic_project(tmp_path)
    data = project.to_dict()
    data.pop("breakdowns")
    path = tmp_path / "legacy.ridepkg.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = RideProject.load(path)

    assert loaded.breakdowns == ["safetyCutOut"]


def test_unknown_breakdown_is_rejected(tmp_path: Path):
    """brakesFailure (and any non-authorable name) must not slip into a project -
    it's tracked-ride-only and would be a no-op or worse on a flat ride."""
    project = make_synthetic_project(tmp_path)
    data = project.to_dict()
    data["breakdowns"] = ["brakesFailure"]
    path = tmp_path / "bad.ridepkg.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="Unknown breakdown"):
        RideProject.load(path)


def test_thumbnail_path_round_trips_through_save_and_load(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.thumbnail_path = "Frames/thumb.png"

    path = tmp_path / "project.ridepkg.json"
    project.save(path)

    loaded = type(project).load(path)

    assert loaded.thumbnail_path == "Frames/thumb.png"


def test_load_back_compat_for_projects_without_thumbnail_path(tmp_path: Path):
    """A project saved before thumbnail_path existed has no such key - must load
    with the default (None), not error."""
    project = make_synthetic_project(tmp_path)
    data = project.to_dict()
    data.pop("thumbnail_path")
    path = tmp_path / "legacy.ridepkg.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = RideProject.load(path)

    assert loaded.thumbnail_path is None


def test_empty_programs_round_trip(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    assert project.programs == []

    path = tmp_path / "project.ridepkg.json"
    project.save(path)

    loaded = type(project).load(path)

    assert loaded.programs == []


def test_layers_round_trip_through_to_dict(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.layers = [
        Layer(name="Background", sprite_dir="Frames/Background", kind="static", dither_algorithm="atkinson", dither_strength=16),
        Layer(name="Core", sprite_dir="Frames/Core", kind="animated", dither_algorithm="bayer", dither_strength=48),
    ]

    data = project.to_dict()

    assert data["layers"][0]["kind"] == "static"
    assert data["layers"][0]["dither_algorithm"] == "atkinson"
    assert data["layers"][0]["dither_strength"] == 16
    assert data["layers"][1]["kind"] == "animated"
    assert data["layers"][1]["dither_algorithm"] == "bayer"


def test_layers_round_trip_through_save_and_load(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.layers = [
        Layer(name="Background", sprite_dir="Frames/Background", kind="static"),
        Layer(name="Core", sprite_dir="Frames/Core", kind="animated", dither_algorithm="bayer"),
    ]

    path = tmp_path / "project.ridepkg.json"
    project.save(path)

    loaded = type(project).load(path)

    assert loaded.layers == project.layers


def test_load_back_compat_shim_for_core_sprite_dir(tmp_path: Path):
    """An old project file with core_sprite_dir and no layers key must load
    as a single animated "Core" layer."""
    data = {
        "id": "openrct2dev.ride.legacy",
        "name": "Legacy",
        "description": "",
        "category": "thrill",
        "frames_per_dir": 4,
        "sprite_width": 10,
        "sprite_height_negative": 10,
        "sprite_height_positive": 10,
        "anchors": [{"x": 0, "y": 0} for _ in range(4)],
        "core_sprite_dir": "Frames/Core",
        "cars": [],
        "programs": [],
    }
    path = tmp_path / "legacy.ridepkg.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = RideProject.load(path)

    assert loaded.layers == [Layer(name="Core", sprite_dir="Frames/Core", kind="animated")]


def test_rideproject_requires_at_least_one_layer(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    with pytest.raises(ValueError, match="at least one layer"):
        project.layers = []
        RideProject(**{**vars(project), "layers": []})


def test_rideproject_rejects_invalid_layer_kind(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    bad_layer = Layer(name="Bad", sprite_dir="Frames/Bad", kind="not_a_kind")
    with pytest.raises(ValueError, match="invalid kind"):
        RideProject(**{**vars(project), "layers": [bad_layer]})


def test_rideproject_rejects_invalid_dither_algorithm(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    bad_layer = Layer(name="Bad", sprite_dir="Frames/Bad", kind="static", dither_algorithm="not_an_algorithm")
    with pytest.raises(ValueError, match="invalid dither_algorithm"):
        RideProject(**{**vars(project), "layers": [bad_layer]})


def test_colour_schemes_round_trip_through_to_dict(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.colour_schemes = [
        ColourScheme(trim_colour="bright_red", tertiary_colour="white"),
        ColourScheme(trim_colour="moss_green", tertiary_colour="yellow"),
    ]

    data = project.to_dict()

    assert data["colour_schemes"] == [
        {"trim_colour": "bright_red", "tertiary_colour": "white", "body_colour": None},
        {"trim_colour": "moss_green", "tertiary_colour": "yellow", "body_colour": None},
    ]


def test_colour_schemes_round_trip_through_save_and_load(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.colour_schemes = [ColourScheme(trim_colour="black", tertiary_colour="yellow")]

    path = tmp_path / "project.ridepkg.json"
    project.save(path)

    loaded = type(project).load(path)

    assert loaded.colour_schemes == project.colour_schemes


def test_load_back_compat_shim_for_body_trim_colour(tmp_path: Path):
    """An old project file with body_colour/trim_colour and no colour_schemes
    key must load as a single ColourScheme - with the field rename applied:
    old body_colour actually fed the Trim zone, old trim_colour fed Tertiary."""
    data = {
        "id": "openrct2dev.ride.legacy",
        "name": "Legacy",
        "description": "",
        "category": "thrill",
        "frames_per_dir": 4,
        "sprite_width": 10,
        "sprite_height_negative": 10,
        "sprite_height_positive": 10,
        "anchors": [{"x": 0, "y": 0} for _ in range(4)],
        "layers": [{"name": "Core", "sprite_dir": "Frames/Core", "kind": "animated",
                    "dither_algorithm": "floyd_steinberg", "dither_strength": 32}],
        "cars": [],
        "programs": [],
        "body_colour": "bright_red",
        "trim_colour": "white",
    }
    path = tmp_path / "legacy.ridepkg.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = RideProject.load(path)

    assert loaded.colour_schemes == [ColourScheme(trim_colour="bright_red", tertiary_colour="white")]


def test_rideproject_requires_at_least_one_colour_scheme(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    with pytest.raises(ValueError, match="at least one colour scheme"):
        RideProject(**{**vars(project), "colour_schemes": []})


def test_catch_tolerance_defaults_to_zero(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    assert project.trim_catch_tolerance == 0
    assert project.tertiary_catch_tolerance == 0


def test_catch_tolerance_round_trips_through_save_and_load(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.trim_catch_tolerance = 12
    project.tertiary_catch_tolerance = -8

    path = tmp_path / "project.ridepkg.json"
    project.save(path)
    loaded = type(project).load(path)

    assert loaded.trim_catch_tolerance == 12
    assert loaded.tertiary_catch_tolerance == -8


def test_load_back_compat_for_projects_without_catch_tolerance(tmp_path: Path):
    """An old project file saved before this feature existed has no
    trim_catch_tolerance/tertiary_catch_tolerance keys at all - must load
    with the default (0, today's original fixed behaviour), not error."""
    project = make_synthetic_project(tmp_path)
    data = project.to_dict()
    data.pop("trim_catch_tolerance")
    data.pop("tertiary_catch_tolerance")
    path = tmp_path / "legacy.ridepkg.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = RideProject.load(path)

    assert loaded.trim_catch_tolerance == 0
    assert loaded.tertiary_catch_tolerance == 0


def test_load_back_compat_shim_for_sprite_height_negative_positive(tmp_path: Path):
    """An old project file split sprite height into negative/positive
    halves around the origin - must load as their sum, with neither old
    key surviving onto the loaded RideProject."""
    project = make_synthetic_project(tmp_path)
    data = project.to_dict()
    data.pop("sprite_height")
    data["sprite_height_negative"] = 85
    data["sprite_height_positive"] = 90
    path = tmp_path / "legacy.ridepkg.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = RideProject.load(path)

    assert loaded.sprite_height == 175
    assert not hasattr(loaded, "sprite_height_negative")
    assert not hasattr(loaded, "sprite_height_positive")


def test_sprite_height_round_trips_through_save_and_load(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.sprite_height = 265

    path = tmp_path / "project.ridepkg.json"
    project.save(path)
    loaded = type(project).load(path)

    assert loaded.sprite_height == 265


def test_ride_object_metadata_defaults(tmp_path: Path):
    project = make_synthetic_project(tmp_path)

    assert project.authors == ["OpenRCT2 Dev Fork"]
    assert project.version == "1.0"
    assert project.car_tab_offset == 0
    assert project.car_tab_scale == 0.0
    assert project.car_num_seats == 0
    assert project.car_visual == 1
    assert project.car_draw_order == 6
    assert project.capacity_text == ""
    assert project.build_cost == 0
    assert project.rating_excitement == 3
    assert project.rating_intensity == 2
    assert project.rating_nausea == 1


def test_ride_object_metadata_round_trips_through_save_and_load(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.authors = ["Jack", "Custom Rides Inc."]
    project.version = "2.0"
    project.car_tab_offset = -20
    project.car_tab_scale = 0.5
    project.car_num_seats = 24
    project.car_visual = 1
    project.car_draw_order = 6
    project.build_cost = 1500
    project.rating_excitement = 7
    project.rating_intensity = 6
    project.rating_nausea = 4
    project.capacity_text = "24 passengers"

    path = tmp_path / "project.ridepkg.json"
    project.save(path)
    loaded = type(project).load(path)

    assert loaded.authors == ["Jack", "Custom Rides Inc."]
    assert loaded.version == "2.0"
    assert loaded.car_tab_offset == -20
    assert loaded.car_tab_scale == 0.5
    assert loaded.car_num_seats == 24
    assert loaded.car_visual == 1
    assert loaded.car_draw_order == 6
    assert loaded.capacity_text == "24 passengers"
    assert loaded.build_cost == 1500
    assert loaded.rating_excitement == 7
    assert loaded.rating_intensity == 6
    assert loaded.rating_nausea == 4


def test_base_footprint_defaults_to_6x6(tmp_path: Path):
    project = make_synthetic_project(tmp_path)

    assert project.base_footprint_width == 6
    assert project.base_footprint_length == 6


def test_base_footprint_round_trips_through_save_and_load(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    project.base_footprint_width = 1
    project.base_footprint_length = 4

    path = tmp_path / "project.ridepkg.json"
    project.save(path)
    loaded = type(project).load(path)

    assert loaded.base_footprint_width == 1
    assert loaded.base_footprint_length == 4


def test_base_footprint_rejects_dimensions_below_one(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    data = project.to_dict()
    data["base_footprint_width"] = 0

    with pytest.raises(ValueError, match="must each be >= 1"):
        RideProject(**{**data, "anchors": project.anchors, "layers": project.layers})


def test_base_footprint_rejects_more_than_64_tiles(tmp_path: Path):
    project = make_synthetic_project(tmp_path)
    data = project.to_dict()
    data["base_footprint_width"] = 8
    data["base_footprint_length"] = 9  # 72 tiles - over the engine's 64-tile cap

    with pytest.raises(ValueError, match="exceeds the engine's 64-tile cap"):
        RideProject(**{**data, "anchors": project.anchors, "layers": project.layers})


def test_load_back_compat_for_projects_without_base_footprint(tmp_path: Path):
    """An old project file saved before this feature existed has no
    base_footprint_width/length keys - must load with the 6x6 default that
    matches every custom ride's behaviour before this field existed."""
    project = make_synthetic_project(tmp_path)
    data = project.to_dict()
    data.pop("base_footprint_width")
    data.pop("base_footprint_length")
    path = tmp_path / "legacy.ridepkg.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = RideProject.load(path)

    assert loaded.base_footprint_width == 6
    assert loaded.base_footprint_length == 6


def test_load_back_compat_for_projects_without_ride_object_metadata(tmp_path: Path):
    """An old project file saved before this feature existed has none of
    these keys - must load with defaults, not error."""
    project = make_synthetic_project(tmp_path)
    data = project.to_dict()
    for key in (
        "authors", "version",
        "car_tab_offset", "car_tab_scale", "car_num_seats", "car_visual", "car_draw_order", "capacity_text",
        "build_cost", "rating_excitement", "rating_intensity", "rating_nausea",
    ):
        data.pop(key)
    path = tmp_path / "legacy.ridepkg.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = RideProject.load(path)

    assert loaded.authors == ["OpenRCT2 Dev Fork"]
    assert loaded.car_visual == 1
