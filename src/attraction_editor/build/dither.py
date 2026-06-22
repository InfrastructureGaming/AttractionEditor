"""Dithered palette quantisation for ride layer frame PNGs: Floyd-Steinberg,
Bayer (ordered), and Atkinson, selectable per layer (see model.project.Layer).

Applies dithering before the openrct2-cli sprite-build step so that smooth
EEVEE lighting gradients are reproduced as dithered palette transitions rather
than hard quantisation bands. Floyd-Steinberg and Atkinson are both
error-diffusion - each pixel's result depends on its neighbourhood - so
applying either to every frame of an animated layer independently causes the
dither pattern to drift frame to frame ("jitter"/"boiling"). Bayer's threshold
depends only on pixel position, not neighbours, so it's the only one of the
three immune to that - but which algorithm a given layer uses is always the
layer author's choice (Layer.dither_algorithm), not inferred from Layer.kind.

Primary-remap palette entries (243-254) are excluded from the output, matching
openrct2-cli's IsChangablePixel() behaviour which also excludes that range from
nearest-colour matching.  Output pixels carry exact StandardPalette RGB values
so that the subsequent -m closest pass finds exact matches with no residual
quantisation error.

This is also where RideProject.trim_catch_tolerance/tertiary_catch_tolerance
actually take effect for the *shipped* sprite (see dither_frame_by_algorithm's
docstring and _apply_catch_tolerance_bias below). The colour-scheme preview
(palette/remap.py's remap_preview) has its own, separate classification, but
the real build never calls that - the secondary/tertiary zone a pixel ends up
in for the shipped sprite is decided entirely by whichever quantisation pass
runs here.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image

from attraction_editor.palette.remap import (
    PRIMARY_REMAP_START,
    REMAP_LENGTH,
    SECONDARY_REMAP_START,
    TERTIARY_REMAP_START,
    classify_remap_zone,
    load_standard_palette,
    pixel_distances_to_palette,
)

# A colour that no EEVEE-rendered pixel will ever be near, used to fill the
# excluded primary-remap palette slots so F-S never assigns pixels there.
_SENTINEL_RGB = (0, 255, 0)  # pure green; absent from both remap zones and normal geometry


@lru_cache(maxsize=1)
def _build_quantise_palette() -> Image.Image:
    """PIL P-mode image for Image.quantize(), with primary-remap slots (243-254)
    replaced by a sentinel colour so F-S never assigns pixels to those indices."""
    entries = [list(rgb) for rgb in load_standard_palette()]
    for i in range(PRIMARY_REMAP_START, PRIMARY_REMAP_START + REMAP_LENGTH):
        entries[i] = list(_SENTINEL_RGB)
    pal_img = Image.new("P", (1, 1))
    pal_img.putpalette([c for rgb in entries for c in rgb])
    return pal_img


@lru_cache(maxsize=1)
def _real_palette_flat() -> list[int]:
    """Flat [R,G,B, R,G,B, ...] list for the real StandardPalette."""
    return [c for rgb in load_standard_palette() for c in rgb]


@lru_cache(maxsize=REMAP_LENGTH)
def _nearest_valid_index(sentinel_idx: int) -> int:
    """Nearest non-primary-remap palette index to `sentinel_idx`, by RGB distance.
    Used as a safety net; in practice F-S should never land on sentinel slots."""
    palette = load_standard_palette()
    r, g, b = palette[sentinel_idx]
    best_idx, best_dist = 0, float("inf")
    for i, (pr, pg, pb) in enumerate(palette):
        if PRIMARY_REMAP_START <= i < PRIMARY_REMAP_START + REMAP_LENGTH:
            continue
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx


def _fix_sentinel_pixels(indexed: Image.Image) -> None:
    """In-place: replace any pixel at a primary-remap index with the nearest
    valid palette index.  This is a defensive pass; well-rendered frames
    should produce zero sentinel hits."""
    px = indexed.load()
    w, h = indexed.size
    for y in range(h):
        for x in range(w):
            idx = px[x, y]  # type: ignore[index]
            if PRIMARY_REMAP_START <= idx < PRIMARY_REMAP_START + REMAP_LENGTH:
                px[x, y] = _nearest_valid_index(idx)  # type: ignore[index]


def dither_frame(img: Image.Image) -> Image.Image:
    """Return an RGBA copy of `img` with Floyd-Steinberg dithering into the
    RCT2 StandardPalette, preserving the alpha channel.

    Primary-remap indices (243-254) are excluded from the quantisation target,
    so the result is safe to pass to openrct2-cli -m closest.  Every output
    pixel is the exact RGB value of its assigned StandardPalette entry.
    """
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")

    # Quantise RGB with F-S dithering.  The sentinel palette ensures that
    # primary-remap slots lose every nearest-neighbour race.
    indexed = rgba.convert("RGB").quantize(
        palette=_build_quantise_palette(),
        dither=Image.Dither.FLOYDSTEINBERG,
    )

    # Safety net: remap any pixel that landed on a sentinel index.
    _fix_sentinel_pixels(indexed)

    # Expand to RGB using the REAL palette so pixel values are exact
    # StandardPalette colours that -m closest will match exactly.
    real_pal = indexed.copy()
    real_pal.putpalette(_real_palette_flat())
    rgb_result = real_pal.convert("RGB")

    result = rgb_result.convert("RGBA")
    result.putalpha(alpha)
    return result


@lru_cache(maxsize=1)
def _bayer_matrix_8x8() -> np.ndarray:
    """Standard recursive 8x8 Bayer threshold matrix, values 0..63."""
    base = np.array([[0, 2], [3, 1]], dtype=np.float64)
    matrix = base
    while matrix.shape[0] < 8:
        n = matrix.shape[0]
        matrix = np.block(
            [
                [4 * matrix + 0, 4 * matrix + 2],
                [4 * matrix + 3, 4 * matrix + 1],
            ]
        )
    return matrix.astype(np.int64)


def dither_frame_bayer(img: Image.Image, *, strength: int = 32) -> Image.Image:
    """Return an RGBA copy of `img` ordered-dithered into the RCT2
    StandardPalette using a tiled 8x8 Bayer threshold matrix, preserving the
    alpha channel.

    Unlike dither_frame (Floyd-Steinberg), the perturbation applied to each
    pixel depends only on (x, y) mod 8 and that pixel's own colour - never on
    neighbouring pixels - so the same spatial noise pattern repeats on every
    frame of an animation instead of drifting ("boiling") frame to frame.

    `strength` is the full perturbation range in palette RGB units (centered
    on the source colour); 0 degenerates to plain nearest-colour matching.
    """
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")

    arr = np.asarray(rgba.convert("RGB"), dtype=np.float64)
    h, w = arr.shape[:2]

    tile = np.tile(_bayer_matrix_8x8(), (h // 8 + 1, w // 8 + 1))[:h, :w]
    offset = (tile / 63.0 - 0.5) * strength

    perturbed = np.clip(arr + offset[:, :, None], 0, 255).astype(np.uint8)
    perturbed_img = Image.fromarray(perturbed, mode="RGB")

    indexed = perturbed_img.quantize(palette=_build_quantise_palette(), dither=Image.Dither.NONE)
    _fix_sentinel_pixels(indexed)

    real_pal = indexed.copy()
    real_pal.putpalette(_real_palette_flat())
    result = real_pal.convert("RGB").convert("RGBA")
    result.putalpha(alpha)
    return result


# Classic Atkinson kernel: 1/8 of each pixel's quantisation error is pushed to
# each of 6 neighbours (east x2, south-west/south/south-east, further-south),
# so only 6/8 = 3/4 of the error is diffused at all - the rest is simply
# dropped, giving a sparser, higher-contrast dither than Floyd-Steinberg.
_ATKINSON_OFFSETS = ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2))


def dither_frame_atkinson(img: Image.Image, *, strength: int = 32) -> Image.Image:
    """Return an RGBA copy of `img` Atkinson-dithered into the RCT2
    StandardPalette, preserving the alpha channel.

    Like dither_frame (Floyd-Steinberg), this is error-diffusion - each
    pixel's quantisation error depends on its neighbourhood, so dithering an
    animated frame sequence with this algorithm will jitter the same way
    Floyd-Steinberg does. Provided as a per-layer author choice, not
    recommended for animated layers.

    `strength` scales the fraction of error diffused (32 ~= classic Atkinson
    at full RGB-unit error; 0 degenerates to plain nearest-colour matching).
    """
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")

    palette = load_standard_palette()
    valid_indices = [i for i in range(len(palette)) if not (PRIMARY_REMAP_START <= i < PRIMARY_REMAP_START + REMAP_LENGTH)]
    valid_palette = np.array([palette[i] for i in valid_indices], dtype=np.float64)

    arr = np.asarray(rgba.convert("RGB"), dtype=np.float64).copy()
    h, w = arr.shape[:2]
    diffuse_fraction = min(1.0, max(0.0, strength / 32.0)) / 8.0

    for y in range(h):
        for x in range(w):
            old = arr[y, x].copy()
            dists = np.sum((valid_palette - old) ** 2, axis=1)
            nearest = valid_palette[int(np.argmin(dists))]
            arr[y, x] = nearest
            error = old - nearest
            for dx, dy in _ATKINSON_OFFSETS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    arr[ny, nx] = arr[ny, nx] + error * diffuse_fraction

    result_rgb = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGB")
    result = result_rgb.convert("RGBA")
    result.putalpha(alpha)
    return result


def _apply_catch_tolerance_bias(img: Image.Image, trim_tolerance: int, tertiary_tolerance: int) -> Image.Image:
    """Pre-snap borderline pixels toward (or away from) the secondary/
    tertiary remap zones before quantising, per RideProject's
    trim_catch_tolerance/tertiary_catch_tolerance.

    At tolerance=0 for both zones, this is a pure no-op - returns `img`
    unchanged - so existing dithering output is byte-identical whenever the
    feature isn't in use. For a nonzero tolerance, only the specific pixels
    whose zone classification actually *changes* (classify_remap_zone's
    `caught & ~natural_win`, pulled in by widening, or `natural_win &
    ~caught`, excluded by narrowing) are touched; pixels that already
    resolve correctly on their own keep their exact original RGB, so the
    residual quantisation error they naturally contribute to error-diffusion
    dithering (Floyd-Steinberg/Atkinson) is undisturbed.
    """
    if trim_tolerance == 0 and tertiary_tolerance == 0:
        return img

    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb_arr = np.array(rgba.convert("RGB"), dtype=np.uint8)
    h, w = rgb_arr.shape[:2]
    flat = rgb_arr.reshape(-1, 3).copy()

    dist_sq = pixel_distances_to_palette(rgb_arr)
    palette = np.array(load_standard_palette(), dtype=np.uint8)

    for zone_start, tolerance in ((SECONDARY_REMAP_START, trim_tolerance), (TERTIARY_REMAP_START, tertiary_tolerance)):
        if tolerance == 0:
            continue
        caught, shade_idx, natural_win, best_other_idx = classify_remap_zone(dist_sq, zone_start, tolerance)
        pulled_in = caught & ~natural_win
        pushed_out = natural_win & ~caught
        flat[pulled_in] = palette[zone_start + shade_idx[pulled_in]]
        flat[pushed_out] = palette[best_other_idx[pushed_out]]

    result = Image.fromarray(flat.reshape(h, w, 3), mode="RGB").convert("RGBA")
    result.putalpha(alpha)
    return result


def dither_frame_by_algorithm(
    img: Image.Image,
    algorithm: str,
    *,
    strength: int = 32,
    trim_tolerance: int = 0,
    tertiary_tolerance: int = 0,
) -> Image.Image:
    """Dispatch to the dithering function named by `algorithm`
    ("floyd_steinberg" | "bayer" | "atkinson" | "none").

    `trim_tolerance`/`tertiary_tolerance` (see classify_remap_zone) widen or
    narrow which pixels actually land in the secondary/tertiary remap zones
    for the three real dithering algorithms - this is the one place that
    decides classification for the shipped sprite (see this module's
    docstring). Not applied for "none": the artist's explicit choice to skip
    quantisation entirely should mean no palette-snapping of any kind."""
    if algorithm == "none":
        return img.convert("RGBA")

    biased = _apply_catch_tolerance_bias(img, trim_tolerance, tertiary_tolerance)
    if algorithm == "floyd_steinberg":
        return dither_frame(biased)
    if algorithm == "bayer":
        return dither_frame_bayer(biased, strength=strength)
    if algorithm == "atkinson":
        return dither_frame_atkinson(biased, strength=strength)
    raise ValueError(f"Unknown dither algorithm: {algorithm!r}")
