"""Reads per-zone recolour masks from a Blender multi-layer EXR (the "zone
pass") so the build can use *authored* remap-zone data instead of guessing
which pixels are recolourable by palette distance + catch-tolerance (see
build/dither.py's _apply_catch_tolerance_bias, the fallback for untagged
layers).

Each recolourable zone is one named RGBA layer inside the EXR, rendered as a
flat Blender AOV stencil: nonzero where the material belongs to that zone, zero
elsewhere. Authored raw (non-colour / no view transform), so the values are
exact 0.0/1.0 with no antialiasing at the boundaries - confirmed against real
Tilt-A-Whirl renders, the mask is pixel-perfect and 1:1 aligned with the beauty
frame. The artist adds zones incrementally by wiring more AOV layers into the
single File Output node; layers that aren't present are simply skipped here.

EXR (float) rather than PNG keeps the stencil exact - no 8-bit quantisation and
no gamma/view-transform mangling of the values (a PNG zone value of 1.0 came
back as 0.5 through the display transform during bring-up).

Layer naming maps to our internal remap zones (palette/remap.py):
  COLOR_TRIM      -> secondary remap (player's Trim colour)
  COLOR_TERTIARY  -> tertiary remap  (player's Tertiary colour)
  COLOR_PRIMARY   -> primary remap   (player's Main/body colour) - newly
                     authorable: the distance-based path could never target the
                     primary range because openrct2-cli's -m closest excludes
                     it, but an explicit mask lets the zone-constrained
                     quantiser place those pixels deliberately.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# EXR layer name -> internal remap-zone key (matches the zone vocabulary the
# dithering/classification code uses).
ZONE_LAYER_NAMES = {
    "COLOR_TRIM": "secondary",
    "COLOR_TERTIARY": "tertiary",
    "COLOR_PRIMARY": "primary",
}

# Authored masks are raw 0/1 with no antialiasing, so any sensible cut works;
# 0.5 is exact for the agreed convention and ignores stray near-zero noise.
_MASK_THRESHOLD = 0.5


def read_zone_masks(exr_path: str | Path) -> dict[str, np.ndarray]:
    """Return ``{zone_key: bool mask of shape (H, W)}`` for every recognised
    zone layer present in `exr_path`.

    A pixel is "in" a zone where that layer's strongest colour channel exceeds
    `_MASK_THRESHOLD` (robust to which channel the artist routed the flat value
    through). Unrecognised layers and absent zones are omitted, so a partially
    authored pass (e.g. only COLOR_TRIM wired up) reads back exactly the zones
    that are there - the caller treats missing zones as empty.
    """
    import Imath
    import OpenEXR

    exr = OpenEXR.InputFile(str(exr_path))
    try:
        header = exr.header()
        window = header["dataWindow"]
        width = window.max.x - window.min.x + 1
        height = window.max.y - window.min.y + 1
        available = set(header["channels"].keys())
        pixel_type = Imath.PixelType(Imath.PixelType.FLOAT)

        masks: dict[str, np.ndarray] = {}
        for layer_name, zone_key in ZONE_LAYER_NAMES.items():
            colour_channels = [f"{layer_name}.{c}" for c in ("R", "G", "B") if f"{layer_name}.{c}" in available]
            if not colour_channels:
                continue
            stacked = np.stack(
                [
                    np.frombuffer(exr.channel(channel, pixel_type), dtype=np.float32).reshape(height, width)
                    for channel in colour_channels
                ],
                axis=-1,
            )
            masks[zone_key] = stacked.max(axis=-1) > _MASK_THRESHOLD
        return masks
    finally:
        exr.close()
