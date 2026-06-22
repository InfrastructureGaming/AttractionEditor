"""Tests for attraction_editor.build.dither: Floyd-Steinberg, Bayer
(ordered), and Atkinson dithering, plus the per-layer dispatch."""

from __future__ import annotations

from PIL import Image

from attraction_editor.build.dither import (
    dither_frame,
    dither_frame_atkinson,
    dither_frame_bayer,
    dither_frame_by_algorithm,
)
from attraction_editor.palette.remap import (
    PRIMARY_REMAP_START,
    REMAP_LENGTH,
    SECONDARY_REMAP_START,
    load_standard_palette,
)


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
    dithering pattern at all, just each pixel's closest palette entry."""
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
    img = _make_gradient_rgba(16, 16)
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
    img = _make_gradient_rgba(16, 16)
    assert list(dither_frame_by_algorithm(img, "floyd_steinberg").getdata()) == list(dither_frame(img).getdata())


def test_dither_frame_by_algorithm_dispatches_bayer():
    img = _make_gradient_rgba(16, 16)
    assert list(dither_frame_by_algorithm(img, "bayer", strength=16).getdata()) == list(
        dither_frame_bayer(img, strength=16).getdata()
    )


def test_dither_frame_by_algorithm_dispatches_atkinson():
    img = _make_gradient_rgba(16, 16)
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
    function directly - existing dithering behaviour is byte-identical
    whenever this feature isn't in use."""
    img = _make_gradient_rgba(16, 16)

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
