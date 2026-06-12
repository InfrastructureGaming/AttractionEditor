"""Unit tests for blank-frame and duplicate-trajectory diagnostics, using
small synthetic frame sets, plus a sanity check against the real TiltAWhirl
project (which should report no errors post-fix)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from attraction_editor.sprites.scanner import frame_path
from attraction_editor.sprites.validate import (
    alpha_bbox,
    detect_duplicate_trajectories,
    has_any_alpha,
    validate_frame_set,
    validate_project,
)
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


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_validate_project_tilt_a_whirl_has_no_errors():
    project = make_tilt_a_whirl_project()
    reports = validate_project(project)

    assert set(reports) == {"Core", "Car0", "Car1", "Car2", "Car3", "Car4", "Car5", "Car6"}
    for name, report in reports.items():
        errors = [i for i in report.issues if i.severity == "error"]
        assert errors == [], f"{name}: {errors}"
