"""Tests for build/motion.py - the parametric motion compiler (motion spec ->
explicit per-tick atlas-frame time-to-sprite map)."""

from __future__ import annotations

import pytest

from attraction_editor.build.motion import (
    ATLAS_FRAMES,
    Frames,
    Loop,
    Swing,
    angle_to_frame,
    compile_motion,
    compile_motion_program,
    compile_motion_spec,
    segment_from_dict,
)


def test_angle_to_frame_maps_and_wraps():
    assert angle_to_frame(0) == 0  # rest
    assert angle_to_frame(90) == 90
    assert angle_to_frame(-30) == 330  # negative wraps
    assert angle_to_frame(360) == 0  # full turn wraps to rest
    assert angle_to_frame(450) == 90


def test_angle_to_frame_scales_to_atlas_resolution():
    # A 120-frame atlas is 3-degree steps: 90 degrees -> frame 30.
    assert angle_to_frame(90, atlas_frames=120) == 30
    assert angle_to_frame(360, atlas_frames=120) == 0


def test_swing_starts_at_rest_and_hits_both_peaks():
    frames = compile_motion([Swing(amplitude=90, cycles=1, ticks=360)])
    assert len(frames) == 360
    assert frames[0] == 0  # begins at rest
    assert frames[90] == 90  # +90 peak a quarter of the way in
    assert frames[180] == 0  # back through rest at the half
    assert frames[270] == 270  # -90 peak (wraps to 270) at three-quarters


def test_swing_peak_frame_follows_amplitude():
    frames = compile_motion([Swing(amplitude=30, cycles=1, ticks=360)])
    assert frames[90] == 30  # +peak == amplitude
    assert frames[270] == 330  # -peak == 360 - amplitude


def test_swing_cycles_repeat_within_the_segment():
    # Two cycles over 360 ticks -> peaks at t=45 and t=225 (each cycle's quarter).
    frames = compile_motion([Swing(amplitude=60, cycles=2, ticks=360)])
    assert frames[45] == 60
    assert frames[225] == 60


def test_sine_vs_linear_swing_differ_between_peaks_but_share_them():
    sine = compile_motion([Swing(amplitude=90, cycles=1, ticks=360, easing="sine")])
    linear = compile_motion([Swing(amplitude=90, cycles=1, ticks=360, easing="linear")])
    # Same peak at the quarter point...
    assert sine[90] == 90 and linear[90] == 90
    # ...but the sine leads a linear (triangle) ramp between rest and peak.
    assert sine[45] == 64  # 90 * sin(pi/4)
    assert linear[45] == 45  # 90 * 0.5 (triangle)


def test_loop_linear_is_one_frame_per_degree_full_revolution():
    frames = compile_motion([Loop(turns=1, ticks=360)])
    assert frames == list(range(360))


def test_loop_multiple_turns_and_direction():
    two = compile_motion([Loop(turns=2, ticks=720)])
    assert len(two) == 720
    assert two[360] == 0 and two[450] == 90  # second revolution

    ccw = compile_motion([Loop(turns=1, ticks=360, direction=-1)])
    assert ccw[0] == 0
    assert ccw[90] == 270  # -90 degrees wraps to 270


def test_compile_concatenates_segments_in_order():
    frames = compile_motion([Swing(amplitude=45, cycles=1, ticks=90), Loop(turns=1, ticks=360)])
    assert len(frames) == 90 + 360
    assert frames[0] == 0  # swing begins at rest
    assert frames[90:] == list(range(360))  # the loop follows


def test_empty_and_zero_tick_segments_are_harmless():
    assert compile_motion([]) == []
    assert compile_motion([Swing(amplitude=90, cycles=1, ticks=0)]) == []


def test_atlas_frames_default_is_360():
    assert ATLAS_FRAMES == 360


def test_segment_from_dict_round_trips_both_kinds():
    assert segment_from_dict({"kind": "swing", "amplitude": 30, "cycles": 2, "ticks": 90, "easing": "linear"}) == Swing(
        amplitude=30, cycles=2, ticks=90, easing="linear"
    )
    assert segment_from_dict({"kind": "loop", "turns": 3, "ticks": 90, "direction": -1}) == Loop(
        turns=3, ticks=90, direction=-1
    )


def test_segment_from_dict_unknown_kind_raises():
    with pytest.raises(ValueError):
        segment_from_dict({"kind": "wobble", "ticks": 10})


def test_compile_motion_spec_from_stored_dicts():
    spec = [
        {"kind": "swing", "amplitude": 45, "cycles": 1, "ticks": 90},
        {"kind": "loop", "turns": 1, "ticks": 360},
    ]
    frames = compile_motion_spec(spec)
    assert len(frames) == 90 + 360
    assert frames[90:] == list(range(360))


# --- Frames (raw-range) segment: doors and other non-angular sub-animations ----


def test_frames_segment_plays_forward_and_reverse():
    assert compile_motion([Frames(start=361, end=364)]) == [361, 362, 363, 364]
    assert compile_motion([Frames(start=364, end=361)]) == [364, 363, 362, 361]


def test_frames_segment_holds_each_frame_ticks_per_frame():
    assert compile_motion([Frames(start=10, end=11, ticks_per_frame=3)]) == [10, 10, 10, 11, 11, 11]


def test_frames_are_raw_indices_ignoring_rotation_resolution():
    # Door frames (391..389) are emitted verbatim even above the 360 rotation res.
    assert compile_motion([Frames(391, 389)], rotation_frames=360) == [391, 390, 389]


def test_rotation_frames_maps_angles_while_frames_stay_raw():
    # A door range (raw) then a loop (angle -> frame over 360) in a 392-frame sheet.
    seq = compile_motion([Frames(391, 390), Loop(turns=1, ticks=4)], rotation_frames=360)
    assert seq == [391, 390, 0, 90, 180, 270]  # doors raw; loop 0,90,180,270 deg


def test_segment_from_dict_frames_and_repeatable_loop():
    assert segment_from_dict({"kind": "frames", "start": 391, "end": 361}) == Frames(391, 361)
    loop = segment_from_dict({"kind": "loop", "turns": 1, "ticks": 90, "repeatable": True})
    assert loop.repeatable is True


# --- compile_motion_program: linear spec -> multi-phase program -----------------


def test_program_splits_at_repeatable_loop_into_three_phases():
    spec = [
        {"kind": "frames", "start": 391, "end": 389},  # doors close
        {"kind": "swing", "amplitude": 90, "cycles": 1, "ticks": 4},
        {"kind": "loop", "turns": 1, "ticks": 4, "repeatable": True},  # operator loop
        {"kind": "frames", "start": 389, "end": 391},  # doors open
    ]
    phases = compile_motion_program(spec, rotation_frames=360)

    assert len(phases) == 3
    # intro: doors + build-up swing, plays once
    assert phases[0]["spriteMap"][:2] == [391, 390]
    assert "repeatUntilRotationsComplete" not in phases[0]
    assert "isFinalPhase" not in phases[0]
    # loop: its own repeatable/reset phase (operator rotations drive the count)
    assert phases[1]["repeatUntilRotationsComplete"] is True
    assert phases[1]["resetRotationsOnEntry"] is True
    assert "isFinalPhase" not in phases[1]
    # outro: doors open, final -> ride idles on the last frame (391)
    assert phases[2]["isFinalPhase"] is True
    assert phases[2]["spriteMap"] == [389, 390, 391]


def test_program_without_repeatable_is_a_single_final_phase():
    phases = compile_motion_program([{"kind": "loop", "turns": 1, "ticks": 360}])
    assert len(phases) == 1
    assert phases[0]["isFinalPhase"] is True
    assert "repeatUntilRotationsComplete" not in phases[0]
    assert phases[0]["spriteMap"] == list(range(360))


def test_program_each_repeatable_loop_is_its_own_phase():
    spec = [
        {"kind": "loop", "turns": 1, "ticks": 4, "repeatable": True},
        {"kind": "swing", "amplitude": 30, "cycles": 1, "ticks": 4},
        {"kind": "loop", "turns": 1, "ticks": 4, "repeatable": True},
    ]
    phases = compile_motion_program(spec, rotation_frames=360)
    assert len(phases) == 3
    assert phases[0]["repeatUntilRotationsComplete"] is True  # first loop
    assert "repeatUntilRotationsComplete" not in phases[1]  # the swing run
    assert phases[2]["repeatUntilRotationsComplete"] is True  # second loop
    assert phases[2]["isFinalPhase"] is True
