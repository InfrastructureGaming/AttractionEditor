"""Unit tests for palette/remap.py - colour swatches and secondary/tertiary
remap-range recolouring, plus a sanity check against a real rendered frame."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from attraction_editor.build.dither import dither_frame
from attraction_editor.palette.remap import (
    PRIMARY_REMAP_START,
    SECONDARY_REMAP_START,
    TERTIARY_REMAP_START,
    classify_remap_zone,
    colour_swatch_rgb,
    linear_to_srgb,
    load_colour_ramps,
    load_standard_palette,
    pixel_distances_to_palette,
    recolour_dithered_zones,
    remap_preview,
    srgb_to_linear,
)
from attraction_editor.sprites.scanner import frame_path
from tests.fixtures.synthetic import make_synthetic_project


def test_colour_swatch_rgb():
    palette = load_standard_palette()
    ramps = load_colour_ramps()

    r, g, b = colour_swatch_rgb("white")

    middle = ramps["white"][len(ramps["white"]) // 2]
    assert [r, g, b] == palette[middle]


def test_srgb_to_linear_known_values():
    # Fixed points 0 and 1, and the canonical mid-grey: sRGB 0.5 -> ~0.214 linear
    # (this gap is exactly the "dithering too dark" error linear-light fixes).
    out = srgb_to_linear(np.array([0.0, 0.5, 1.0], dtype=np.float32))
    assert out[0] == pytest.approx(0.0, abs=1e-6)
    assert out[1] == pytest.approx(0.2140, abs=1e-3)
    assert out[2] == pytest.approx(1.0, abs=1e-6)


def test_srgb_linear_round_trips():
    values = np.linspace(0.0, 1.0, 64, dtype=np.float32)
    assert np.allclose(linear_to_srgb(srgb_to_linear(values)), values, atol=1e-4)


def test_srgb_to_linear_clips_out_of_range_inputs():
    # Error diffusion can push a channel slightly past [0,1]; clamp, never NaN.
    out = srgb_to_linear(np.array([-0.5, 1.5], dtype=np.float32))
    assert not np.any(np.isnan(out))
    assert out[0] == pytest.approx(0.0) and out[1] == pytest.approx(1.0)


def test_pixel_distances_default_path_is_unchanged_srgb():
    # An exact palette colour has ~0 distance to its own entry, and the default
    # (sRGB) path is byte-for-byte the old behaviour (linear is opt-in only).
    palette = load_standard_palette()
    arr = np.array([[palette[100]]], dtype=np.uint8)  # shape (1,1,3)
    srgb = pixel_distances_to_palette(arr)
    assert srgb.shape == (1, 256)
    assert int(np.argmin(srgb[0])) == 100
    assert srgb[0, 100] == pytest.approx(0.0, abs=1e-3)
    assert np.array_equal(srgb, pixel_distances_to_palette(arr, linear=False))


def test_pixel_distances_linear_is_smaller_scale_but_same_extremes():
    palette = np.array(load_standard_palette(), dtype=np.uint8)
    # Pure black and pure white are transfer-function fixed points, so the
    # nearest palette entry must agree across both colour spaces.
    extremes = np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8)
    srgb = pixel_distances_to_palette(extremes)
    lin = pixel_distances_to_palette(extremes, linear=True)
    assert lin.max() <= 3.0 + 1e-3  # linear distances live in [0, 3], not 0..195075
    assert srgb.max() > 3.0
    assert np.array_equal(np.argmin(srgb, axis=1), np.argmin(lin, axis=1))


def test_linear_and_srgb_disagree_on_some_midtone_match():
    """The whole point: linear-light nearest-matching genuinely differs from
    sRGB for midtones (otherwise the change would be cosmetic)."""
    greys = np.array([[[v, v, v] for v in range(8, 248, 8)]], dtype=np.uint8)
    srgb_idx = np.argmin(pixel_distances_to_palette(greys), axis=1)
    lin_idx = np.argmin(pixel_distances_to_palette(greys, linear=True), axis=1)
    assert not np.array_equal(srgb_idx, lin_idx)


def test_recolour_dithered_zones_recolours_primary_with_body():
    palette = load_standard_palette()
    ramps = load_colour_ramps()
    primary_index = PRIMARY_REMAP_START + 3

    img = Image.new("RGBA", (1, 1), (*palette[primary_index], 255))
    result = recolour_dithered_zones(img, trim_colour="black", tertiary_colour="white", body_colour="bright_red")

    # primary pixel -> the bright_red ramp shade at the same in-zone offset
    assert list(result.getpixel((0, 0))[:3]) == palette[ramps["bright_red"][3]]


def test_recolour_dithered_zones_leaves_primary_untouched_without_body():
    palette = load_standard_palette()
    primary_index = PRIMARY_REMAP_START + 3

    img = Image.new("RGBA", (1, 1), (*palette[primary_index], 255))
    result = recolour_dithered_zones(img, trim_colour="black", tertiary_colour="white")

    assert list(result.getpixel((0, 0))[:3]) == palette[primary_index]  # unchanged (legacy two-zone)


def test_remap_preview_recolours_secondary_and_tertiary_pixels():
    palette = load_standard_palette()
    ramps = load_colour_ramps()

    secondary_index = SECONDARY_REMAP_START + 3
    tertiary_index = TERTIARY_REMAP_START + 3

    img = Image.new("RGBA", (2, 1), (0, 0, 0, 255))
    img.putpixel((0, 0), (*palette[secondary_index], 255))
    img.putpixel((1, 0), (*palette[tertiary_index], 255))

    result = remap_preview(img, trim_colour="black", tertiary_colour="white")

    expected_secondary = tuple(palette[ramps["black"][3]])
    expected_tertiary = tuple(palette[ramps["white"][3]])

    assert result.getpixel((0, 0))[:3] == expected_secondary
    assert result.getpixel((1, 0))[:3] == expected_tertiary


def test_remap_preview_does_not_quantize_non_remap_zone_pixels():
    """Regression test: an earlier version of remap_preview ran a hard
    nearest-match quantize() over the *entire* image before remapping,
    snapping every pixel - including ones nowhere near a remap zone - to an
    exact palette entry with zero residual error. That left nothing for a
    later dithering pass to diffuse, making "Preview dithering" a no-op for
    any frame that had gone through this function. Pixels outside the
    remap zones must keep their original, off-palette RGB value untouched."""
    off_palette_colour = (123, 77, 201, 255)  # deliberately not an exact palette entry
    palette = {tuple(rgb) for rgb in load_standard_palette()}
    assert off_palette_colour[:3] not in palette  # confirm the premise

    img = Image.new("RGBA", (1, 1), off_palette_colour)
    result = remap_preview(img, trim_colour="black", tertiary_colour="white")

    assert result.getpixel((0, 0)) == off_palette_colour


def test_remap_preview_followed_by_dithering_still_changes_pixels():
    """End-to-end version of the same regression: dithering a remapped
    frame must actually differ from not dithering it, for a smooth gradient
    that isn't already palette-exact."""
    width = 32
    img = Image.new("RGBA", (width, 1), (0, 0, 0, 255))
    for x in range(width):
        img.putpixel((x, 0), (x * 7 % 256, x * 11 % 256, x * 13 % 256, 255))

    remapped = remap_preview(img, trim_colour="black", tertiary_colour="white")
    dithered = dither_frame(remapped)

    assert remapped.convert("RGB").tobytes() != dithered.convert("RGB").tobytes()


def test_remap_preview_preserves_alpha():
    img = Image.new("RGBA", (2, 1), (255, 255, 255, 255))
    img.putpixel((0, 0), (255, 255, 255, 0))
    img.putpixel((1, 0), (255, 255, 255, 255))

    result = remap_preview(img, trim_colour="black", tertiary_colour="white")

    assert result.getpixel((0, 0))[3] == 0
    assert result.getpixel((1, 0))[3] == 255


def _borderline_pixel(rgb: tuple[int, int, int]) -> np.ndarray:
    img = Image.new("RGBA", (1, 1), (*rgb, 255))
    return pixel_distances_to_palette(np.array(img.convert("RGB")))


def test_classify_remap_zone_tolerance_zero_matches_nearest_match_rule():
    """tolerance=0 must reproduce the original fixed behaviour exactly:
    caught iff the zone's own best shade is also the pixel's single
    nearest match among all 256 palette entries."""
    palette = load_standard_palette()
    exact_zone_pixel = palette[SECONDARY_REMAP_START + 3]
    dist_sq = _borderline_pixel(tuple(exact_zone_pixel))

    caught, shade_idx, natural_win, _ = classify_remap_zone(dist_sq, SECONDARY_REMAP_START, tolerance=0)

    assert caught[0]
    assert natural_win[0]
    assert shade_idx[0] == 3


def test_classify_remap_zone_widening_catches_a_borderline_pixel():
    """[143, 31, 58] sits 1.86 RGB-distance units closer to a non-zone
    palette entry (index 63) than to secondary shade 3 - today's exact
    nearest-match rule misses it. A tolerance covering that margin should
    catch it; a smaller one should not."""
    dist_sq = _borderline_pixel((143, 31, 58))

    not_caught, _, natural_win, _ = classify_remap_zone(dist_sq, SECONDARY_REMAP_START, tolerance=0)
    still_not_caught, _, _, _ = classify_remap_zone(dist_sq, SECONDARY_REMAP_START, tolerance=1)
    caught, shade_idx, _, _ = classify_remap_zone(dist_sq, SECONDARY_REMAP_START, tolerance=2)

    assert not natural_win[0]
    assert not not_caught[0]
    assert not still_not_caught[0]
    assert caught[0]
    assert shade_idx[0] == 3


def test_classify_remap_zone_narrowing_excludes_a_borderline_win():
    """[143, 31, 60] currently wins secondary shade 3 by a margin of only
    1.86 RGB-distance units over its best alternative. Narrowing by more
    than that margin should exclude it even though it wins naturally."""
    dist_sq = _borderline_pixel((143, 31, 60))

    caught_today, _, natural_win, best_other_idx = classify_remap_zone(dist_sq, SECONDARY_REMAP_START, tolerance=0)
    still_caught, _, _, _ = classify_remap_zone(dist_sq, SECONDARY_REMAP_START, tolerance=-1)
    excluded, _, _, _ = classify_remap_zone(dist_sq, SECONDARY_REMAP_START, tolerance=-2)

    assert natural_win[0]
    assert caught_today[0]
    assert still_caught[0]
    assert not excluded[0]
    assert best_other_idx[0] == 63


def test_remap_preview_trim_tolerance_widens_recolouring():
    """End-to-end: the same borderline pixel from
    test_classify_remap_zone_widening_catches_a_borderline_pixel should only
    get recoloured to the chosen Trim colour once the tolerance covers it."""
    palette = load_standard_palette()
    ramps = load_colour_ramps()
    img = Image.new("RGBA", (1, 1), (143, 31, 58, 255))

    untouched = remap_preview(img, trim_colour="black", tertiary_colour="white", trim_tolerance=0)
    widened = remap_preview(img, trim_colour="black", tertiary_colour="white", trim_tolerance=2)

    assert untouched.getpixel((0, 0))[:3] == (143, 31, 58)  # not caught - original RGB kept
    assert widened.getpixel((0, 0))[:3] == tuple(palette[ramps["black"][3]])  # caught - recoloured


def test_remap_preview_trim_tolerance_narrows_recolouring():
    """End-to-end version of the narrowing classification test: a pixel
    that's recoloured by default should be excluded (kept as its original,
    un-recoloured RGB) once the tolerance is narrowed past its margin."""
    img = Image.new("RGBA", (1, 1), (143, 31, 60, 255))

    default = remap_preview(img, trim_colour="black", tertiary_colour="white", trim_tolerance=0)
    narrowed = remap_preview(img, trim_colour="black", tertiary_colour="white", trim_tolerance=-2)

    assert default.getpixel((0, 0))[:3] != (143, 31, 60)  # caught by default - recoloured
    assert narrowed.getpixel((0, 0))[:3] == (143, 31, 60)  # excluded - original RGB kept


def test_remap_preview_real_frame_preserves_mode_size_and_alpha(tmp_path):
    project = make_synthetic_project(tmp_path)
    core_dir = project.project_dir / project.layers[0].sprite_dir

    scheme = project.colour_schemes[0]
    with Image.open(frame_path(core_dir, 0, 0)) as img:
        source = img.convert("RGBA")
        result = remap_preview(source, scheme.trim_colour, scheme.tertiary_colour)

    assert result.mode == "RGBA"
    assert result.size == source.size
    assert result.getchannel("A").tobytes() == source.getchannel("A").tobytes()
    assert result.tobytes() != source.tobytes()
