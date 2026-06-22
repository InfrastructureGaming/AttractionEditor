"""Generates a build summary report: the key values written to object.json
(flatRideAnimation block, images range, sprite anchors). The flatRideAnimation
block is generated automatically by object_json.py on every build — no manual
C++ editing or copy-paste is required."""

from __future__ import annotations

from attraction_editor.build.object_json import invalidation_bounds
from attraction_editor.model.project import RideProject
from attraction_editor.sprites.manifest import manifest_image_count


def generate_handoff_report(project: RideProject) -> str:
    """Human-readable summary of what was written to object.json on the last build."""
    image_count = manifest_image_count(project)
    half_width, height_above, height_below = invalidation_bounds(project)

    lines = [
        f"Build summary for {project.name} ({project.id})",
        "",
        "flatRideAnimation (auto-generated in object.json):",
        f"  framesPerDir          = {project.frames_per_dir}",
        f"  riderFrameStride      = {len(project.cars)}",
        f"  invalidationHalfWidth   = {half_width}",
        f"  invalidationHeightAbove = {height_above}",
        f"  invalidationHeightBelow = {height_below}",
        "",
        f"object.json images = $LGX:images.dat[0..{image_count - 1}] ({image_count} images)",
        "",
        "Per-direction sprite anchors (applied to sprite_manifest.json):",
    ]

    for direction, anchor in enumerate(project.anchors):
        lines.append(f"  dir{direction}: x={anchor.x}, y={anchor.y}")

    if project.programs:
        lines.extend(["", "Programs:"])
        for p_idx, program in enumerate(project.programs):
            lines.append(f"  [{p_idx}] {program.name} ({len(program.phases)} phases)")
            for ph_idx, phase in enumerate(program.phases):
                end_frame = phase.frame_start + phase.frame_count - 1
                flags = []
                if phase.repeat_until_rotations_complete:
                    flags.append("repeatUntilRotationsComplete")
                if phase.is_final_phase:
                    flags.append("isFinalPhase")
                if phase.reset_rotations_on_entry:
                    flags.append("resetRotationsOnEntry")
                flag_str = f"  [{', '.join(flags)}]" if flags else ""
                lines.append(
                    f"    phase {ph_idx} ({phase.name!r}): "
                    f"frames {phase.frame_start}..{end_frame}, "
                    f"{phase.ticks_per_frame} tick/frame"
                    f"{flag_str}"
                )
    else:
        lines.extend(["", "No programs defined (legacy single-program behaviour)."])

    return "\n".join(lines)
