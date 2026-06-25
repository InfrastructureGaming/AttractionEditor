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

Every algorithm, including Floyd-Steinberg, honours Layer.dither_strength
(0-32, default 32 = full dithering, 0 = plain nearest-match with no
dithering at all). dither_frame's strength<32 path blends PIL's plain and
fully-dithered results (both already exact palette colours) in continuous
RGB space, then snaps the blend back to its nearest palette entry - see
dither_frame's own docstring for the two slower/less correct approaches
this replaced (a manual per-pixel diffusion loop, and blending the source
toward its own plain value before a single dithering pass).

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

dither_frame_by_algorithm's quantisation is also zone-constrained: a pixel
classified into the secondary or tertiary remap zone is only ever quantised
against that zone's own 12 entries, and a pixel classified as neither is
quantised against everything except both zones - never the unconstrained
244-entry candidate set on its own. Without this, error-diffusion dithering
can drift a zone pixel's accumulated error far enough that the globally
nearest palette entry is a similar-looking but non-remappable colour just
outside the zone; since the engine only recolours pixels whose index falls
inside a watched zone range, an escaped pixel ships as a fixed, wrong
colour regardless of which scheme the player picks (see
dither_frame_by_algorithm's own docstring for the full mechanism - this was
a real, confirmed bug, not a hypothetical).
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

# A colour that no EEVEE-rendered pixel will ever be near, used to fill
# excluded palette slots so quantisation never assigns pixels there.
_SENTINEL_RGB = (0, 255, 0)  # pure green; absent from both remap zones and normal geometry


@lru_cache(maxsize=1)
def all_non_primary_indices() -> frozenset[int]:
    """Every palette index except the 12 primary-remap slots (243-254) -
    the default candidate set for ordinary (zone-unaware) quantisation."""
    primary = range(PRIMARY_REMAP_START, PRIMARY_REMAP_START + REMAP_LENGTH)
    return frozenset(range(256)) - frozenset(primary)


@lru_cache(maxsize=1)
def secondary_zone_indices() -> frozenset[int]:
    return frozenset(range(SECONDARY_REMAP_START, SECONDARY_REMAP_START + REMAP_LENGTH))


@lru_cache(maxsize=1)
def tertiary_zone_indices() -> frozenset[int]:
    return frozenset(range(TERTIARY_REMAP_START, TERTIARY_REMAP_START + REMAP_LENGTH))


@lru_cache(maxsize=1)
def structure_indices() -> frozenset[int]:
    """Every valid index except both remap zones - the candidate set for
    pixels that don't belong to either zone, so ordinary structure can never
    be diffused into a colour the engine would mistake for recolourable
    trim/tertiary at runtime (the mirror-image of the zone-escape bug)."""
    return all_non_primary_indices() - secondary_zone_indices() - tertiary_zone_indices()


def _resolve_allowed(allowed_indices: frozenset[int] | None) -> frozenset[int]:
    return allowed_indices if allowed_indices is not None else all_non_primary_indices()


@lru_cache(maxsize=8)
def _build_quantise_palette(allowed_indices: frozenset[int]) -> Image.Image:
    """PIL P-mode image for Image.quantize(), with every slot not in
    `allowed_indices` replaced by a sentinel colour so quantisation can never
    assign a pixel to an excluded index - whether that's just the primary
    slots (today's default, ordinary quantisation) or also one or both
    remap zones (zone-constrained quantisation, see
    dither_frame_by_algorithm)."""
    entries = [list(rgb) for rgb in load_standard_palette()]
    for i in range(256):
        if i not in allowed_indices:
            entries[i] = list(_SENTINEL_RGB)
    pal_img = Image.new("P", (1, 1))
    pal_img.putpalette([c for rgb in entries for c in rgb])
    return pal_img


@lru_cache(maxsize=1)
def _real_palette_flat() -> list[int]:
    """Flat [R,G,B, R,G,B, ...] list for the real StandardPalette."""
    return [c for rgb in load_standard_palette() for c in rgb]


@lru_cache(maxsize=None)
def _nearest_allowed_index(sentinel_idx: int, allowed_indices: frozenset[int]) -> int:
    """Nearest `allowed_indices` palette index to `sentinel_idx`, by RGB
    distance. Used as a safety net; in practice quantisation should never
    land on a sentinel slot."""
    palette = load_standard_palette()
    r, g, b = palette[sentinel_idx]
    best_idx, best_dist = next(iter(allowed_indices)), float("inf")
    for i in allowed_indices:
        pr, pg, pb = palette[i]
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx


def _fix_sentinel_pixels(indexed: Image.Image, allowed_indices: frozenset[int]) -> None:
    """In-place: replace any pixel at an excluded index with the nearest
    allowed palette index. This is a defensive pass; well-rendered frames
    should produce zero sentinel hits."""
    px = indexed.load()
    w, h = indexed.size
    for y in range(h):
        for x in range(w):
            idx = px[x, y]  # type: ignore[index]
            if idx not in allowed_indices:
                px[x, y] = _nearest_allowed_index(idx, allowed_indices)  # type: ignore[index]


def _quantise_to_real_rgb(
    rgb_img: Image.Image, *, dither: Image.Dither, allowed_indices: frozenset[int] | None = None
) -> Image.Image:
    """Quantise `rgb_img` (mode "RGB") into the sentinel-excluded palette
    with the given PIL dither mode, then expand back to exact real-palette
    RGB values (see dither_frame's docstring for why: the sentinel palette
    only exists to keep excluded slots out of the nearest-neighbour race,
    real output pixels must carry the actual StandardPalette colour).

    `allowed_indices` defaults to all_non_primary_indices() (today's
    ordinary behaviour); dither_frame_by_algorithm passes a zone-restricted
    set instead, for zone-constrained quantisation."""
    allowed = _resolve_allowed(allowed_indices)
    indexed = rgb_img.quantize(palette=_build_quantise_palette(allowed), dither=dither)
    _fix_sentinel_pixels(indexed, allowed)
    real_pal = indexed.copy()
    real_pal.putpalette(_real_palette_flat())
    return real_pal.convert("RGB")


def dither_frame(img: Image.Image, *, strength: int = 32, allowed_indices: frozenset[int] | None = None) -> Image.Image:
    """Return an RGBA copy of `img` with Floyd-Steinberg dithering into the
    RCT2 StandardPalette, preserving the alpha channel.

    Primary-remap indices (243-254) are excluded from the quantisation target,
    so the result is safe to pass to openrct2-cli -m closest.  Every output
    pixel is the exact RGB value of its assigned StandardPalette entry.

    `allowed_indices`, if given, further restricts the candidate set (e.g.
    to just one remap zone's 12 entries) - see dither_frame_by_algorithm for
    why and how this is combined per pixel.

    `strength` (0-32, default 32 = full classic Floyd-Steinberg) lets a layer
    author dial the effect back, the same way dither_frame_bayer/_atkinson's
    `strength` does. At strength=32, PIL's fast built-in F-S quantisation is
    used directly on the source. At strength=0, it's the plain (undithered)
    nearest-match result. In between: compute both the plain and the fully
    F-S-dithered result (both already exact palette colours), linearly blend
    them in continuous RGB space by `strength/32`, then snap that blend back
    to its single nearest palette entry (no further dithering - this last
    step is just resolving the in-between blend, not diffusing new error).
    All PIL/numpy array ops, no manual per-pixel loop, so cost is
    independent of strength.

    Two earlier, less correct attempts at this:
    - A manual per-pixel loop scaling the diffused error fraction directly
      (mirroring dither_frame_atkinson's diffuse_fraction) was correct but
      ~1s/frame on a real layer - a "build takes 10x longer" regression,
      since this is the default algorithm.
    - Blending the *source* toward its own plain-quantised value before a
      single F-S pass (instead of blending the two already-dithered
      candidates after) was fast, but plain quantisation alone collapses a
      typical EEVEE render to a handful of flat colour bands; blending only
      a small fraction of the original signal back in wasn't enough to
      break that banding before F-S ran, so the result still looked
      artificially regular - just shaped by the banding instead of by a
      spatial mask.

    Blending two *already on-palette* candidates avoids both: each
    candidate already has F-S's natural per-pixel variation (no banding to
    introduce regularity), and which one wins after the final snap is a
    function of how close that pixel's blend happens to land to each
    candidate - not a fixed grid or a flattened intermediate.
    """
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb = rgba.convert("RGB")

    strength = min(32, max(0, strength))
    if strength >= 32:
        rgb_result = _quantise_to_real_rgb(rgb, dither=Image.Dither.FLOYDSTEINBERG, allowed_indices=allowed_indices)
    else:
        plain_rgb = _quantise_to_real_rgb(rgb, dither=Image.Dither.NONE, allowed_indices=allowed_indices)
        if strength <= 0:
            rgb_result = plain_rgb
        else:
            full_rgb = _quantise_to_real_rgb(rgb, dither=Image.Dither.FLOYDSTEINBERG, allowed_indices=allowed_indices)
            plain_arr = np.asarray(plain_rgb, dtype=np.float64)
            full_arr = np.asarray(full_rgb, dtype=np.float64)
            fraction = strength / 32.0
            blended_arr = plain_arr + (full_arr - plain_arr) * fraction
            blended_img = Image.fromarray(np.clip(blended_arr, 0, 255).astype(np.uint8), mode="RGB")
            rgb_result = _quantise_to_real_rgb(blended_img, dither=Image.Dither.NONE, allowed_indices=allowed_indices)

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


def dither_frame_bayer(
    img: Image.Image, *, strength: int = 32, allowed_indices: frozenset[int] | None = None
) -> Image.Image:
    """Return an RGBA copy of `img` ordered-dithered into the RCT2
    StandardPalette using a tiled 8x8 Bayer threshold matrix, preserving the
    alpha channel.

    Unlike dither_frame (Floyd-Steinberg), the perturbation applied to each
    pixel depends only on (x, y) mod 8 and that pixel's own colour - never on
    neighbouring pixels - so the same spatial noise pattern repeats on every
    frame of an animation instead of drifting ("boiling") frame to frame.

    `allowed_indices`, if given, restricts the quantisation target the same
    way dither_frame's does - see dither_frame_by_algorithm.

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

    allowed = _resolve_allowed(allowed_indices)
    indexed = perturbed_img.quantize(palette=_build_quantise_palette(allowed), dither=Image.Dither.NONE)
    _fix_sentinel_pixels(indexed, allowed)

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


@lru_cache(maxsize=8)
def _atkinson_colour_cache(allowed_indices: frozenset[int]) -> dict[tuple[int, int, int], tuple[float, float, float]]:
    """A nearest-palette-colour memo, one dict per distinct allowed_indices
    set, returned by reference and reused across every dither_frame_atkinson
    call for the lifetime of the process (lru_cache hands back the same dict
    object every time, so callers mutating it in place is the intended use).

    The error-diffusion loop below has a genuine serial dependency (each
    pixel's diffused error feeds the next), so it can't be vectorised across
    the whole image the way dither_frame's Floyd-Steinberg path was - but the
    per-pixel nearest-palette search inside that loop has no such dependency
    on *which* colour it's searching for, only on the (rounded) RGB value.
    A rendered frame's distinct colours number in the hundreds to low
    thousands, not one per pixel - and an animated layer's hundreds of
    frames overwhelmingly reuse the same handful of shaded tones - so memoing
    the search by rounded RGB turns the vast majority of pixels into an O(1)
    dict lookup instead of an O(len(allowed_indices)) numpy distance search,
    with the full search only ever run once per distinct colour actually
    encountered. Independent of `strength` (nearest-colour search doesn't
    depend on it), so the same cache benefits every strength used with a
    given allowed_indices set."""
    return {}


def dither_frame_atkinson(
    img: Image.Image, *, strength: int = 32, allowed_indices: frozenset[int] | None = None
) -> Image.Image:
    """Return an RGBA copy of `img` Atkinson-dithered into the RCT2
    StandardPalette, preserving the alpha channel.

    Like dither_frame (Floyd-Steinberg), this is error-diffusion - each
    pixel's quantisation error depends on its neighbourhood, so dithering an
    animated frame sequence with this algorithm will jitter the same way
    Floyd-Steinberg does. Provided as a per-layer author choice, not
    recommended for animated layers.

    `allowed_indices`, if given, restricts the quantisation target the same
    way dither_frame's does - see dither_frame_by_algorithm.

    `strength` scales the fraction of error diffused (32 ~= classic Atkinson
    at full RGB-unit error; 0 degenerates to plain nearest-colour matching).
    """
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")

    palette = load_standard_palette()
    valid_indices = sorted(_resolve_allowed(allowed_indices))
    valid_palette = np.array([palette[i] for i in valid_indices], dtype=np.float64)
    cache = _atkinson_colour_cache(frozenset(valid_indices))

    arr_np = np.asarray(rgba.convert("RGB"), dtype=np.float64)
    h, w = arr_np.shape[:2]
    diffuse_fraction = min(1.0, max(0.0, strength / 32.0)) / 8.0

    # Plain Python nested lists for the hot loop: numpy scalar indexing
    # (arr[y, x]) carries per-element dispatch/boxing overhead that adds up
    # over tens of thousands of pixels - a raw Python list/float is cheaper
    # to read and mutate here even though the loop itself can't be
    # vectorised (each pixel's diffused error feeds pixels not yet visited).
    arr = arr_np.tolist()

    for y in range(h):
        row = arr[y]
        for x in range(w):
            r, g, b = row[x]
            key = (
                0 if r <= 0.0 else (255 if r >= 255.0 else int(r + 0.5)),
                0 if g <= 0.0 else (255 if g >= 255.0 else int(g + 0.5)),
                0 if b <= 0.0 else (255 if b >= 255.0 else int(b + 0.5)),
            )
            nearest = cache.get(key)
            if nearest is None:
                dists = np.sum((valid_palette - key) ** 2, axis=1)
                nearest = tuple(float(c) for c in valid_palette[int(np.argmin(dists))])
                cache[key] = nearest
            nr, ng, nb = nearest
            row[x] = [nr, ng, nb]
            er = (r - nr) * diffuse_fraction
            eg = (g - ng) * diffuse_fraction
            eb = (b - nb) * diffuse_fraction
            for dx, dy in _ATKINSON_OFFSETS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    neighbour = arr[ny][nx]
                    neighbour[0] += er
                    neighbour[1] += eg
                    neighbour[2] += eb

    result_rgb = Image.fromarray(np.clip(np.array(arr, dtype=np.float64), 0, 255).astype(np.uint8), mode="RGB")
    result = result_rgb.convert("RGBA")
    result.putalpha(alpha)
    return result


def _apply_catch_tolerance_bias(
    img: Image.Image, trim_tolerance: int, tertiary_tolerance: int
) -> tuple[Image.Image, np.ndarray, np.ndarray]:
    """Pre-snap borderline pixels toward (or away from) the secondary/
    tertiary remap zones before quantising, per RideProject's
    trim_catch_tolerance/tertiary_catch_tolerance - and always return each
    pixel's final zone classification too (shape (H, W) bool each), needed
    by dither_frame_by_algorithm's zone-constrained quantisation regardless
    of whether a tolerance is in use: tolerance=0 reproduces the original
    "single nearest match decides" rule exactly (see classify_remap_zone),
    so it's already the right classification to constrain by, not just a
    bias-pixel special case.

    The returned image is unchanged from `img` whenever both tolerances are
    0 (today's original, only behaviour) - this is still a pure no-op for
    the *image*. For a nonzero tolerance, only the specific pixels whose
    zone classification actually *changes* (classify_remap_zone's `caught &
    ~natural_win`, pulled in by widening, or `natural_win & ~caught`,
    excluded by narrowing) have their RGB touched; pixels that already
    resolve correctly on their own keep their exact original RGB, so the
    residual quantisation error they naturally contribute to error-diffusion
    dithering (Floyd-Steinberg/Atkinson) is undisturbed.
    """
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb_arr = np.array(rgba.convert("RGB"), dtype=np.uint8)
    h, w = rgb_arr.shape[:2]
    flat = rgb_arr.reshape(-1, 3).copy()

    dist_sq = pixel_distances_to_palette(rgb_arr)
    palette = np.array(load_standard_palette(), dtype=np.uint8)
    global_min_idx = np.argmin(dist_sq, axis=1)
    global_min_dist_sq = np.min(dist_sq, axis=1)

    zone_masks: dict[int, np.ndarray] = {}
    for zone_start, tolerance in ((SECONDARY_REMAP_START, trim_tolerance), (TERTIARY_REMAP_START, tertiary_tolerance)):
        caught, shade_idx, natural_win, best_other_idx = classify_remap_zone(
            dist_sq, zone_start, tolerance, global_min_dist_sq=global_min_dist_sq, global_min_idx=global_min_idx
        )
        zone_masks[zone_start] = caught
        if tolerance != 0:
            pulled_in = caught & ~natural_win
            pushed_out = natural_win & ~caught
            flat[pulled_in] = palette[zone_start + shade_idx[pulled_in]]
            flat[pushed_out] = palette[best_other_idx[pushed_out]]

    secondary_mask = zone_masks[SECONDARY_REMAP_START].reshape(h, w)
    tertiary_mask = zone_masks[TERTIARY_REMAP_START].reshape(h, w)

    # Resolve the (in practice vanishingly rare) case where both zones claim
    # the same pixel - same tie-break remap_preview uses: whichever zone is
    # actually closer wins.
    both = secondary_mask & tertiary_mask
    if np.any(both):
        sec_dist = np.min(dist_sq[:, SECONDARY_REMAP_START : SECONDARY_REMAP_START + REMAP_LENGTH], axis=1).reshape(h, w)
        ter_dist = np.min(dist_sq[:, TERTIARY_REMAP_START : TERTIARY_REMAP_START + REMAP_LENGTH], axis=1).reshape(h, w)
        secondary_mask = secondary_mask & ~(both & (ter_dist < sec_dist))
        tertiary_mask = tertiary_mask & ~(both & (sec_dist <= ter_dist))

    if trim_tolerance == 0 and tertiary_tolerance == 0:
        result = img.convert("RGBA")
    else:
        result = Image.fromarray(flat.reshape(h, w, 3), mode="RGB").convert("RGBA")
        result.putalpha(alpha)

    return result, secondary_mask, tertiary_mask


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
    quantisation entirely should mean no palette-snapping of any kind.

    Zone-constrained quantisation: a pixel classified into the secondary or
    tertiary zone is quantised against *only that zone's* 12 entries, never
    the full palette - and a pixel classified as neither is quantised
    against everything except both zones. Without this, ordinary
    error-diffusion dithering (Floyd-Steinberg in particular, since its
    accumulated error is unbounded along a scanline, unlike Bayer's fixed
    perturbation) can push a pixel that started as an exact zone reference
    shade to drift, under diffused error from its neighbours, to whichever
    palette entry is globally nearest - which is sometimes a similar-looking
    but non-remappable colour just outside the zone. The engine only
    recolours pixels whose *index* falls inside a watched zone range at
    render time, so an escaped pixel never gets recoloured: it ships as a
    fixed, wrong-looking colour regardless of which colour scheme the
    player picks. This showed up as light-red speckling concentrated in
    lighter trim/tertiary shades (closer in RGB space to the nearest
    non-zone "escape route") and absent everywhere else - invisible in this
    tool's own preview (which shows the raw, un-recoloured reference
    shades, so an escaped pixel still looks like a plausible neighbour) but
    glaring in-game once the *zone* pixels around it get recoloured to a
    totally different hue.

    Implementation: each algorithm runs up to three times against
    progressively restricted candidate sets (structure_indices() by
    default, plus secondary_zone_indices()/tertiary_zone_indices() only if
    any pixel actually classifies into that zone), and the results are
    combined per pixel by classification. A layer with no remap-zone
    content at all (most background/structural layers) pays for exactly
    one pass, same as before this existed.
    """
    if algorithm == "none":
        return img.convert("RGBA")

    dither_fn = {"floyd_steinberg": dither_frame, "bayer": dither_frame_bayer, "atkinson": dither_frame_atkinson}.get(
        algorithm
    )
    if dither_fn is None:
        raise ValueError(f"Unknown dither algorithm: {algorithm!r}")

    biased, secondary_mask, tertiary_mask = _apply_catch_tolerance_bias(img, trim_tolerance, tertiary_tolerance)

    has_secondary = bool(np.any(secondary_mask))
    has_tertiary = bool(np.any(tertiary_mask))
    if not has_secondary and not has_tertiary:
        return dither_fn(biased, strength=strength)

    structure_result = dither_fn(biased, strength=strength, allowed_indices=structure_indices())
    result_arr = np.asarray(structure_result.convert("RGBA")).copy()

    if has_secondary:
        secondary_result = dither_fn(biased, strength=strength, allowed_indices=secondary_zone_indices())
        result_arr[secondary_mask] = np.asarray(secondary_result.convert("RGBA"))[secondary_mask]
    if has_tertiary:
        tertiary_result = dither_fn(biased, strength=strength, allowed_indices=tertiary_zone_indices())
        result_arr[tertiary_mask] = np.asarray(tertiary_result.convert("RGBA"))[tertiary_mask]

    return Image.fromarray(result_arr, mode="RGBA")


def snap_to_palette(img: Image.Image) -> Image.Image:
    """Return an RGBA copy of `img` with every pixel snapped to its single
    nearest StandardPalette RGB value - a clean one-shot nearest-match, no
    dithering. Primary-remap indices excluded, same as every dithering
    function in this module.

    Needed after alpha-compositing multiple already-dithered (exact-palette)
    layers together (build/compositing.py's composite_layer_stack):
    Image.alpha_composite does a true per-channel weighted blend wherever
    any layer has partial alpha (anti-aliased edges, soft shadows), which
    produces off-palette RGB at those pixels even though every input layer
    was itself dithered to exact palette colours beforehand. Left alone,
    those off-palette pixels would be re-quantised uncontrollably by
    openrct2-cli's own (non-dithered) -m closest pass at build time,
    undermining the deliberate per-layer dithering choices with banding
    that looks like dithering gone wrong at every layer seam. This is a
    cleanup pass for that blending artefact, not a creative dithering
    decision, so it's deliberately undithered - applying dithering again
    here would just add a second, uncoordinated noise pattern on top of
    each layer's own already-dithered result.
    """
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb_result = _quantise_to_real_rgb(rgba.convert("RGB"), dither=Image.Dither.NONE)
    result = rgb_result.convert("RGBA")
    result.putalpha(alpha)
    return result
