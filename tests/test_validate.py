"""Unit tests for blank-frame and duplicate-trajectory diagnostics, using
small synthetic frame sets, plus a sanity check against the real TiltAWhirl
project (which should report no errors post-fix)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from attraction_editor.model.project import DIRECTIONS, AnimationPhase, AnimationProgram
from attraction_editor.sprites.scanner import frame_path
from attraction_editor.sprites.scanner import static_frame_path
from attraction_editor.sprites.validate import (
    alpha_bbox,
    detect_duplicate_trajectories,
    has_any_alpha,
    validate_frame_set,
    validate_programs,
    validate_project,
    validate_static_layer,
)
from tests.fixtures.synthetic import make_multilayer_synthetic_project, make_synthetic_project
from tests.fixtures.tilt_a_whirl import TILT_A_WHIRL_DIR, make_tilt_a_whirl_project

SIZE = 8


def _save_frame(dir_path: Path, direction: int, frame: int, box: tuple[int, int, int, int] | None) -> None:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    if box is not None:
        left, top, right, bottom = box
        for x in range(left, right):
            for y in range(top, bottom):
                img.putpixel((x, y), (255, 0, 0, 255))
    img.save(frame_path(dir_path, direction, frame))


def test_alpha_bbox_and_has_any_alpha():
    blank = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    assert alpha_bbox(blank) is None
    assert has_any_alpha(blank) is False

    filled = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    filled.putpixel((1, 1), (255, 0, 0, 255))
    assert alpha_bbox(filled) == (1, 1, 2, 2)
    assert has_any_alpha(filled) is True


def test_validate_frame_set_clean(tmp_path: Path):
    sprite_dir = tmp_path / "clean"
    sprite_dir.mkdir()
    frames_per_dir = 4
    for direction in range(4):
        for frame in range(frames_per_dir):
            box = (frame, frame, frame + 2, frame + 2)
            _save_frame(sprite_dir, direction, frame, box)

    report = validate_frame_set(sprite_dir, frames_per_dir, name="clean", sample_frames=(0, 1, 2, 3))

    assert report.ok
    assert report.issues == []
    assert report.sample_bboxes[(0, 0)] == (0, 0, 2, 2)


def test_validate_frame_set_fully_blank_direction(tmp_path: Path):
    sprite_dir = tmp_path / "blank_dir"
    sprite_dir.mkdir()
    frames_per_dir = 4
    for direction in range(4):
        for frame in range(frames_per_dir):
            box = None if direction == 2 else (0, 0, 2, 2)
            _save_frame(sprite_dir, direction, frame, box)

    report = validate_frame_set(sprite_dir, frames_per_dir, name="blank_dir", sample_frames=(0, 1, 2, 3))

    assert not report.ok
    assert any("Direction 2 is entirely blank" in issue.message for issue in report.issues)


def test_validate_frame_set_occlusion_window_warning(tmp_path: Path):
    sprite_dir = tmp_path / "occluded"
    sprite_dir.mkdir()
    frames_per_dir = 5
    for direction in range(4):
        for frame in range(frames_per_dir):
            # Direction 1's sampled frames (0-3) are blank, but frame 4 (not
            # sampled) has content - should be a warning, not an error.
            if direction == 1 and frame < 4:
                box = None
            else:
                box = (0, 0, 2, 2)
            _save_frame(sprite_dir, direction, frame, box)

    report = validate_frame_set(sprite_dir, frames_per_dir, name="occluded", sample_frames=(0, 1, 2, 3))

    assert report.ok  # warnings don't fail `ok`
    warnings = [i for i in report.issues if i.severity == "warning"]
    assert any("Direction 1" in w.message and "occlusion" in w.message for w in warnings)


def test_validate_frame_set_missing_directory_reports_error_not_crash(tmp_path: Path):
    """An entirely absent sprite_dir (e.g. a layer pointed at frames that
    were never rendered) must surface as a validation error, not raise."""
    sprite_dir = tmp_path / "does_not_exist"

    report = validate_frame_set(sprite_dir, frames_per_dir=4, name="missing", sample_frames=(0, 1, 2, 3))

    assert not report.ok
    errors = [i for i in report.issues if i.severity == "error"]
    assert len(errors) == DIRECTIONS * 4  # every sampled frame in every direction is "missing"
    assert all("Missing frame" in e.message for e in errors)


def test_validate_frame_set_some_frames_missing_reports_error_not_crash(tmp_path: Path):
    sprite_dir = tmp_path / "partial"
    sprite_dir.mkdir()
    frames_per_dir = 4
    for direction in range(4):
        for frame in range(frames_per_dir):
            if direction == 1 and frame == 2:
                continue  # leave this one frame missing
            _save_frame(sprite_dir, direction, frame, (0, 0, 2, 2))

    report = validate_frame_set(sprite_dir, frames_per_dir, name="partial", sample_frames=(0, 1, 2, 3))

    errors = [i for i in report.issues if i.severity == "error"]
    assert any("Missing frame" in e.message and "dir1_f0002" in e.message for e in errors)


def test_validate_static_layer_missing_directory_reports_error_not_crash(tmp_path: Path):
    sprite_dir = tmp_path / "does_not_exist"

    report = validate_static_layer(sprite_dir, name="missing")

    assert not report.ok
    errors = [i for i in report.issues if i.severity == "error"]
    assert len(errors) == DIRECTIONS
    assert all("Missing frame" in e.message for e in errors)


def test_validate_project_missing_layer_frames_reports_error_not_crash(tmp_path):
    """validate_project must not raise when a layer's frames don't exist on
    disk yet - this is the exact crash reported from the running app."""
    from attraction_editor.model.project import Layer

    project = make_synthetic_project(tmp_path)
    project.layers = [Layer(name="Core", sprite_dir="Frames/NeverRendered", kind="animated")]

    reports = validate_project(project)

    assert not reports["Core"].ok
    assert any("Missing frame" in i.message for i in reports["Core"].issues)


def test_detect_duplicate_trajectories(tmp_path: Path):
    frames_per_dir = 4
    sample_frames = (0, 1, 2, 3)

    car0_dir = tmp_path / "Car0"
    car1_dir = tmp_path / "Car1"
    car0_dir.mkdir()
    car1_dir.mkdir()

    for direction in range(4):
        for frame in range(frames_per_dir):
            box = (frame, direction, frame + 2, direction + 2)
            _save_frame(car0_dir, direction, frame, box)
            _save_frame(car1_dir, direction, frame, box)  # identical -> duplicate

    report0 = validate_frame_set(car0_dir, frames_per_dir, name="Car0", sample_frames=sample_frames)
    report1 = validate_frame_set(car1_dir, frames_per_dir, name="Car1", sample_frames=sample_frames)

    issues = detect_duplicate_trajectories({"Car0": report0, "Car1": report1})

    assert len(issues) == 1
    assert "Car0" in issues[0].message and "Car1" in issues[0].message
    assert issues[0].severity == "error"


def test_validate_static_layer_clean(tmp_path: Path):
    sprite_dir = tmp_path / "static"
    sprite_dir.mkdir()
    for direction in range(4):
        img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        img.putpixel((1, 1), (255, 0, 0, 255))
        img.save(static_frame_path(sprite_dir, direction))

    report = validate_static_layer(sprite_dir, name="static")

    assert report.ok
    assert report.issues == []


def test_validate_static_layer_blank_direction_is_error(tmp_path: Path):
    sprite_dir = tmp_path / "static"
    sprite_dir.mkdir()
    for direction in range(4):
        img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        if direction != 2:
            img.putpixel((1, 1), (255, 0, 0, 255))
        img.save(static_frame_path(sprite_dir, direction))

    report = validate_static_layer(sprite_dir, name="static")

    assert not report.ok
    assert any("Direction 2 is blank" in issue.message for issue in report.issues)


def test_validate_project_multilayer_dispatches_by_kind(tmp_path):
    project = make_multilayer_synthetic_project(tmp_path)

    reports = validate_project(project)

    assert set(reports) >= {"Background", "Core", "Foreground"}
    for name in ("Background", "Core", "Foreground"):
        assert reports[name].ok


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_validate_project_tilt_a_whirl_has_no_errors():
    project = make_tilt_a_whirl_project()
    reports = validate_project(project)

    assert set(reports) == {
        "Core_Static_0", "Core_Anim_0", "Car0", "Car1", "Car2", "Car3", "Car4", "Car5", "Car6", "Programs",
    }
    for name, report in reports.items():
        errors = [i for i in report.issues if i.severity == "error"]
        assert errors == [], f"{name}: {errors}"


def test_validate_programs_valid():
    program = AnimationProgram(
        name="Normal",
        phases=[
            AnimationPhase(name="Start", frame_start=0, frame_count=8, next_phase=1),
            AnimationPhase(
                name="Loop",
                frame_start=8,
                frame_count=16,
                next_phase=2,
                repeat_until_rotations_complete=True,
            ),
            AnimationPhase(name="End", frame_start=24, frame_count=8, is_final_phase=True),
        ],
    )

    class _Project:
        frames_per_dir = 32
        programs = [program]

    assert validate_programs(_Project()) == []


def test_validate_programs_frame_count_must_be_positive():
    program = AnimationProgram(
        name="Bad",
        phases=[AnimationPhase(name="Empty", frame_start=0, frame_count=0)],
    )

    class _Project:
        frames_per_dir = 32
        programs = [program]

    issues = validate_programs(_Project())

    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "frame_count must be positive" in issues[0].message


def test_validate_programs_frame_range_out_of_bounds():
    program = AnimationProgram(
        name="Overflow",
        phases=[AnimationPhase(name="TooFar", frame_start=24, frame_count=16)],
    )

    class _Project:
        frames_per_dir = 32
        programs = [program]

    issues = validate_programs(_Project())

    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "out of range for frames_per_dir=32" in issues[0].message


def test_validate_programs_next_phase_out_of_range():
    program = AnimationProgram(
        name="Dangling",
        phases=[AnimationPhase(name="Only", frame_start=0, frame_count=4, next_phase=5)],
    )

    class _Project:
        frames_per_dir = 32
        programs = [program]

    issues = validate_programs(_Project())

    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert "next_phase=5 is out of range" in issues[0].message


def test_validate_project_includes_programs_report(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.programs = [
        AnimationProgram(
            name="Normal",
            phases=[AnimationPhase(name="Only", frame_start=0, frame_count=2, is_final_phase=True)],
        )
    ]

    reports = validate_project(project)

    assert "Programs" in reports
    assert reports["Programs"].ok


def test_validate_project_omits_programs_report_when_empty(tmp_path):
    project = make_synthetic_project(tmp_path)
    assert project.programs == []

    reports = validate_project(project)

    assert "Programs" not in reports
