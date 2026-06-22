"""Updates a ride's object.json: "images" range, "flatRideAnimation" block,
and properties.carColours (default colour schemes)."""

from __future__ import annotations

import json
from pathlib import Path

from attraction_editor.model.project import RideProject
from attraction_editor.sprites.manifest import manifest_image_count

OBJECT_JSON_FILENAME = "object.json"

_UINT8_MAX = 255


def images_range_string(project: RideProject) -> str:
    """The `$LGX:images.dat[0..N-1]` range string for `project`'s manifest."""
    count = manifest_image_count(project)
    return f"$LGX:images.dat[0..{count - 1}]"


def invalidation_bounds(project: RideProject) -> tuple[int, int, int]:
    """(halfWidth, heightAbove, heightBelow) as uint8_t values (max 255).

    Doubles the sprite half-extents to cover the full rotation envelope.
    These are starting-point values; verify in-game and adjust as needed.
    """
    return (
        min(_UINT8_MAX, project.sprite_width * 2),
        min(_UINT8_MAX, project.sprite_height_negative * 2),
        min(_UINT8_MAX, project.sprite_height_positive * 2),
    )


def flat_ride_animation_block(project: RideProject) -> dict | None:
    """Build the 'flatRideAnimation' dict from the project model.

    Returns None if the project has no programs (legacy single-program rides
    that don't use the flatRideAnimation JSON block).
    """
    if not project.programs:
        return None

    half_width, height_above, height_below = invalidation_bounds(project)

    programs_json = []
    for program in project.programs:
        phases_json = []
        for phase in program.phases:
            phase_dict: dict = {
                "startFrame": phase.frame_start,
                "endFrame": phase.frame_start + phase.frame_count - 1,
                "ticksPerFrame": phase.ticks_per_frame,
            }
            if not phase.is_final_phase:
                phase_dict["nextPhase"] = phase.next_phase
            if phase.repeat_until_rotations_complete:
                phase_dict["repeatUntilRotationsComplete"] = True
            if phase.is_final_phase:
                phase_dict["isFinalPhase"] = True
            if phase.reset_rotations_on_entry:
                phase_dict["resetRotationsOnEntry"] = True
            phases_json.append(phase_dict)
        programs_json.append({"phases": phases_json})

    return {
        "framesPerDir": project.frames_per_dir,
        "riderFrameStride": len(project.cars),
        "invalidationHalfWidth": half_width,
        "invalidationHeightAbove": height_above,
        "invalidationHeightBelow": height_below,
        "programs": programs_json,
    }


def colour_schemes_block(project: RideProject) -> list:
    """Build the 'carColours' array (RideObject::ReadJsonCarColours,
    RideObject.cpp - generic to any ride object, no engine changes needed)
    from project.colour_schemes. The engine picks one preset at random when
    the ride is placed; the ride stays fully recolourable by the player
    afterward - this is a starting point, never baked into the sprites.

    Schema (matching rct2.ride.twist1.json's carColours exactly): a list of
    presets, each preset a one-element list wrapping a single [Body, Trim,
    Tertiary] triple - ReadJsonCarColours only ever reads the first car's
    triple out of each preset regardless of car count. Body has no visible
    effect on our sprites (see model.project.ColourScheme) so it's defaulted
    to the Trim colour - inert, but keeps the JSON self-consistent rather
    than an arbitrary placeholder.
    """
    return [[[scheme.trim_colour, scheme.trim_colour, scheme.tertiary_colour]] for scheme in project.colour_schemes]


def update_object_json(project: RideProject) -> dict:
    """Load project_dir/object.json, update "images" and "flatRideAnimation"
    from the project model, and write it back. Returns the updated data.

    Invalidation bounds (invalidationHalfWidth/HeightAbove/HeightBelow) are
    preserved from the existing JSON if already present, since they are often
    manually tuned after the first build. All other flatRideAnimation fields
    (framesPerDir, riderFrameStride, programs) are always recomputed.
    """
    if project.project_dir is None:
        raise ValueError("RideProject.project_dir is not set")

    object_json_path = project.project_dir / OBJECT_JSON_FILENAME
    data = json.loads(object_json_path.read_text(encoding="utf-8"))
    data["images"] = [images_range_string(project)]

    animation = flat_ride_animation_block(project)
    if animation is not None:
        existing = data.get("flatRideAnimation", {})
        for key in ("invalidationHalfWidth", "invalidationHeightAbove", "invalidationHeightBelow"):
            if key in existing:
                animation[key] = existing[key]
        data["flatRideAnimation"] = animation

    data.setdefault("properties", {})["carColours"] = colour_schemes_block(project)

    object_json_path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
    return data
