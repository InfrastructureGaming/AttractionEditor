"""Parametric motion compiler: turns a high-level motion spec (a sequence of
swing/loop segments) into an explicit per-tick time-to-sprite map over an angle
atlas.

Background: a single-axis rotating ride (Loop-O-Plane, pendulum, Ferris wheel...)
occupies a bounded pose space - one frame per degree covers *every* position it
can ever hold, rendered once. Instead of baking a specific animation sequence
frame-by-frame (where a long/complex motion costs many frames x 4 directions),
we render that 360-frame "angle atlas" and DRIVE the motion by choosing which
atlas frame to show each tick. This module produces that per-tick frame sequence
from parametric primitives, so motion length/complexity is decoupled from the
sprite count entirely.

The output is exactly the shape the engine already plays: FlatRideAnimationPhase's
TimeToSpriteMap (Vehicle.Animation.cpp's UpdateFlatRideGeneric reads
`phase.TimeToSpriteMap[time] -> flatRideAnimationFrame`). We just emit it
explicitly (build/object_json.py) rather than having the engine build it from a
contiguous frame range - so an arbitrary, eased motion works with zero playback
change.

Atlas convention: the artist renders a uniform 360-degree rotation starting from
rest, so atlas frame k is the ride at k degrees from rest (0-based). A motion
angle (degrees from rest, signed) maps to a frame via angle_to_frame(); negative
angles simply wrap (a swing of -30 degrees is atlas frame 330). Because the map
is an explicit arbitrary sequence, that wrap needs no special handling downstream.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# One frame per degree - the default atlas resolution. Lower is allowed (e.g. 120
# = 3-degree steps) for a smaller atlas; the compiler scales angles to whatever
# resolution is passed in.
ATLAS_FRAMES = 360

EASINGS = {"sine", "linear"}


@dataclass
class Swing:
    """Oscillate +/- `amplitude` degrees around rest for `cycles` complete
    back-and-forth swings, spread over `ticks` game ticks.

    easing "sine" (default) is the natural pendulum curve - angle = A*sin(...),
    which slows at the extremes and is fastest through rest, exactly like a real
    swing. "linear" is a triangle wave (constant angular speed, hard reversals) -
    mechanical, but occasionally wanted. Amplitude build-up (swings growing
    higher before a loop) is authored by chaining Swings of increasing amplitude.
    """

    amplitude: float
    cycles: int
    ticks: int
    easing: str = "sine"


@dataclass
class Loop:
    """Rotate `turns` complete 360-degree revolutions over `ticks` ticks,
    `direction` +1 (one way) or -1 (the other).

    easing "linear" (default) is a constant-speed rotation; "sine" eases the
    revolution in and out (accelerate then decelerate), useful for a single
    showcase loop rather than continuous spinning.
    """

    turns: int
    ticks: int
    direction: int = 1
    easing: str = "linear"


MotionSegment = Swing | Loop


def angle_to_frame(angle_deg: float, atlas_frames: int = ATLAS_FRAMES) -> int:
    """Map a motion angle (degrees from rest, any sign) to its atlas frame index.
    Negative and >360 angles wrap; rest (0) is frame 0."""
    return round(angle_deg * atlas_frames / 360.0) % atlas_frames


def _ease(frac: float, easing: str) -> float:
    """Remap a 0..1 progress fraction. "linear" is identity; "sine" is a smooth
    ease-in-out (0 and 1 velocity at the ends)."""
    if easing == "sine":
        return 0.5 - 0.5 * math.cos(math.pi * frac)
    return frac


def _swing_angles(seg: Swing) -> list[float]:
    if seg.ticks <= 0:
        return []
    angles = []
    for t in range(seg.ticks):
        # `cycles` full oscillations across the segment. A pure sine already eases
        # at the extremes; "linear" swaps in a triangle wave of the same period.
        phase = seg.cycles * 2.0 * math.pi * (t / seg.ticks)
        if seg.easing == "linear":
            # Triangle wave in [-1, 1]: 4/pi * arcsin(sin(phase)) normalised.
            oscillation = (2.0 / math.pi) * math.asin(math.sin(phase))
        else:
            oscillation = math.sin(phase)
        angles.append(seg.amplitude * oscillation)
    return angles


def _loop_angles(seg: Loop) -> list[float]:
    if seg.ticks <= 0:
        return []
    total = seg.direction * seg.turns * 360.0
    return [total * _ease(t / seg.ticks, seg.easing) for t in range(seg.ticks)]


def compile_motion(segments: list[MotionSegment], atlas_frames: int = ATLAS_FRAMES) -> list[int]:
    """Compile an ordered list of motion segments into the explicit per-tick
    atlas-frame sequence (the phase's time-to-sprite map). Segments are
    concatenated in order - each begins from rest-angle 0, so chaining a
    swing into a loop is continuous through the rest point."""
    frames: list[int] = []
    for seg in segments:
        if isinstance(seg, Swing):
            angles = _swing_angles(seg)
        elif isinstance(seg, Loop):
            angles = _loop_angles(seg)
        else:  # pragma: no cover - guards against a bad spec
            raise TypeError(f"unknown motion segment {type(seg).__name__}")
        frames.extend(angle_to_frame(a, atlas_frames) for a in angles)
    return frames
