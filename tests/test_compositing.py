"""Tests for build/compositing.py: alpha-over flattening of a layer stack."""

from __future__ import annotations

import pytest
from PIL import Image

from attraction_editor.build.compositing import composite_layer_stack


def _solid(colour: tuple[int, int, int, int], size: tuple[int, int] = (4, 4)) -> Image.Image:
    return Image.new("RGBA", size, colour)


def test_composite_layer_stack_single_layer_returned_as_rgba():
    img = _solid((10, 20, 30, 255))
    result = composite_layer_stack([img])
    assert result.mode == "RGBA"
    assert result.getpixel((0, 0)) == (10, 20, 30, 255)


def test_composite_layer_stack_opaque_front_layer_wins():
    back = _solid((255, 0, 0, 255))
    front = _solid((0, 255, 0, 255))
    result = composite_layer_stack([back, front])
    assert result.getpixel((0, 0)) == (0, 255, 0, 255)


def test_composite_layer_stack_transparent_front_shows_back():
    back = _solid((255, 0, 0, 255))
    front = _solid((0, 255, 0, 0))
    result = composite_layer_stack([back, front])
    assert result.getpixel((0, 0)) == (255, 0, 0, 255)


def test_composite_layer_stack_z_order_matters():
    red = _solid((255, 0, 0, 255))
    green = _solid((0, 255, 0, 0))  # transparent green - shouldn't show either way
    blue = _solid((0, 0, 255, 128))  # half-transparent blue

    front_to_back = composite_layer_stack([red, blue])
    back_to_front = composite_layer_stack([blue, red])

    assert front_to_back.getpixel((0, 0)) != back_to_front.getpixel((0, 0))
    # blue-over-red: red shows through; red-over-blue: blue is fully opaque on top
    assert back_to_front.getpixel((0, 0)) == (255, 0, 0, 255)


def test_composite_layer_stack_three_layers():
    back = _solid((255, 0, 0, 255))
    middle = _solid((0, 255, 0, 0))  # fully transparent, invisible
    front = _solid((0, 0, 255, 255))
    result = composite_layer_stack([back, middle, front])
    assert result.getpixel((0, 0)) == (0, 0, 255, 255)


def test_composite_layer_stack_requires_at_least_one_image():
    with pytest.raises(ValueError, match="at least one image"):
        composite_layer_stack([])


def test_composite_layer_stack_size_mismatch_raises():
    a = _solid((255, 0, 0, 255), size=(4, 4))
    b = _solid((0, 255, 0, 255), size=(8, 8))
    with pytest.raises(ValueError, match="size mismatch"):
        composite_layer_stack([a, b])
