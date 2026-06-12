"""Validates frame-set scanning against the shipped TiltAWhirl Frames directory
(512 frames per car, 243x170 each)."""

from __future__ import annotations

import pytest

from attraction_editor.sprites.scanner import FrameSetError, scan_project
from tests.fixtures.tilt_a_whirl import TILT_A_WHIRL_DIR, make_tilt_a_whirl_project


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_scan_project_finds_all_frame_sets():
    project = make_tilt_a_whirl_project()

    results = scan_project(project)

    assert set(results) == {"Core", "Car0", "Car1", "Car2", "Car3", "Car4", "Car5", "Car6"}
    for name, info in results.items():
        assert info.width == 243
        assert info.height == 170
        assert info.frames_per_dir == 128


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_scan_project_detects_missing_frame(tmp_path):
    project = make_tilt_a_whirl_project()
    project.cars = project.cars[:1]
    # Point Car0 at an empty directory to trigger a missing-frame error.
    project.cars[0].sprite_dir = str(tmp_path)

    with pytest.raises(FrameSetError, match="Missing frame"):
        scan_project(project)
