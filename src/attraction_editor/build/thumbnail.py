"""Renders a ride's preview thumbnail to the exact size the engine's New Ride /
construction-window preview expects.

The preview is drawn by GfxDrawSpriteRawMasked against a 112x112 mask
(SPR_NEW_RIDE_MASK, kScrollItemSize 116 minus a 2px inset on each side). The
*correct* masked draw - feathered border, clipped to the box - only runs when
both the mask and the preview sprite carry G1Flag::hasTransparency, which a
flat "raw"-format sprite does but an RLE one does not (ImageImporter.cpp). So
sprites/manifest.py builds the file produced here with "format": "raw", and
this module's only job is to make sure the pixels are 112x112 with the ride
centered - the masked draw aligns the sprite to the mask's top-left and ignores
the sprite's own offset, so centering has to be baked into the raster itself.

Palette quantization is deliberately NOT done here: the build runs
`openrct2-cli sprite build ... -m closest`, which quantizes every sprite
(thumbnail included) to the OpenRCT2 palette, exactly as it does for the car
overlays. Pre-quantizing would only risk diverging from that.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

# Matches the New Ride preview's visible area: kScrollItemSize (116) drawn at a
# +2px inset on each side -> 112x112 (NewRide.cpp / SPR_NEW_RIDE_MASK).
THUMBNAIL_SIZE = 112

# Name of the rendered thumbnail file the build writes into its temp dir.
THUMBNAIL_FILENAME = "_thumbnail.png"


def fit_to_thumbnail(image: Image.Image, size: int = THUMBNAIL_SIZE) -> Image.Image:
    """Return `image` fitted into a size x size transparent RGBA canvas:
    shrunk (never enlarged) to fit while preserving aspect ratio, then centered.

    Shrink-only because the common source is a full-size structure frame
    (hundreds of px) that must come down to 112; a source already <= 112 is
    left at its native resolution and simply centered, rather than upscaled
    into blur. Transparent padding fills the rest, so the masked preview draw
    feathers cleanly around the ride.
    """
    src = image.convert("RGBA")
    if src.width > size or src.height > size:
        src = src.copy()
        src.thumbnail((size, size), Image.LANCZOS)  # preserves aspect, downscale only

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = ((size - src.width) // 2, (size - src.height) // 2)
    canvas.alpha_composite(src, offset)
    return canvas


def render_thumbnail(source_path: Path, out_path: Path, size: int = THUMBNAIL_SIZE) -> Path:
    """Load `source_path`, fit it to `size`x`size` (see fit_to_thumbnail), and
    write the result to `out_path`. Returns `out_path`."""
    with Image.open(source_path) as im:
        thumb = fit_to_thumbnail(im, size)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    thumb.save(out_path)
    return out_path
