"""Approximates OpenRCT2's in-game colour remap for Blender-rendered sprite
frames, using the data extracted by tools/extract_palette.py.

Mirrors GfxDrawSpriteGetPalette's secondary/tertiary remap (see
feedback_sprite_packaging.md): a frame's pixels are matched to the nearest
StandardPalette entry (as `-m closest` does), then any pixel landing in the
secondary (202-213) or tertiary (46-57) remap ranges is replaced according to
the chosen Trim/Tertiary Colour's 12-shade ramp.

Field naming matches the engine's actual VehicleColour terminology (verified
against VehiclePaint.cpp/ImageId.hpp/PaletteIndex.h): Trim drives the
secondary zone (202-213, reference shade "bright_pink"), Tertiary drives the
tertiary zone (46-57, reference shade "yellow"). There's no Body/primary
parameter for the same reason `primary_colour` below is noted as
build-irrelevant: openrct2-cli's `-m closest` excludes the primary zone
(243-254) from its nearest-match targets entirely (ImageImporter.cpp's
IsChangablePixel), so no PNG-authored pixel can ever land there.

IMPORTANT: this function is preview-only. The real sprite-build pipeline
(build/layers.py's render_layer_frame, used by build_composite_frames) must
NOT call this - baking a specific colour into the shipped sprite would erase
the secondary/tertiary zone pixels the engine needs to recolour the ride live
at render time. Only call this from UI preview code or when generating
object.json's properties.carColours default-scheme list.
"""

from __future__ import annotations

import json
from pathlib import Path
from functools import lru_cache

import numpy as np
from PIL import Image

_DATA_DIR = Path(__file__).resolve().parent

SECONDARY_REMAP_START = 202
TERTIARY_REMAP_START = 46
PRIMARY_REMAP_START = 243
REMAP_LENGTH = 12

# sRGB <-> linear-light transfer (IEC 61966-2-1). Colour distance and error
# diffusion are physically meaningful only in linear light: averaging or
# nearest-matching in gamma-encoded sRGB skews toward dark (the classic
# "dithering comes out too dark" error). These mirror libIsoRender's
# srgb2linear/linear2srgb (see reference-community-tools) but vectorised over
# numpy arrays. Both operate on values in [0, 1]; callers normalise 0-255
# channels first. This is groundwork for Phase 2 of the pipeline overhaul - the
# helpers exist and are tested here, but no existing caller switches to linear
# yet (pixel_distances_to_palette stays sRGB by default for exact back-compat).
_SRGB_LINEAR_THRESHOLD = 0.04045
_LINEAR_SRGB_THRESHOLD = 0.0031308
_SRGB_GAMMA = 2.4


def srgb_to_linear(srgb: np.ndarray) -> np.ndarray:
    """Convert sRGB-encoded values in [0, 1] to linear-light [0, 1]."""
    srgb = np.clip(np.asarray(srgb, dtype=np.float32), 0.0, 1.0)
    return np.where(
        srgb <= _SRGB_LINEAR_THRESHOLD,
        srgb / 12.92,
        np.power((srgb + 0.055) / 1.055, _SRGB_GAMMA),
    ).astype(np.float32)


def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    """Inverse of srgb_to_linear: linear-light [0, 1] back to sRGB [0, 1]."""
    linear = np.clip(np.asarray(linear, dtype=np.float32), 0.0, 1.0)
    return np.where(
        linear <= _LINEAR_SRGB_THRESHOLD,
        linear * 12.92,
        1.055 * np.power(linear, 1.0 / _SRGB_GAMMA) - 0.055,
    ).astype(np.float32)


@lru_cache(maxsize=1)
def load_standard_palette() -> list[list[int]]:
    return json.loads((_DATA_DIR / "standard_palette.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_colour_ramps() -> dict[str, list[int]]:
    return json.loads((_DATA_DIR / "colour_ramps.json").read_text(encoding="utf-8"))


def colour_swatch_rgb(colour: str) -> tuple[int, int, int]:
    """A representative RGB swatch for `colour`, taken from the middle of its
    12-shade ramp - useful for UI colour pickers."""
    ramp = load_colour_ramps()[colour]
    palette = load_standard_palette()
    index = ramp[len(ramp) // 2]
    r, g, b = palette[index]
    return (r, g, b)


def pixel_distances_to_palette(rgb_arr: np.ndarray, *, linear: bool = False) -> np.ndarray:
    """Squared RGB Euclidean distance from every pixel in `rgb_arr` (shape
    (H, W, 3) or (N, 3)) to every one of the 256 StandardPalette entries.
    Returns shape (N, 256). Computed via the sum-of-squares expansion
    (|a-b|^2 = |a|^2 - 2a.b + |b|^2) so the result is a matmul rather than a
    materialized (N, 256, 3) difference array - this matters because N is
    every pixel in a full sprite frame.

    `linear=False` (default) measures distance in raw sRGB 0-255 space, the
    original behaviour every current caller relies on. `linear=True` converts
    both pixels and palette to linear light first (see srgb_to_linear), so
    nearest-match distance is physically correct - the gamma-aware path Phase 2
    of the pipeline overhaul moves the dithering/classification onto. The two
    paths return values on different scales (0-255^2 vs 0-1^2); only compare or
    threshold distances computed the same way.

    float32 throughout: sRGB distance-squared for 0-255 channels never exceeds
    3*255^2 = 195075, comfortably inside float32's exactly-representable integer
    range (2^24); the linear path's [0,1] values are smaller still. So this
    loses no precision while roughly halving the matmul's cost versus float64 -
    this runs on every animation-preview tick once a colour scheme or catch
    tolerance is in use (see classify_remap_zone), so that cost matters."""
    flat = rgb_arr.reshape(-1, 3).astype(np.float32)
    palette = np.array(load_standard_palette(), dtype=np.float32)
    if linear:
        flat = srgb_to_linear(flat / 255.0)
        palette = srgb_to_linear(palette / 255.0)
    sq_sum_px = np.sum(flat**2, axis=1)
    sq_sum_pal = np.sum(palette**2, axis=1)
    cross = flat @ palette.T
    dist_sq = sq_sum_px[:, None] - 2 * cross + sq_sum_pal[None, :]
    return np.clip(dist_sq, 0, None)  # guard tiny negative float error


def classify_remap_zone(
    dist_sq: np.ndarray,
    zone_start: int,
    tolerance: int,
    *,
    global_min_dist_sq: np.ndarray | None = None,
    global_min_idx: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Classify every pixel (whose distances to all 256 palette entries are
    in `dist_sq`, shape (N, 256)) as caught by the REMAP_LENGTH-entry remap
    zone starting at `zone_start`, or not - given a catch-tolerance in plain
    (non-squared) RGB-distance units.

    tolerance == 0 reproduces the original fixed behaviour exactly: a pixel
    is caught only if the zone's own best-matching shade is *also* its
    single nearest match among all 256 entries (today's `-m closest`-style
    nearest-colour rule). tolerance > 0 widens the net: a pixel is also
    caught if the zone's best shade is within `tolerance` RGB-distance
    units of beating its actual best alternative, even though it doesn't
    win outright - this is what "catches" borderline EEVEE-lit pixels that
    fall just short. tolerance < 0 narrows it: a pixel that *would* win
    outright is excluded unless its margin of victory over the best
    alternative is at least `abs(tolerance)` - filtering out borderline wins.

    `global_min_dist_sq`/`global_min_idx` (each shape (N,), from
    `dist_sq.min(axis=1)`/`dist_sq.argmin(axis=1)`) let a caller classifying
    both zones from the same `dist_sq` compute the global nearest-match
    once and pass it to both calls, instead of every call re-deriving it -
    see remap_preview/_apply_catch_tolerance_bias. For most pixels (whose
    global best match isn't even in this zone), that's *also* this zone's
    best alternative, with no further search needed - only pixels whose
    single nearest match across all 256 entries falls inside this specific
    zone (a small minority, in practice) need the more expensive
    zone-excluded search.

    Returns (caught, shade_idx, natural_win, best_other_idx), each shape
    (N,). `shade_idx` (0..REMAP_LENGTH-1) is the nearest shade within the
    zone, valid regardless of `caught`. `natural_win` is the pixel's
    tolerance=0 classification - callers that need to avoid disturbing
    pixels that already resolve correctly on their own (build/dither.py)
    use `caught & ~natural_win` (pulled in by widening) and
    `natural_win & ~caught` (excluded by narrowing) to find exactly the
    pixels a nonzero tolerance actually changes. `best_other_idx` (0..255)
    is the nearest *non-zone* palette entry, the snap target for pixels
    excluded by narrowing.
    """
    zone_end = zone_start + REMAP_LENGTH
    zone_dists = dist_sq[:, zone_start:zone_end]
    shade_idx = np.argmin(zone_dists, axis=1)
    best_zone_dist = np.sqrt(np.min(zone_dists, axis=1))

    if global_min_dist_sq is None or global_min_idx is None:
        global_min_idx = np.argmin(dist_sq, axis=1)
        global_min_dist_sq = np.min(dist_sq, axis=1)

    best_other_idx = global_min_idx.copy()
    best_other_dist_sq = global_min_dist_sq.copy()

    in_zone = (global_min_idx >= zone_start) & (global_min_idx < zone_end)
    if np.any(in_zone):
        # Only the (typically small) subset whose single global-nearest
        # match falls inside this zone needs a proper zone-excluded
        # re-search - copying just that subset, not the full (N, 256) array.
        masked = dist_sq[in_zone].copy()
        masked[:, zone_start:zone_end] = np.inf
        best_other_idx[in_zone] = np.argmin(masked, axis=1)
        best_other_dist_sq[in_zone] = np.min(masked, axis=1)

    best_other_dist = np.sqrt(best_other_dist_sq)
    natural_win = best_zone_dist <= best_other_dist

    if tolerance >= 0:
        caught = natural_win | (best_zone_dist <= best_other_dist + tolerance)
    else:
        margin = best_other_dist - best_zone_dist
        caught = natural_win & (margin >= -tolerance)

    return caught, shade_idx, natural_win, best_other_idx


def remap_preview(
    image: Image.Image,
    trim_colour: str,
    tertiary_colour: str,
    body_colour: str | None = None,
    *,
    trim_tolerance: int = 0,
    tertiary_tolerance: int = 0,
) -> Image.Image:
    """Return an RGBA copy of `image` with its secondary/tertiary remap-range
    pixels recoloured according to `trim_colour`/`tertiary_colour`. Every
    other pixel keeps its original, un-quantized RGB value - only the
    matched remap-zone pixels are touched.

    This matters for dithering: an earlier version of this function ran a
    nearest-match `quantize()` over the *entire* image first, then remapped
    via a palette LUT. That hard-snapped every pixel to an exact palette
    entry with zero residual error, so a dithering pass run afterward
    (build/dither.py's dither_frame_by_algorithm) had nothing left to
    diffuse - "Preview dithering" silently became a no-op for any frame
    that had gone through this function. Only replacing the specific
    remap-zone pixels (which are meant to be flat reference shades anyway)
    leaves the rest of the smooth EEVEE-rendered surface untouched, so a
    later dithering pass still has real quantisation error to work with.

    `trim_tolerance`/`tertiary_tolerance` (see classify_remap_zone) widen or
    narrow which pixels count as "in" each zone - normally sourced from
    RideProject.trim_catch_tolerance/tertiary_catch_tolerance, so this
    preview matches what build/dither.py will actually catch for the real
    build (see render_layer_frame's docstring for why dithering, not this
    function, is what determines the *shipped* sprite's classification).

    `body_colour`, if given, also remaps the primary range (243-254) -
    included for completeness even though no pixel from a `-m closest`
    Blender render can land there in practice. Never tolerance-adjusted,
    since it's already moot in practice.
    """
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")

    rgb_arr = np.array(rgba.convert("RGB"), dtype=np.uint8)
    h, w = rgb_arr.shape[:2]
    dist_sq = pixel_distances_to_palette(rgb_arr)
    global_min_idx = np.argmin(dist_sq, axis=1)
    global_min_dist_sq = np.min(dist_sq, axis=1)

    secondary_caught, secondary_idx, _, _ = classify_remap_zone(
        dist_sq, SECONDARY_REMAP_START, trim_tolerance, global_min_dist_sq=global_min_dist_sq, global_min_idx=global_min_idx
    )
    tertiary_caught, tertiary_idx, _, _ = classify_remap_zone(
        dist_sq, TERTIARY_REMAP_START, tertiary_tolerance, global_min_dist_sq=global_min_dist_sq, global_min_idx=global_min_idx
    )

    # Resolve the (in practice vanishingly rare) case where both zones claim
    # the same pixel - whichever zone it's actually closer to wins.
    both = secondary_caught & tertiary_caught
    if np.any(both):
        sec_dist = np.min(dist_sq[:, SECONDARY_REMAP_START : SECONDARY_REMAP_START + REMAP_LENGTH], axis=1)
        ter_dist = np.min(dist_sq[:, TERTIARY_REMAP_START : TERTIARY_REMAP_START + REMAP_LENGTH], axis=1)
        secondary_caught = secondary_caught & ~(both & (ter_dist < sec_dist))
        tertiary_caught = tertiary_caught & ~(both & (sec_dist <= ter_dist))

    palette = load_standard_palette()
    ramps = load_colour_ramps()

    result_flat = rgb_arr.reshape(-1, 3).copy()
    trim_ramp = np.array([palette[i] for i in ramps[trim_colour]])
    tertiary_ramp = np.array([palette[i] for i in ramps[tertiary_colour]])
    result_flat[secondary_caught] = trim_ramp[secondary_idx[secondary_caught]]
    result_flat[tertiary_caught] = tertiary_ramp[tertiary_idx[tertiary_caught]]

    if body_colour is not None:
        primary_caught, primary_idx, _, _ = classify_remap_zone(
            dist_sq, PRIMARY_REMAP_START, 0, global_min_dist_sq=global_min_dist_sq, global_min_idx=global_min_idx
        )
        primary_ramp = np.array([palette[i] for i in ramps[body_colour]])
        result_flat[primary_caught] = primary_ramp[primary_idx[primary_caught]]

    result = Image.fromarray(result_flat.reshape(h, w, 3), mode="RGB").convert("RGBA")
    result.putalpha(alpha)
    return result


def recolour_dithered_zones(image: Image.Image, trim_colour: str, tertiary_colour: str) -> Image.Image:
    """Return an RGBA copy of `image` with its secondary/tertiary remap-zone
    pixels recoloured to `trim_colour`/`tertiary_colour`'s ramps, via a
    direct index lookup rather than remap_preview's distance-based
    classification.

    For use only on an image that has already been through
    build.dither.dither_frame_by_algorithm's zone-constrained quantisation,
    where every zone pixel is *guaranteed* to sit exactly on one of that
    zone's 12 reference entries - so there's nothing to classify, just an
    index to read and substitute. This is what build.layers.
    render_layer_frame_preview uses for its dither=True path: dither the raw
    reference shades first (exactly as the real build does), then recolour
    the result, mirroring what the engine itself does at runtime (recolour
    an already-dithered shipped sprite by index). Recolouring *before*
    dithering - remap_preview's approach, used for the dither=False fast
    preview where there's no quantised index yet to look up - would
    collapse the zone's natural EEVEE gradient into flat per-shade bands
    before dithering had a chance to diffuse error across it, losing detail
    a real dithered build would have kept; that mismatch was visible as the
    preview's dithering looking measurably less detailed/textured than the
    shipped sprite's.
    """
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")

    rgb_arr = np.array(rgba.convert("RGB"), dtype=np.uint8)
    h, w = rgb_arr.shape[:2]
    flat = rgb_arr.reshape(-1, 3)

    dist_sq = pixel_distances_to_palette(rgb_arr)
    idx = np.argmin(dist_sq, axis=1)

    palette = load_standard_palette()
    ramps = load_colour_ramps()
    trim_ramp = np.array([palette[i] for i in ramps[trim_colour]], dtype=np.uint8)
    tertiary_ramp = np.array([palette[i] for i in ramps[tertiary_colour]], dtype=np.uint8)

    result_flat = flat.copy()
    secondary_hit = (idx >= SECONDARY_REMAP_START) & (idx < SECONDARY_REMAP_START + REMAP_LENGTH)
    tertiary_hit = (idx >= TERTIARY_REMAP_START) & (idx < TERTIARY_REMAP_START + REMAP_LENGTH)
    result_flat[secondary_hit] = trim_ramp[idx[secondary_hit] - SECONDARY_REMAP_START]
    result_flat[tertiary_hit] = tertiary_ramp[idx[tertiary_hit] - TERTIARY_REMAP_START]

    result = Image.fromarray(result_flat.reshape(h, w, 3), mode="RGB").convert("RGBA")
    result.putalpha(alpha)
    return result
