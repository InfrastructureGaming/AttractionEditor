"""Approximates OpenRCT2's in-game colour remap for Blender-rendered sprite
frames, using the data extracted by tools/extract_palette.py.

Mirrors GfxDrawSpriteGetPalette's secondary/tertiary remap (see
feedback_sprite_packaging.md): a frame's pixels are matched to the nearest
StandardPalette entry (as `-m closest` does), then any pixel landing in the
secondary (202-213) or tertiary (46-57) remap ranges is replaced according to
the chosen body/trim Colour's 12-shade ramp.
"""

from __future__ import annotations

import json
from pathlib import Path
from functools import lru_cache

from PIL import Image

_DATA_DIR = Path(__file__).resolve().parent

SECONDARY_REMAP_START = 202
TERTIARY_REMAP_START = 46
PRIMARY_REMAP_START = 243
REMAP_LENGTH = 12


@lru_cache(maxsize=1)
def load_standard_palette() -> list[list[int]]:
    return json.loads((_DATA_DIR / "standard_palette.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_colour_ramps() -> dict[str, list[int]]:
    return json.loads((_DATA_DIR / "colour_ramps.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _palette_image() -> Image.Image:
    """A 1x1 "P" image carrying the full StandardPalette, suitable for
    Image.quantize(palette=...)."""
    img = Image.new("P", (1, 1))
    img.putpalette([component for rgb in load_standard_palette() for component in rgb])
    return img


def colour_swatch_rgb(colour: str) -> tuple[int, int, int]:
    """A representative RGB swatch for `colour`, taken from the middle of its
    12-shade ramp - useful for UI colour pickers."""
    ramp = load_colour_ramps()[colour]
    palette = load_standard_palette()
    index = ramp[len(ramp) // 2]
    r, g, b = palette[index]
    return (r, g, b)


def remap_preview(image: Image.Image, body_colour: str, trim_colour: str, primary_colour: str | None = None) -> Image.Image:
    """Return an RGBA copy of `image` with its secondary/tertiary remap-range
    pixels recoloured according to `body_colour`/`trim_colour`.

    `primary_colour`, if given, also remaps the primary range (243-254) -
    included for completeness even though no pixel from a `-m closest`
    Blender render can land there in practice.
    """
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")

    indexed = rgba.convert("RGB").quantize(palette=_palette_image(), dither=Image.Dither.NONE)

    ramps = load_colour_ramps()
    lut = list(range(256))
    for i in range(REMAP_LENGTH):
        lut[SECONDARY_REMAP_START + i] = ramps[body_colour][i]
        lut[TERTIARY_REMAP_START + i] = ramps[trim_colour][i]
    if primary_colour is not None:
        for i in range(REMAP_LENGTH):
            lut[PRIMARY_REMAP_START + i] = ramps[primary_colour][i]

    remapped = indexed.point(lut)
    remapped.putpalette([component for rgb in load_standard_palette() for component in rgb])

    result = remapped.convert("RGBA")
    result.putalpha(alpha)
    return result
