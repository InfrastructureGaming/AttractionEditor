"""Generates a handoff report listing the values that must be carried over
into the ride's RTD C++ header (FlatRideRotationDescriptor) after a
sprite/manifest change. C++ changes are manual + require a Visual Studio
rebuild - this tool never edits or builds C++ directly."""

from __future__ import annotations

import re

from attraction_editor.model.project import AnimationPhase, RideProject
from attraction_editor.sprites.manifest import manifest_image_count

# uint8_t fields in FlatRideRotationDescriptor (RideData.h).
UINT8_MAX = 255

# Values per line when emitting TimeToSpriteMap[] literals.
_MAP_VALUES_PER_LINE = 16


def _pascal_case(name: str) -> str:
    """"Tilt-A-Whirl" -> "TiltAWhirl", for generating kXxx C++ identifiers."""
    return "".join(word[:1].upper() + word[1:] for word in re.findall(r"[A-Za-z0-9]+", name))


def _time_to_sprite_map_values(phase: AnimationPhase) -> list[int]:
    """Expand a phase's [frame_start, frame_start + frame_count) range into a
    time-indexed sprite-frame sequence, each frame repeated ticks_per_frame
    times, terminated by the 0xFF end-of-phase sentinel."""
    values: list[int] = []
    for frame in range(phase.frame_start, phase.frame_start + phase.frame_count):
        values.extend([frame] * max(1, phase.ticks_per_frame))
    values.append(0xFF)
    return values


def _format_map_values(values: list[int]) -> list[str]:
    lines: list[str] = []
    for i in range(0, len(values), _MAP_VALUES_PER_LINE):
        chunk = values[i : i + _MAP_VALUES_PER_LINE]
        lines.append("    " + ", ".join(("0xFF" if v == 0xFF else str(v)) for v in chunk) + ",")
    return lines


def generate_animation_program_cpp(project: RideProject) -> str:
    """C++ literals for FlatRideAnimationPhase[]/FlatRideAnimationProgram[] and
    the TimeToSpriteMap[] arrays they reference, generated from
    project.programs - ready to paste into the ride's RTD header alongside
    `.FlatRideRotation = {...}`, following TiltAWhirl.h's kTiltAWhirlPrograms
    pattern. Returns "" if project.programs is empty (legacy single-program
    Start/Loop/End behaviour, FlatRideRotationDescriptor.Programs == nullptr)."""
    if not project.programs:
        return ""

    base = _pascal_case(project.name)
    lines: list[str] = []
    program_refs: list[tuple[str, int, str]] = []

    for p_idx, program in enumerate(project.programs):
        phases_name = f"k{base}Program{p_idx}Phases"
        phase_refs: list[str] = []

        for ph_idx, phase in enumerate(program.phases):
            map_name = f"k{base}Program{p_idx}Phase{ph_idx}"
            lines.append(f"static constexpr uint8_t {map_name}[] = {{")
            lines.extend(_format_map_values(_time_to_sprite_map_values(phase)))
            lines.append("};")
            lines.append("")
            phase_refs.append(map_name)

        lines.append(f"static constexpr FlatRideAnimationPhase {phases_name}[] = {{")
        for ph_idx, phase in enumerate(program.phases):
            map_name = phase_refs[ph_idx]
            if 0 <= phase.next_phase < len(program.phases):
                next_name = program.phases[phase.next_phase].name
            else:
                next_name = f"<out of range: {phase.next_phase}>"
            repeat = "true" if phase.repeat_until_rotations_complete else "false"
            final = "true" if phase.is_final_phase else "false"
            lines.append(
                f"    {{ {map_name}, {phase.next_phase}, {repeat}, {final} }}, "
                f"// {phase.name!r} -> {next_name!r}"
            )
        lines.append("};")
        lines.append("")
        program_refs.append((phases_name, len(program.phases), program.name))

    programs_name = f"k{base}Programs"
    lines.append(f"static constexpr FlatRideAnimationProgram {programs_name}[] = {{")
    for phases_name, num_phases, program_name in program_refs:
        lines.append(f"    {{ {phases_name}, {num_phases} }}, // {program_name!r}")
    lines.append("};")
    lines.append("")
    lines.append("// In FlatRideRotationDescriptor (.FlatRideRotation = {...}):")
    lines.append(f"//   .Programs    = {programs_name},")
    lines.append(f"//   .NumPrograms = {len(project.programs)},")

    return "\n".join(lines)


def generate_handoff_report(project: RideProject) -> str:
    """A human-readable report of the FlatRideRotationDescriptor fields
    implied by `project`, for hand-transfer into the ride's RTD header."""
    image_count = manifest_image_count(project)

    frames_per_dir_note = (
        " (TOTAL combined frames across all phases of all programs - see Programs below)"
        if project.programs
        else ""
    )

    lines = [
        f"Handoff report for {project.name} ({project.id})",
        "",
        "FlatRideRotationDescriptor:",
        f"  FramesPerDir     = {project.frames_per_dir}{frames_per_dir_note}",
        f"  RiderFrameStride = {len(project.cars)}",
        "",
        f"object.json images = $LGX:images.dat[0..{image_count - 1}] ({image_count} images)",
        "",
        "Per-direction sprite anchors (sprite_manifest.json, already applied):",
    ]
    for direction, anchor in enumerate(project.anchors):
        lines.append(f"  dir{direction}: x={anchor.x}, y={anchor.y}")

    half_width = min(UINT8_MAX, project.sprite_width * 2)
    height_above = min(UINT8_MAX, project.sprite_height_negative * 2)
    height_below = min(UINT8_MAX, project.sprite_height_positive * 2)

    lines.extend(
        [
            "",
            "Suggested invalidation bounds (uint8_t, max 255 - starting point only,",
            "doubling the sprite half-extents to cover the full rotation envelope;",
            "verify in-game and adjust, as TiltAWhirl's were):",
            f"  InvalidationHalfWidth   = {half_width}"
            + (" (capped from sprite_width*2)" if project.sprite_width * 2 > UINT8_MAX else ""),
            f"  InvalidationHeightAbove = {height_above}"
            + (" (capped from sprite_height_negative*2)" if project.sprite_height_negative * 2 > UINT8_MAX else ""),
            f"  InvalidationHeightBelow = {height_below}"
            + (" (capped from sprite_height_positive*2)" if project.sprite_height_positive * 2 > UINT8_MAX else ""),
        ]
    )

    animation_cpp = generate_animation_program_cpp(project)
    if animation_cpp:
        lines.extend(
            [
                "",
                "Animation programs/phases (paste alongside .FlatRideRotation = {...}):",
                "",
                animation_cpp,
            ]
        )

    return "\n".join(lines)
