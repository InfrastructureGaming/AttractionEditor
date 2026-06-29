"""Tests for attraction_editor.build.dither: Floyd-Steinberg, Bayer
(ordered), and Atkinson dithering, plus the per-layer dispatch."""

from __future__ import annotations

import numpy as np
from PIL import Image

from attraction_editor.build.dither import (
    _linear_luma,
    dither_frame,
    dither_frame_atkinson,
    dither_frame_bayer,
    dither_frame_by_algorithm,
    primary_zone_indices,
    secondary_zone_indices,
    snap_to_palette,
)
from attraction_editor.palette.remap import (
    PRIMARY_REMAP_START,
    REMAP_LENGTH,
    SECONDARY_REMAP_START,
    linear_to_srgb,
    load_standard_palette,
    srgb_to_linear,
)


def _palette_index_of(rgba_pixel) -> int:
    """Exact palette index of a dithered output pixel (output is always exact
    StandardPalette RGB, so an exact match exists)."""
    rgb = [int(c) for c in rgba_pixel[:3]]
    for i, entry in enumerate(load_standard_palette()):
        if list(entry) == rgb:
            return i
    return -1


def _make_gradient_rgba(w: int = 64, h: int = 64) -> Image.Image:
    """RGBA image with a horizontal RGB gradient and a transparent strip at the bottom."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    px = img.load()
    for x in range(w):
        r = int(x * 255 / (w - 1))
        g = int((w - 1 - x) * 255 / (w - 1))
        b = 128
        for y in range(h - 8):
            px[x, y] = (r, g, b, 255)
        for y in range(h - 8, h):
            px[x, y] = (r, g, b, 0)  # fully transparent strip
    return img


def _standard_palette_set() -> set[tuple[int, int, int]]:
    return {tuple(rgb) for rgb in load_standard_palette()}


def test_authored_secondary_mask_overrides_distance_classification():
    """An authored zone mask classifies directly: a neutral grey pixel - which
    the distance/catch-tolerance path would never call secondary (it's nowhere
    near the bright-pink reference shade) - lands in the secondary range purely
    because the mask says so."""
    img = Image.new("RGBA", (2, 1), (120, 140, 120, 255))
    masks = {"secondary": np.array([[True, False]])}

    out = np.asarray(dither_frame_by_algorithm(img, "floyd_steinberg", zone_masks=masks).convert("RGBA"))

    secondary = set(secondary_zone_indices())
    assert _palette_index_of(out[0, 0]) in secondary  # masked pixel -> secondary
    assert _palette_index_of(out[0, 1]) not in secondary  # structure pixel stays out


def test_authored_primary_mask_unlocks_the_primary_range():
    """The new capability: only an authored COLOR_PRIMARY mask can push pixels
    into 243-254, which the distance path excludes entirely."""
    img = Image.new("RGBA", (2, 1), (120, 140, 120, 255))
    masks = {"primary": np.array([[True, False]])}

    out = np.asarray(dither_frame_by_algorithm(img, "floyd_steinberg", zone_masks=masks).convert("RGBA"))

    primary = set(primary_zone_indices())
    assert _palette_index_of(out[0, 0]) in primary
    assert _palette_index_of(out[0, 1]) not in primary


def test_authored_zone_picks_shade_by_luma_ignoring_chroma():
    """The crux of grayscale authoring: two pixels with the SAME luminance but
    very different chroma must land on the SAME ramp shade - the zone's hue is
    irrelevant (the engine supplies it at runtime)."""
    grey = np.array([150.0, 150.0, 150.0], dtype=np.float32)
    grey_luma = float(_linear_luma(grey))
    # A pure-green pixel constructed to share that exact linear luma.
    g = float(linear_to_srgb(np.array([grey_luma / 0.587], dtype=np.float32))[0]) * 255.0

    img = Image.new("RGBA", (2, 1), (0, 0, 0, 255))
    img.putpixel((0, 0), (150, 150, 150, 255))
    img.putpixel((1, 0), (0, int(round(g)), 0, 255))
    masks = {"secondary": np.array([[True, True]])}

    # strength=0 => deterministic nearest-luma snap (no ordered perturbation).
    out = np.asarray(dither_frame_by_algorithm(img, "floyd_steinberg", strength=0, zone_masks=masks).convert("RGBA"))

    assert tuple(out[0, 0][:3]) == tuple(out[0, 1][:3])


def test_authored_zone_luma_gradient_is_monotonic_and_uses_the_ramp():
    """A grey gradient maps to ascending ramp shades by brightness, spanning more
    than one shade."""
    w = 24
    img = Image.new("RGBA", (w, 1), (0, 0, 0, 255))
    for x in range(w):
        v = int(x * 255 / (w - 1))
        img.putpixel((x, 0), (v, v, v, 255))
    masks = {"primary": np.ones((1, w), dtype=bool)}

    out = np.asarray(dither_frame_by_algorithm(img, "floyd_steinberg", strength=0, zone_masks=masks).convert("RGBA"))

    lumas = [float(_linear_luma(out[0, x][:3].astype(np.float32))) for x in range(w)]
    assert all(lumas[i] <= lumas[i + 1] + 1e-6 for i in range(w - 1))  # non-decreasing
    assert len({tuple(out[0, x][:3]) for x in range(w)}) > 1  # uses the ramp, not one flat shade


def test_snap_to_palette_preserves_authored_primary_pixels():
    """Regression for the 'Main colour won't recolour' bug: snap_to_palette must
    NOT strip exact 243-254 primary-remap pixels - the post-composite snap used
    to quantise them onto fixed, non-remappable colours."""
    palette = load_standard_palette()
    img = Image.new("RGBA", (2, 1), (0, 0, 0, 255))
    img.putpixel((0, 0), (*palette[248], 255))  # exact primary-range colour
    img.putpixel((1, 0), (*palette[100], 255))  # exact normal colour

    out = np.asarray(snap_to_palette(img).convert("RGBA"))

    assert _palette_index_of(out[0, 0]) == 248  # primary preserved, not stripped
    assert _palette_index_of(out[0, 1]) == 100  # normal preserved


def test_snap_to_palette_still_fixes_off_palette_pixels():
    """Off-palette (AA-blend) pixels are still cleaned up - to a non-primary entry."""
    img = Image.new("RGBA", (1, 1), (127, 63, 200, 255))  # arbitrary off-palette colour

    out = np.asarray(snap_to_palette(img).convert("RGBA"))
    idx = _palette_index_of(out[0, 0])

    assert idx != -1  # snapped onto an exact palette entry
    assert idx not in set(primary_zone_indices())  # never invents a primary-zone pixel


def test_zone_masks_none_falls_back_to_distance_path():
    """With no masks, behaviour is unchanged - a frame with no remap content
    just snaps to the palette and never lands in any remap zone."""
    img = Image.new("RGBA", (4, 4), (120, 140, 120, 255))

    out = np.asarray(dither_frame_by_algorithm(img, "floyd_steinberg").convert("RGBA"))

    idxs = {_palette_index_of(out[y, x]) for y in range(4) for x in range(4)}
    assert all(i not in set(primary_zone_indices()) for i in idxs)
    assert all(i not in set(secondary_zone_indices()) for i in idxs)


def _make_gradient_rgba_no_zone(w: int = 16, h: int = 16) -> Image.Image:
    """Grayscale gradient (r=g=b) - never classifies into the secondary
    (bright_pink) or tertiary (yellow) remap zone, so
    dither_frame_by_algorithm's zone-constrained quantisation is a pure
    pass-through (no zone content to constrain) and its result is byte-
    identical to calling the underlying algorithm directly. Used by tests
    that check dispatch/strength/tolerance-no-op behaviour specifically,
    not zone classification itself (see test_dither_frame_by_algorithm_*
    and test_catch_tolerance_zero_is_a_no_op_for_every_algorithm)."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    px = img.load()
    for x in range(w):
        g = int(x * 255 / (w - 1))
        for y in range(h):
            px[x, y] = (g, g, g, 255)
    return img


# ---------------------------------------------------------------------------
# dither_frame
# ---------------------------------------------------------------------------

def test_dither_frame_preserves_size():
    img = _make_gradient_rgba(48, 32)
    out = dither_frame(img)
    assert out.size == img.size


def test_dither_frame_output_is_rgba():
    img = _make_gradient_rgba()
    out = dither_frame(img)
    assert out.mode == "RGBA"


def test_dither_frame_preserves_alpha():
    """Transparent pixels in the source must remain fully transparent."""
    img = _make_gradient_rgba(32, 32)
    out = dither_frame(img)
    src_px = img.load()
    out_px = out.load()
    w, h = img.size
    for x in range(w):
        for y in range(h):
            if src_px[x, y][3] == 0:
                assert out_px[x, y][3] == 0, f"alpha lost at ({x},{y})"


def test_dither_frame_all_opaque_pixels_in_standard_palette():
    """Every opaque output pixel must be an exact StandardPalette RGB entry."""
    img = _make_gradient_rgba(64, 64)
    out = dither_frame(img)
    palette = _standard_palette_set()
    out_px = out.load()
    w, h = out.size
    for x in range(w):
        for y in range(h):
            r, g, b, a = out_px[x, y]
            if a > 0:
                assert (r, g, b) in palette, (  # type: ignore[operator]
                    f"pixel ({x},{y}) = ({r},{g},{b}) not in StandardPalette"
                )


def test_dither_frame_no_primary_remap_indices():
    """No opaque output pixel should map to a primary-remap palette index (243-254)."""
    img = _make_gradient_rgba(64, 64)
    out = dither_frame(img)

    # Re-quantise output RGB (no dithering) against the real palette to recover indices.
    palette = load_standard_palette()
    pal_map = {tuple(rgb): i for i, rgb in enumerate(palette)}

    out_px = out.load()
    w, h = out.size
    for x in range(w):
        for y in range(h):
            r, g, b, a = out_px[x, y]
            if a > 0:
                idx = pal_map.get((r, g, b))
                assert idx is not None
                assert not (PRIMARY_REMAP_START <= idx < PRIMARY_REMAP_START + REMAP_LENGTH), (
                    f"pixel ({x},{y}) maps to primary-remap index {idx}"
                )


def test_dither_frame_opaque_input_stays_opaque():
    """A 100% opaque input must produce a 100% opaque output."""
    img = Image.new("RGBA", (16, 16), (200, 100, 50, 255))
    out = dither_frame(img)
    out_px = out.load()
    for x in range(16):
        for y in range(16):
            assert out_px[x, y][3] == 255


def test_dither_frame_default_strength_is_byte_identical_to_explicit_32():
    """Regression guard for the default-argument value itself, independent
    of any caller's behaviour."""
    img = _make_gradient_rgba(32, 32)
    assert list(dither_frame(img).getdata()) == list(dither_frame(img, strength=32).getdata())


def test_dither_frame_strength_zero_is_plain_nearest_match():
    """strength=0 must degenerate to the same plain (undithered)
    nearest-match result dither_frame_bayer's strength=0 produces - no
    dithering pattern at all, just each pixel's closest palette entry.
    Both use PIL's own quantize(dither=NONE) for this, so they agree
    exactly."""
    img = _make_gradient_rgba(32, 32)
    assert list(dither_frame(img, strength=0).getdata()) == list(dither_frame_bayer(img, strength=0).getdata())


def test_dither_frame_strength_changes_the_output():
    """Regression test for "changing dither strength has no visual effect" -
    dither_frame previously had no strength parameter at all; the spinbox
    silently did nothing whenever a layer used the default
    floyd_steinberg algorithm."""
    img = _make_gradient_rgba(32, 32)
    full = dither_frame(img, strength=32)
    half = dither_frame(img, strength=16)
    none_ = dither_frame(img, strength=0)

    assert list(half.getdata()) != list(full.getdata())
    assert list(half.getdata()) != list(none_.getdata())
    assert list(none_.getdata()) != list(full.getdata())


def test_dither_frame_strength_is_clamped_to_0_32_range():
    """The UI's strength spinbox allows up to 255 (shared range across all
    three algorithms) - values above 32 must behave like 32, not error or
    keep scaling."""
    img = _make_gradient_rgba(16, 16)
    assert list(dither_frame(img, strength=32).getdata()) == list(dither_frame(img, strength=255).getdata())
    assert list(dither_frame(img, strength=0).getdata()) == list(dither_frame(img, strength=-10).getdata())


def test_dither_frame_by_algorithm_floyd_steinberg_passes_strength_through():
    img = _make_gradient_rgba_no_zone(16, 16)
    assert list(dither_frame_by_algorithm(img, "floyd_steinberg", strength=10).getdata()) == list(
        dither_frame(img, strength=10).getdata()
    )


# ---------------------------------------------------------------------------
# dither_frame_bayer
# ---------------------------------------------------------------------------


def test_dither_frame_bayer_preserves_size_and_alpha():
    img = _make_gradient_rgba(32, 32)
    out = dither_frame_bayer(img)
    assert out.size == img.size
    assert out.mode == "RGBA"
    src_px, out_px = img.load(), out.load()
    for x in range(32):
        for y in range(24, 32):  # transparent strip
            assert out_px[x, y][3] == 0


def test_dither_frame_bayer_all_opaque_pixels_in_standard_palette():
    img = _make_gradient_rgba(64, 64)
    out = dither_frame_bayer(img)
    palette = _standard_palette_set()
    out_px = out.load()
    for x in range(64):
        for y in range(56):
            r, g, b, a = out_px[x, y]
            if a > 0:
                assert (r, g, b) in palette


def test_dither_frame_bayer_threshold_is_position_dependent_not_diffusion():
    """The same pixel value at the same (x, y) must quantise the same way
    regardless of its neighbours - proves the threshold depends only on
    position + colour, never on neighbouring pixels (unlike error diffusion)."""
    w, h = 16, 16
    shared_xy = (8, 8)
    shared_colour = (130, 90, 200, 255)

    img_a = Image.new("RGBA", (w, h), (10, 10, 10, 255))
    img_b = Image.new("RGBA", (w, h), (240, 240, 240, 255))
    img_a.putpixel(shared_xy, shared_colour)
    img_b.putpixel(shared_xy, shared_colour)

    out_a = dither_frame_bayer(img_a)
    out_b = dither_frame_bayer(img_b)
    assert out_a.getpixel(shared_xy) == out_b.getpixel(shared_xy)


def test_dither_frame_bayer_strength_zero_is_nearest_match():
    """strength=0 degenerates to plain nearest-colour matching: a flat-colour
    input must produce a perfectly uniform output (no induced dither noise)."""
    img = Image.new("RGBA", (24, 24), (123, 77, 44, 255))
    out = dither_frame_bayer(img, strength=0)
    out_px = out.load()
    first = out_px[0, 0]
    for x in range(24):
        for y in range(24):
            assert out_px[x, y] == first


# ---------------------------------------------------------------------------
# dither_frame_atkinson
# ---------------------------------------------------------------------------


def test_dither_frame_atkinson_preserves_size_and_alpha():
    img = _make_gradient_rgba(24, 24)
    out = dither_frame_atkinson(img)
    assert out.size == img.size
    assert out.mode == "RGBA"
    out_px = out.load()
    for x in range(24):
        for y in range(16, 24):  # transparent strip
            assert out_px[x, y][3] == 0


def test_dither_frame_atkinson_all_opaque_pixels_in_standard_palette():
    img = _make_gradient_rgba(24, 24)
    out = dither_frame_atkinson(img)
    palette = _standard_palette_set()
    out_px = out.load()
    for x in range(24):
        for y in range(16):
            r, g, b, a = out_px[x, y]
            if a > 0:
                assert (r, g, b) in palette


def test_dither_frame_atkinson_strength_zero_is_nearest_match():
    img = Image.new("RGBA", (16, 16), (60, 150, 90, 255))
    out = dither_frame_atkinson(img, strength=0)
    out_px = out.load()
    first = out_px[0, 0]
    for x in range(16):
        for y in range(16):
            assert out_px[x, y] == first


def test_dither_frame_atkinson_diffuses_error_at_full_strength():
    """Full-strength Atkinson must differ from the strength=0 (plain
    nearest-match) result for a smooth gradient - otherwise no error is
    actually being diffused."""
    img = _make_gradient_rgba(32, 32)
    no_diffusion = dither_frame_atkinson(img, strength=0)
    full_diffusion = dither_frame_atkinson(img, strength=32)
    assert list(no_diffusion.getdata()) != list(full_diffusion.getdata())


# ---------------------------------------------------------------------------
# dither_frame_by_algorithm
# ---------------------------------------------------------------------------


def test_dither_frame_by_algorithm_dispatches_floyd_steinberg():
    img = _make_gradient_rgba_no_zone(16, 16)
    assert list(dither_frame_by_algorithm(img, "floyd_steinberg").getdata()) == list(dither_frame(img).getdata())


def test_dither_frame_by_algorithm_dispatches_bayer():
    img = _make_gradient_rgba_no_zone(16, 16)
    assert list(dither_frame_by_algorithm(img, "bayer", strength=16).getdata()) == list(
        dither_frame_bayer(img, strength=16).getdata()
    )


def test_dither_frame_by_algorithm_dispatches_atkinson():
    img = _make_gradient_rgba_no_zone(16, 16)
    assert list(dither_frame_by_algorithm(img, "atkinson", strength=16).getdata()) == list(
        dither_frame_atkinson(img, strength=16).getdata()
    )


def test_dither_frame_by_algorithm_none_returns_unchanged_rgba():
    img = _make_gradient_rgba(16, 16)
    out = dither_frame_by_algorithm(img, "none")
    assert out.mode == "RGBA"
    assert list(out.getdata()) == list(img.convert("RGBA").getdata())


# ---------------------------------------------------------------------------
# dither_frame_by_algorithm's trim_tolerance/tertiary_tolerance (catch
# tolerance bias - see palette/remap.py's classify_remap_zone)
# ---------------------------------------------------------------------------

# [143, 31, 58] is 1.86 RGB-distance units closer to a non-zone palette
# entry than to secondary remap shade 3 - it doesn't win that shade's
# nearest-match race on its own (see test_remap.py's classify_remap_zone
# tests, which derive and verify this exact figure).
_BORDERLINE_SECONDARY_RGB = (143, 31, 58)


def _make_flat_rgba(rgb: tuple[int, int, int], size: int = 8) -> Image.Image:
    return Image.new("RGBA", (size, size), (*rgb, 255))


def test_catch_tolerance_zero_is_a_no_op_for_every_algorithm():
    """Default tolerance (0, 0) must reproduce calling the underlying
    function directly when the image has no zone content at all - the
    zone-constrained quantisation path is a pure pass-through with nothing
    to constrain. (For an image *with* zone content, tolerance=0 still
    selects the zone-constrained path - see dither_frame_by_algorithm's
    docstring - so this specific equivalence only holds zone-free.)"""
    img = _make_gradient_rgba_no_zone(16, 16)

    assert list(dither_frame_by_algorithm(img, "floyd_steinberg", trim_tolerance=0, tertiary_tolerance=0).getdata()) == list(
        dither_frame(img).getdata()
    )
    assert list(
        dither_frame_by_algorithm(img, "bayer", strength=16, trim_tolerance=0, tertiary_tolerance=0).getdata()
    ) == list(dither_frame_bayer(img, strength=16).getdata())
    assert list(
        dither_frame_by_algorithm(img, "atkinson", strength=16, trim_tolerance=0, tertiary_tolerance=0).getdata()
    ) == list(dither_frame_atkinson(img, strength=16).getdata())


def test_catch_tolerance_widening_pulls_borderline_pixels_into_the_zone():
    """A flat image of the borderline colour sits almost exactly between two
    competing palette entries (margin 1.86), so even at tolerance=0 plain
    F-S dithering naturally checkerboards between the two rather than
    picking either uniformly. Widening past that margin pre-snaps every
    pixel exactly onto the zone shade *before* F-S runs, leaving it zero
    residual error to diffuse - the dithered result becomes fully uniform."""
    img = _make_flat_rgba(_BORDERLINE_SECONDARY_RGB)
    target_rgb = tuple(load_standard_palette()[SECONDARY_REMAP_START + 3])

    untouched = dither_frame_by_algorithm(img, "floyd_steinberg", trim_tolerance=0)
    widened = dither_frame_by_algorithm(img, "floyd_steinberg", trim_tolerance=2)

    assert any(px[:3] != target_rgb for px in untouched.getdata())  # still a dithered checkerboard
    assert all(px[:3] == target_rgb for px in widened.getdata())  # fully pulled in, no residual error left


def test_catch_tolerance_does_not_apply_to_none_algorithm():
    """"none" is the artist's explicit choice to skip quantisation entirely -
    a nonzero tolerance must not sneak in any palette-snapping there."""
    img = _make_flat_rgba(_BORDERLINE_SECONDARY_RGB)

    out = dither_frame_by_algorithm(img, "none", trim_tolerance=100)

    assert list(out.getdata()) == list(img.convert("RGBA").getdata())


def test_dither_frame_by_algorithm_unknown_raises():
    img = _make_gradient_rgba(8, 8)
    try:
        dither_frame_by_algorithm(img, "not_a_real_algorithm")
        assert False, "expected ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# snap_to_palette
# ---------------------------------------------------------------------------


def test_snap_to_palette_fixes_alpha_blend_artifacts():
    """Regression test for the actual bug report: Image.alpha_composite
    blends two already-dithered (exact-palette) layers' RGB values
    wherever either has partial alpha, producing off-palette pixels that
    openrct2-cli's own -m closest pass would otherwise re-quantise
    uncontrollably. snap_to_palette must put every pixel back on-palette."""
    from attraction_editor.build.compositing import composite_layer_stack

    palette_set = {tuple(rgb) for rgb in load_standard_palette()}

    back = dither_frame(Image.new("RGBA", (10, 10), (200, 50, 50, 255)))

    front = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    for x in range(10):
        for y in range(10):
            front.putpixel((x, y), (50, 200, 50, 128))
    front = dither_frame(front)

    composite = composite_layer_stack([back, front])
    assert any(px[:3] not in palette_set for px in composite.getdata())  # confirms the premise

    snapped = snap_to_palette(composite)

    assert all(px[:3] in palette_set for px in snapped.getdata())


def test_snap_to_palette_preserves_alpha():
    img = Image.new("RGBA", (2, 1), (123, 77, 201, 255))
    img.putpixel((0, 0), (123, 77, 201, 0))
    img.putpixel((1, 0), (123, 77, 201, 200))

    result = snap_to_palette(img)

    assert result.getpixel((0, 0))[3] == 0
    assert result.getpixel((1, 0))[3] == 200


def test_snap_to_palette_does_not_invent_primary_pixels_from_off_palette():
    """An OFF-palette pixel near a primary-range colour must still snap to a
    non-primary entry (snap must never create a spurious recolourable pixel).
    Note: an *exact* primary pixel is now deliberately preserved - that's the
    authored-zone path - see test_snap_to_palette_preserves_authored_primary_pixels."""
    palette = load_standard_palette()
    pal_map = {tuple(rgb): i for i, rgb in enumerate(palette)}

    # Nudge an exact primary colour off-palette so it's an AA-blend-style pixel.
    nudged = tuple(min(255, c + 1) for c in palette[PRIMARY_REMAP_START + 3])
    img = Image.new("RGBA", (1, 1), (*nudged, 255))
    result = snap_to_palette(img)

    idx = pal_map[result.getpixel((0, 0))[:3]]
    assert not (PRIMARY_REMAP_START <= idx < PRIMARY_REMAP_START + REMAP_LENGTH)


def test_snap_to_palette_is_a_no_op_for_already_exact_pixels():
    """A frame that's already entirely on-palette (the common case for a
    single, fully-opaque layer) should pass through unchanged."""
    img = dither_frame(Image.new("RGBA", (8, 8), (90, 140, 30, 255)))

    result = snap_to_palette(img)

    assert result.convert("RGB").tobytes() == img.convert("RGB").tobytes()
