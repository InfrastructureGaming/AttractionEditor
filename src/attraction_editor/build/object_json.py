"""Authors a ride's object.json from the project model: id/authors/version,
properties (type/category/cars/carColours), flatRideAnimation, images range,
and strings. See write_object_json's docstring."""

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


def _sprite_extents(project: RideProject) -> tuple[int, int, int, int]:
    """(left, right, above, below): max across all 4 directions of how far
    the structure extends from its anchor's origin point to each edge of the
    rendered frame (DirectionAnchor is the offset from the origin point to
    the image's top-left corner - see anchor_editor_panel.py's
    anchor_to_origin: origin sits at pixel (-x, -y)).

    Shared by invalidation_bounds (which doubles these for a rotation-safety
    margin - the screen-space redraw box must cover every rotation state, not
    just one) and write_object_json's cars block (which uses them as-is,
    undoubled - that's the car/structure's actual measured sprite bound, not
    an invalidation margin). Clamped at 0: an anchor placed outside the
    sprite's bounds (an authoring mistake, or a deliberately off-canvas
    origin) must not produce a negative extent.
    """
    left = max(0, max(-anchor.x for anchor in project.anchors))
    right = max(0, max(project.sprite_width + anchor.x for anchor in project.anchors))
    above = max(0, max(-anchor.y for anchor in project.anchors))
    below = max(0, max(project.sprite_height + anchor.y for anchor in project.anchors))
    return left, right, above, below


def invalidation_bounds(project: RideProject) -> tuple[int, int, int]:
    """(halfWidth, heightAbove, heightBelow) as uint8_t values (max 255),
    derived from _sprite_extents and doubled to cover the full rotation
    envelope. These are starting-point values; verify in-game and adjust as
    needed."""
    left, right, above, below = _sprite_extents(project)
    half_width = max(left, right)
    return (
        min(_UINT8_MAX, half_width * 2),
        min(_UINT8_MAX, above * 2),
        min(_UINT8_MAX, below * 2),
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
            if phase.play_reverse:
                phase_dict["playReverse"] = True
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


def cars_block(project: RideProject) -> dict:
    """Build the single 'cars' entry (carsPerFlatRide is always 1 for this
    tool's flat rides - RideProject.cars is a different concept, the
    rider-overlay sprite sets layered on top, not this engine-level vehicle
    descriptor). spriteWidth/spriteHeightNegative/Positive are derived from
    _sprite_extents rather than authored directly, same reasoning as
    invalidation_bounds. hasAdditionalColour1/2 are always true - every
    colour scheme this tool generates uses both the Trim (secondary,
    enableTrimColour) and Tertiary (enableTertiaryColour) zones, so both
    must be enabled or the engine won't actually apply that recolouring
    in-game even though carColours specifies it.

    spacing/mass are deliberately omitted - confirmed against Ride.cpp that
    the engine's train-validation logic (which is what reads them) only
    runs for tracked rides, skipped entirely whenever carsPerFlatRide is
    set, so they're inert for every ride this tool builds.
    """
    left, right, above, below = _sprite_extents(project)
    return {
        "rotationFrameMask": project.rotation_frame_mask,
        "tabOffset": project.car_tab_offset,
        "tabScale": project.car_tab_scale,
        "numSeats": project.car_num_seats,
        "spriteWidth": max(left, right),
        "spriteHeightNegative": above,
        "spriteHeightPositive": below,
        "carVisual": project.car_visual,
        "drawOrder": project.car_draw_order,
        "frames": {"flat": True},
        "recalculateSpriteBounds": True,
        "hasAdditionalColour1": True,
        "hasAdditionalColour2": True,
    }


def write_object_json(project: RideProject) -> dict:
    """Create or update project_dir/object.json from the project model.
    Returns the written data.

    This function fully owns every field needed for a flat ride object (id,
    authors, version, images, properties.type/category/cars/carColours,
    flatRideAnimation, strings) - the file no longer needs to exist
    beforehand. The one exception: invalidationHalfWidth/HeightAbove/
    HeightBelow are preserved from the existing file if already present,
    since they're often manually tuned after visually checking the ride
    in-game; everything else is always regenerated from the project model.

    properties.type is always "flat_ride_generic" - this project's own
    modular, self-contained flat-ride object type, built specifically so a
    wide variety of flat rides (this one included) can be driven entirely by
    a flatRideAnimation block rather than each needing its own hardcoded
    engine ride-type descriptor. rotationMode is omitted entirely for the
    same reason: it only matters for rides *without* a flatRideAnimation
    block (UpdateFlatRideGeneric() bypasses the hardcoded rotation-mode
    sprite maps once one exists, which it always does here, driven by
    Programs & Phases instead).
    """
    if project.project_dir is None:
        raise ValueError("RideProject.project_dir is not set")

    object_json_path = project.project_dir / OBJECT_JSON_FILENAME
    data = json.loads(object_json_path.read_text(encoding="utf-8")) if object_json_path.exists() else {}

    # invalidation bounds live under properties.flatRideAnimation in the
    # real schema (RideObject.cpp) - preserve from there if present.
    existing_animation = data.get("properties", {}).get("flatRideAnimation", {})
    preserved_bounds = {
        key: existing_animation[key]
        for key in ("invalidationHalfWidth", "invalidationHeightAbove", "invalidationHeightBelow")
        if key in existing_animation
    }

    data["id"] = project.id
    data["objectType"] = "ride"
    data["sourceGame"] = "custom"
    data["authors"] = list(project.authors)
    data["version"] = project.version
    data["images"] = [images_range_string(project)]

    properties = data.setdefault("properties", {})
    properties["type"] = "flat_ride_generic"
    properties["category"] = project.category
    properties.pop("rotationMode", None)
    properties["carsPerFlatRide"] = 1
    properties["carColours"] = colour_schemes_block(project)
    properties["cars"] = cars_block(project)
    # Always emitted, so it always replaces the generic flat-ride type's default
    # breakdown set for this ride (RideObject.cpp -> Ride::getAvailableBreakdowns).
    # An empty list means the ride never breaks down (see RideProject.breakdowns).
    properties["breakdowns"] = list(project.breakdowns)

    animation = flat_ride_animation_block(project)
    if animation is not None:
        animation.update(preserved_bounds)
        properties["flatRideAnimation"] = animation
    else:
        properties.pop("flatRideAnimation", None)

    strings = data.setdefault("strings", {})
    strings["name"] = {"en-GB": project.name}
    strings["description"] = {"en-GB": project.description}
    strings["capacity"] = {"en-GB": project.capacity_text}

    object_json_path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
    return data


def custom_ride_manifest(project: RideProject) -> dict:
    """Build the dict for manifest.json - a SEPARATE file from object.json/
    the .parkobj, read directly by this fork's CustomRideLoader.cpp at
    startup (not by RideObject.cpp) to register the ride with the
    research-bypass custom-rides platform: it's how the engine finds out a
    ride exists at all, before anything in the .parkobj is even consulted.

    CustomRideLoader.cpp iterates every subdirectory of the custom_rides
    folder looking for exactly "manifest.json" (the filename is fixed, not
    derived from the ride's name) - this dict is meant to be written there
    by build/package.py's write_custom_ride_manifest, in the same directory
    `deploy_parkobj` copies the .parkobj into.

    "parkobj" is the one field most likely to be gotten wrong: it must be
    the ride's *object id* (RideProject.id, matching object.json's own "id"
    field - how LoadObject() looks it up in the object repository), not the
    .parkobj filename, even though the two can look superficially similar.
    Get this wrong and the ride registers but its vehicle object silently
    fails to load (CustomRideLoader.cpp's "parkobj ... not found" warning).

    "description"/"author" are omitted when empty - the engine already
    defaults both to "" if absent (manifest.value(key, "")), so there's no
    behavioural difference, just a smaller file. "cost" is similarly
    omitted when <= 0 - CustomRideLoader.cpp only applies a build-cost
    override at all when cost > 0, so 0 means "use FlatRideGenericRTD's own
    default cost", not "free". "ratings" is always written (never omitted)
    - RideProject.rating_excitement/intensity/nausea default to 3/2/1,
    matching the engine's own fallback when "ratings" is absent entirely,
    so writing them is behaviourally identical to omitting the block, just
    one consistent code path instead of a conditional.

    "footprint" is likewise always written (never omitted) - it selects
    which TrackElemType CustomRideLoader.cpp registers the ride's
    StartTrackPiece as. base_footprint_width/length default to 6x6, matching
    every custom ride's behaviour before this field existed (FlatRideGenericRTD
    was hardcoded to TrackElemType::flatTrack6x6), so writing the default is
    behaviourally identical to omitting it.
    """
    manifest: dict = {
        "name": project.name,
        "parkobj": project.id,
        "ratings": {
            "excitement": project.rating_excitement,
            "intensity": project.rating_intensity,
            "nausea": project.rating_nausea,
        },
        "footprint": {
            "width": project.base_footprint_width,
            "length": project.base_footprint_length,
        },
    }
    if project.description:
        manifest["description"] = project.description
    if project.authors:
        manifest["author"] = project.authors[0]
    if project.build_cost > 0:
        manifest["cost"] = project.build_cost
    return manifest
