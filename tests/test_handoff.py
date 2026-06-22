"""Tests for build/handoff.py: build summary report (framesPerDir,
riderFrameStride, invalidation bounds, programs listing)."""

from __future__ import annotations

import pytest

from attraction_editor.build.handoff import generate_handoff_report
from attraction_editor.model.project import AnimationPhase, AnimationProgram
from tests.fixtures.synthetic import make_synthetic_project
from tests.fixtures.tilt_a_whirl import TILT_A_WHIRL_DIR, make_tilt_a_whirl_project


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_generate_handoff_report_tilt_a_whirl():
    project = make_tilt_a_whirl_project()

    report = generate_handoff_report(project)

    assert "riderFrameStride      = 7" in report
    assert "framesPerDir          = 384" in report
    assert "$LGX:images.dat[0..12290]" in report
    for direction, anchor in enumerate(project.anchors):
        assert f"dir{direction}: x={anchor.x}, y={anchor.y}" in report
    # sprite_width=122 -> 244 (uncapped); height neg/pos=85 -> 170
    assert "invalidationHalfWidth   = 244" in report
    assert "invalidationHeightAbove = 170" in report
    assert "invalidationHeightBelow = 170" in report


def test_generate_handoff_report_caps_at_uint8_max(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.sprite_width = 200  # *2 = 400, capped to 255

    report = generate_handoff_report(project)

    assert "invalidationHalfWidth   = 255" in report


def test_generate_handoff_report_includes_programs(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.programs = [
        AnimationProgram(
            name="Normal",
            phases=[
                AnimationPhase(name="Start", frame_start=0, frame_count=2, next_phase=1),
                AnimationPhase(name="End", frame_start=2, frame_count=2, next_phase=0, is_final_phase=True),
            ],
        ),
    ]

    report = generate_handoff_report(project)

    assert "Programs:" in report
    assert "[0] Normal (2 phases)" in report
    assert "phase 0 ('Start'): frames 0..1, 1 tick/frame" in report
    assert "phase 1 ('End'): frames 2..3, 1 tick/frame" in report
    assert "[isFinalPhase]" in report


def test_generate_handoff_report_flags(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.programs = [
        AnimationProgram(
            name="Prog",
            phases=[
                AnimationPhase(
                    name="Spin",
                    frame_start=0,
                    frame_count=4,
                    ticks_per_frame=2,
                    next_phase=0,
                    repeat_until_rotations_complete=True,
                    reset_rotations_on_entry=True,
                ),
            ],
        ),
    ]

    report = generate_handoff_report(project)

    assert "frames 0..3, 2 tick/frame" in report
    assert "repeatUntilRotationsComplete" in report
    assert "resetRotationsOnEntry" in report


def test_generate_handoff_report_omits_programs_when_empty(tmp_path):
    project = make_synthetic_project(tmp_path)
    assert project.programs == []

    report = generate_handoff_report(project)

    assert "Programs:" not in report
    assert "No programs defined" in report
