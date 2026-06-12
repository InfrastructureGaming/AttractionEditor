"""Generates a handoff report listing the values that must be carried over
into the ride's RTD C++ header (FlatRideRotationDescriptor) after a
sprite/manifest change. C++ changes are manual + require a Visual Studio
rebuild - this tool never edits or builds C++ directly."""

from __future__ import annotations

from attraction_editor.model.project import RideProject
from attraction_editor.sprites.manifest import manifest_image_count

# uint8_t fields in FlatRideRotationDescriptor (RideData.h).
UINT8_MAX = 255


def generate_handoff_report(project: RideProject) -> str:
    """A human-readable report of the FlatRideRotationDescriptor fields
    implied by `project`, for hand-transfer into the ride's RTD header."""
    image_count = manifest_image_count(project)

    lines = [
        f"Handoff report for {project.name} ({project.id})",
        "",
        "FlatRideRotationDescriptor:",
        f"  FramesPerDir     = {project.frames_per_dir}",
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

    return "\n".join(lines)
