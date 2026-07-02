"""Tests for build/motion.py - the parametric motion compiler (motion spec ->
explicit per-tick atlas-frame time-to-sprite map)."""

from __future__ import annotations

from attraction_editor.build.motion import (
    ATLAS_FRAMES,
    Loop,
    Swing,
    angle_to_frame,
    compile_motion,
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
