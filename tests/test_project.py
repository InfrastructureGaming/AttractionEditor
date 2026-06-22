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
        {"trim_colour": "bright_red", "tertiary_colour": "white"},
        {"trim_colour": "moss_green", "tertiary_colour": "yellow"},
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
