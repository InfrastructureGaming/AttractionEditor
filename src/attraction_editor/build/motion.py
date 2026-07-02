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

    `repeatable` marks this loop as the operator-controlled unit: compile_motion_program
    splits it into its own phase with resetRotationsOnEntry + repeatUntilRotationsComplete,
    so the ride's "number of rotations" operating setting drives how many times it plays.
    """

    turns: int
    ticks: int
    direction: int = 1
    easing: str = "linear"
    repeatable: bool = False


@dataclass
class Frames:
    """Raw frame-range playback, NOT angle-based: plays `start`..`end` inclusive,
    each frame held `ticks_per_frame` ticks. Direction is inferred - start <= end
    plays forward, start > end plays in reverse (so one door-open range, reversed,
    doubles as door-close). For doors, restraints, or any sub-animation whose frames
    aren't a function of rotation angle; indices are raw atlas positions, never
    remapped by the rotation resolution.
    """

    start: int
    end: int
    ticks_per_frame: int = 1


MotionSegment = Swing | Loop | Frames


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


def _frames_sequence(seg: Frames) -> list[int]:
    step = 1 if seg.start <= seg.end else -1
    ticks = max(1, seg.ticks_per_frame)
    out: list[int] = []
    for f in range(seg.start, seg.end + step, step):
        out.extend([f] * ticks)
    return out


def compile_motion(segments: list[MotionSegment], rotation_frames: int = ATLAS_FRAMES) -> list[int]:
    """Compile an ordered list of motion segments into the explicit per-tick
    atlas-frame sequence (the phase's time-to-sprite map). Segments are
    concatenated in order - each angular segment begins from rest-angle 0, so
    chaining a swing into a loop is continuous through the rest point.

    `rotation_frames` is the ROTATION atlas resolution (degrees -> frame) for the
    angular Swing/Loop segments; it is NOT the total sprite-sheet size. Frames
    segments emit raw indices and ignore it (e.g. a 360-frame rotation living in a
    392-frame sheet whose 361-391 are doors)."""
    frames: list[int] = []
    for seg in segments:
        if isinstance(seg, Frames):
            frames.extend(_frames_sequence(seg))
            continue
        if isinstance(seg, Swing):
            angles = _swing_angles(seg)
        elif isinstance(seg, Loop):
            angles = _loop_angles(seg)
        else:  # pragma: no cover - guards against a bad spec
            raise TypeError(f"unknown motion segment {type(seg).__name__}")
        frames.extend(angle_to_frame(a, rotation_frames) for a in angles)
    return frames


def segment_from_dict(d: dict) -> MotionSegment:
    """Rehydrate a Swing/Loop from its stored dict form (RideProject.motion holds
    plain dicts so it round-trips through JSON with no custom serialisation; the
    `kind` field is the discriminator)."""
    kind = d.get("kind")
    if kind == "swing":
        return Swing(
            amplitude=float(d["amplitude"]),
            cycles=int(d.get("cycles", 1)),
            ticks=int(d["ticks"]),
            easing=str(d.get("easing", "sine")),
        )
    if kind == "loop":
        return Loop(
            turns=int(d.get("turns", 1)),
            ticks=int(d["ticks"]),
            direction=int(d.get("direction", 1)),
            easing=str(d.get("easing", "linear")),
            repeatable=bool(d.get("repeatable", False)),
        )
    if kind == "frames":
        return Frames(
            start=int(d["start"]),
            end=int(d["end"]),
            ticks_per_frame=int(d.get("ticks_per_frame", 1)),
        )
    raise ValueError(f"unknown motion segment kind {kind!r}")


def compile_motion_spec(spec: list[dict], rotation_frames: int = ATLAS_FRAMES) -> list[int]:
    """compile_motion for a stored spec (list of dicts), as a single flat map.
    Used for pure-spin rides and tests; multi-phase rides use compile_motion_program."""
    return compile_motion([segment_from_dict(d) for d in spec], rotation_frames)


def compile_motion_program(spec: list[dict], rotation_frames: int = ATLAS_FRAMES) -> list[dict]:
    """Compile a linear motion spec into a MULTI-PHASE program (a list of phase
    dicts in object.json shape). The spec is split at every repeatable segment: a
    contiguous run of non-repeatable segments becomes one one-shot phase, and each
    repeatable Loop becomes its own phase carrying resetRotationsOnEntry +
    repeatUntilRotationsComplete - so the operator's "number of rotations" setting
    drives that loop's count while the intro (doors + build-up) and outro (settle +
    doors) around it play exactly once. The last phase is marked isFinalPhase; the
    engine defaults each phase's nextPhase to the following one, so the flow is
    sequential without emitting it. A spec with no repeatable segment yields a
    single final phase (equivalent to one compiled map).

    Each phase dict: {"spriteMap": [...], optionally "repeatUntilRotationsComplete",
    "resetRotationsOnEntry", "isFinalPhase"} - see build/object_json.py."""
    segments = [segment_from_dict(d) for d in spec]

    # Group into runs so each repeatable Loop stands alone as its own phase.
    groups: list[tuple[bool, list[MotionSegment]]] = []
    run: list[MotionSegment] = []
    for seg in segments:
        if isinstance(seg, Loop) and seg.repeatable:
            if run:
                groups.append((False, run))
                run = []
            groups.append((True, [seg]))
        else:
            run.append(seg)
    if run:
        groups.append((False, run))

    phases: list[dict] = []
    for is_repeatable, segs in groups:
        phase: dict = {"spriteMap": compile_motion(segs, rotation_frames)}
        if is_repeatable:
            phase["repeatUntilRotationsComplete"] = True
            phase["resetRotationsOnEntry"] = True
        phases.append(phase)
    if phases:
        phases[-1]["isFinalPhase"] = True
    return phases
