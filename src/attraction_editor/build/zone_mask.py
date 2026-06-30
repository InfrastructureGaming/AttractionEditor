"""Reads per-zone recolour masks from a Blender multi-layer EXR (the "zone
pass") so the build can use *authored* remap-zone data instead of guessing
which pixels are recolourable by palette distance + catch-tolerance (see
build/dither.py's _apply_catch_tolerance_bias, the fallback for untagged
layers).

Each recolourable zone is one named RGBA layer inside the EXR (its own *part*,
in Blender's multi-part multi-layer output), rendered as a flat AOV stencil:
nonzero where the material belongs to that zone, zero elsewhere. Authored raw (non-colour / no view transform), so the values are
exact 0.0/1.0 with no antialiasing at the boundaries - confirmed against real
Tilt-A-Whirl renders, the mask is pixel-perfect and 1:1 aligned with the beauty
frame. The artist adds zones incrementally by wiring more AOV layers into the
single File Output node; layers that aren't present are simply skipped here.

EXR (float) rather than PNG keeps the stencil exact - no 8-bit quantisation and
no gamma/view-transform mangling of the values (a PNG zone value of 1.0 came
back as 0.5 through the display transform during bring-up).

Layer naming maps to our internal remap zones (palette/remap.py). The canonical
names are COLOR<n>, numbered in the engine's colour-slot order (the same order
the ride colour pickers and GenericFlatRide paint use), which reads more
naturally than the role names and extends cleanly if a 4th remap colour is ever
added (COLOR4 beats "quaternary"):
  COLOR1  -> primary remap   (player's Main/body colour)
  COLOR2  -> secondary remap (player's Trim / "Additional Color 1")
  COLOR3  -> tertiary remap  (player's Tertiary / "Additional Color 2")
The primary zone is newly authorable: the distance-based path could never target
the primary range because openrct2-cli's -m closest excludes it, but an explicit
mask lets the zone-constrained quantiser place those pixels deliberately.

The earlier descriptive names (COLOR_PRIMARY/COLOR_TRIM/COLOR_TERTIARY, used by
the first Tilt-A-Whirl zone passes) are still recognised so those EXRs keep
building until re-authored with COLOR<n>.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# EXR layer name -> internal remap-zone key (matches the zone vocabulary the
# dithering/classification code uses).
ZONE_LAYER_NAMES = {
    # Canonical COLOR<n> naming (n = engine colour-slot order).
    "COLOR1": "primary",
    "COLOR2": "secondary",
    "COLOR3": "tertiary",
    # Legacy descriptive names (early Tilt-A-Whirl passes) - kept for back-compat.
    "COLOR_PRIMARY": "primary",
    "COLOR_TRIM": "secondary",
    "COLOR_TERTIARY": "tertiary",
}

# Authored masks are raw 0/1 with no antialiasing, so any sensible cut works;
# 0.5 is exact for the agreed convention and ignores stray near-zero noise.
_MASK_THRESHOLD = 0.5


def read_zone_masks(exr_path: str | Path) -> dict[str, np.ndarray]:
    """Return ``{zone_key: bool mask of shape (H, W)}`` for every recognised
    zone layer present in `exr_path`.

    A pixel is "in" a zone where that layer's strongest channel exceeds
    `_MASK_THRESHOLD` (robust to which channel the artist routed the flat value
    through). Unrecognised layers and absent zones are omitted, so a partially
    authored pass (e.g. only COLOR_TRIM wired up) reads back exactly the zones
    that are there - the caller treats missing zones as empty.

    Uses OpenEXR's multi-part File API, which normalises both layouts Blender
    emits: a multi-part EXR (each zone its own part) and a single-part
    multi-channel EXR (zones as COLOR_*.R/G/B/A channel groups) both surface
    here as one grouped channel per zone, named after the zone, with an
    (H, W, components) pixel array - and in the file's native dtype (Blender's
    File Output writes half floats). The earlier single-part InputFile reader
    read only part 0, silently dropping every zone after the first, and assumed
    32-bit floats; both are fixed here.
    """
    import OpenEXR

    masks: dict[str, np.ndarray] = {}
    exr = OpenEXR.File(str(exr_path))
    for part in exr.parts:
        for channel_name, channel in part.channels.items():
            zone_key = ZONE_LAYER_NAMES.get(channel_name)
            if zone_key is None:
                continue
            values = np.asarray(channel.pixels)
            if values.ndim == 3:
                values = values.max(axis=-1)
            masks[zone_key] = values > _MASK_THRESHOLD
    return masks
