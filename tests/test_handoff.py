"""Tests for build/handoff.py against the real TiltAWhirl project, whose
FlatRideRotationDescriptor values (RiderFrameStride=7, image range
0..4098, anchors, InvalidationHalfWidth=255/170/170) are already known."""

from __future__ import annotations

import pytest

from attraction_editor.build.handoff import generate_animation_program_cpp, generate_handoff_report
from attraction_editor.model.project import AnimationPhase, AnimationProgram
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


def test_generate_animation_program_cpp_empty_programs(tmp_path):
    project = make_synthetic_project(tmp_path)
    assert project.programs == []

    assert generate_animation_program_cpp(project) == ""


def test_generate_animation_program_cpp(tmp_path):
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

    cpp = generate_animation_program_cpp(project)

    assert "static constexpr uint8_t kSyntheticProgram0Phase0[] = {" in cpp
    assert "    0, 1, 0xFF," in cpp
    assert "static constexpr uint8_t kSyntheticProgram0Phase1[] = {" in cpp
    assert "    2, 3, 0xFF," in cpp

    assert "static constexpr FlatRideAnimationPhase kSyntheticProgram0Phases[] = {" in cpp
    assert "{ kSyntheticProgram0Phase0, 1, false, false }, // 'Start' -> 'End'" in cpp
    assert "{ kSyntheticProgram0Phase1, 0, false, true }, // 'End' -> 'Start'" in cpp

    assert "static constexpr FlatRideAnimationProgram kSyntheticPrograms[] = {" in cpp
    assert "{ kSyntheticProgram0Phases, 2 }, // 'Normal'" in cpp

    assert ".Programs    = kSyntheticPrograms," in cpp
    assert ".NumPrograms = 1," in cpp


def test_generate_handoff_report_includes_programs(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.programs = [
        AnimationProgram(
            name="Normal",
            phases=[AnimationPhase(name="Only", frame_start=0, frame_count=2, is_final_phase=True)],
        ),
    ]

    report = generate_handoff_report(project)

    assert "TOTAL combined frames across all phases of all programs" in report
    assert "Animation programs/phases (paste alongside .FlatRideRotation = {...}):" in report
    assert "static constexpr FlatRideAnimationProgram kSyntheticPrograms[] = {" in report


def test_generate_handoff_report_omits_programs_when_empty(tmp_path):
    project = make_synthetic_project(tmp_path)
    assert project.programs == []

    report = generate_handoff_report(project)

    assert "Animation programs/phases" not in report
    assert "TOTAL combined frames" not in report
