"""Validates frame-set scanning against the real TiltAWhirl Frames directory
(384x265 canvas; Core_Static_0 is a static layer, Core_Anim_0 + every car is
an animated layer with frames_per_dir=384)."""

from __future__ import annotations

import pytest

from attraction_editor.model.project import Layer
from attraction_editor.sprites.scanner import FrameSetError, scan_layer, scan_project, scan_static_layer
from tests.fixtures.synthetic import make_multilayer_synthetic_project, write_static_layer_frames
from tests.fixtures.tilt_a_whirl import TILT_A_WHIRL_DIR, make_tilt_a_whirl_project


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_scan_project_finds_all_frame_sets():
    project = make_tilt_a_whirl_project()

    results = scan_project(project)

    assert set(results) == {
        "Core_Static_0", "Core_Anim_0", "Car0", "Car1", "Car2", "Car3", "Car4", "Car5", "Car6",
    }
    for name, info in results.items():
        assert info.width == 384
        assert info.height == 265
        if name == "Core_Static_0":
            assert info.frames_per_dir == 1
        else:
            assert info.frames_per_dir == 384


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_scan_project_detects_missing_frame(tmp_path):
    project = make_tilt_a_whirl_project()
    project.cars = project.cars[:1]
    # Point Car0 at an empty directory to trigger a missing-frame error.
    project.cars[0].sprite_dir = str(tmp_path)

    with pytest.raises(FrameSetError, match="Missing frame"):
        scan_project(project)


def test_scan_static_layer_finds_four_frames(tmp_path):
    sprite_dir = tmp_path / "Background"
    write_static_layer_frames(sprite_dir)

    info = scan_static_layer(sprite_dir)

    assert info.frames_per_dir == 1
    assert info.width > 0 and info.height > 0


def test_scan_static_layer_missing_frame_raises(tmp_path):
    sprite_dir = tmp_path / "Background"
    sprite_dir.mkdir()

    with pytest.raises(FrameSetError, match="Missing frame"):
        scan_static_layer(sprite_dir)


def test_scan_layer_dispatches_by_kind(tmp_path):
    static_dir = tmp_path / "Background"
    write_static_layer_frames(static_dir)
    static_layer = Layer(name="Background", sprite_dir="Background", kind="static")

    info = scan_layer(tmp_path, static_layer, frames_per_dir=8)
    assert info.frames_per_dir == 1


def test_scan_project_multilayer_finds_every_layer(tmp_path):
    project = make_multilayer_synthetic_project(tmp_path)

    results = scan_project(project)

    assert set(results) == {"Background", "Core", "Foreground"}
    assert results["Background"].frames_per_dir == 1
    assert results["Foreground"].frames_per_dir == 1
    assert results["Core"].frames_per_dir == project.frames_per_dir


def test_scan_project_dimension_mismatch_across_layers_raises(tmp_path):
    project = make_multilayer_synthetic_project(tmp_path)
    # Replace Background with a differently-sized static frame set.
    mismatched_dir = tmp_path / "Frames" / "Background"
    from PIL import Image

    for direction in range(4):
        Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(mismatched_dir / f"dir{direction}_f0000.png")

    with pytest.raises(FrameSetError, match="all layers must share one canvas size"):
        scan_project(project)
