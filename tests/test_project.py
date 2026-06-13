"""Round-trip serialization tests for AnimationPhase/AnimationProgram
(RideProject.programs), the model additions for the multi-phase/multi-program
animation system."""

from __future__ import annotations

from pathlib import Path

from attraction_editor.model.project import AnimationPhase, AnimationProgram
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
