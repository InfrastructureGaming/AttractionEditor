"""Tests for build/handoff.py against the real TiltAWhirl project, whose
FlatRideRotationDescriptor values (RiderFrameStride=7, image range
0..4098, anchors, InvalidationHalfWidth=255/170/170) are already known."""

from __future__ import annotations

import pytest

from attraction_editor.build.handoff import generate_handoff_report
from tests.fixtures.synthetic import make_synthetic_project
from tests.fixtures.tilt_a_whirl import TILT_A_WHIRL_DIR, make_tilt_a_whirl_project


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_generate_handoff_report_tilt_a_whirl():
    project = make_tilt_a_whirl_project()

    report = generate_handoff_report(project)

    assert "RiderFrameStride = 7" in report
    assert "FramesPerDir     = 128" in report
    assert "$LGX:images.dat[0..4098]" in report
    for direction, anchor in enumerate(project.anchors):
        assert f"dir{direction}: x={anchor.x}, y={anchor.y}" in report
    # sprite_width=122 -> 244 (uncapped); height neg/pos=85 -> 170
    assert "InvalidationHalfWidth   = 244" in report
    assert "InvalidationHeightAbove = 170" in report
    assert "InvalidationHeightBelow = 170" in report


def test_generate_handoff_report_caps_at_uint8_max(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.sprite_width = 200  # *2 = 400, should cap to 255

    report = generate_handoff_report(project)

    assert "InvalidationHalfWidth   = 255 (capped from sprite_width*2)" in report
