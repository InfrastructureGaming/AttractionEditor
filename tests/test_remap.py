"""Unit tests for palette/remap.py - colour swatches and secondary/tertiary
remap-range recolouring, plus a sanity check against a real TiltAWhirl frame."""

from __future__ import annotations

import pytest
from PIL import Image

from attraction_editor.palette.remap import (
    SECONDARY_REMAP_START,
    TERTIARY_REMAP_START,
    colour_swatch_rgb,
    load_colour_ramps,
    load_standard_palette,
    remap_preview,
)
from attraction_editor.sprites.scanner import frame_path
from tests.fixtures.tilt_a_whirl import TILT_A_WHIRL_DIR, make_tilt_a_whirl_project


def test_colour_swatch_rgb():
    palette = load_standard_palette()
    ramps = load_colour_ramps()

    r, g, b = colour_swatch_rgb("white")

    middle = ramps["white"][len(ramps["white"]) // 2]
    assert [r, g, b] == palette[middle]


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


def test_remap_preview_preserves_alpha():
    img = Image.new("RGBA", (2, 1), (255, 255, 255, 255))
    img.putpixel((0, 0), (255, 255, 255, 0))
    img.putpixel((1, 0), (255, 255, 255, 255))

    result = remap_preview(img, trim_colour="black", tertiary_colour="white")

    assert result.getpixel((0, 0))[3] == 0
    assert result.getpixel((1, 0))[3] == 255


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_remap_preview_tilt_a_whirl_core_frame():
    project = make_tilt_a_whirl_project()
    core_dir = project.project_dir / project.layers[0].sprite_dir

    scheme = project.colour_schemes[0]
    with Image.open(frame_path(core_dir, 0, 0)) as img:
        source = img.convert("RGBA")
        result = remap_preview(source, scheme.trim_colour, scheme.tertiary_colour)

    assert result.mode == "RGBA"
    assert result.size == source.size
    assert result.getchannel("A").tobytes() == source.getchannel("A").tobytes()
    assert result.tobytes() != source.tobytes()
