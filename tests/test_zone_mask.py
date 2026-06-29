"""Tests for build/zone_mask.py - reading per-zone recolour masks from a
Blender multi-layer "zone pass" EXR. Synthetic EXRs are written here so the
tests don't depend on any rendered frames."""

from __future__ import annotations

import numpy as np

from attraction_editor.build.zone_mask import ZONE_LAYER_NAMES, read_zone_masks


def _write_zone_exr(path, width, height, layers: dict[str, np.ndarray]) -> None:
    """Write a multi-layer float EXR: each `layers` entry becomes one RGBA
    layer with its float values in R and A (G/B zero), mirroring how the
    Blender AOV stencils come through."""
    import Imath
    import OpenEXR

    channel = Imath.Channel(Imath.PixelType(Imath.PixelType.FLOAT))
    header = OpenEXR.Header(width, height)
    channels = {}
    pixels = {}
    zero = np.zeros((height, width), dtype=np.float32)
    for layer, value_arr in layers.items():
        value = np.ascontiguousarray(value_arr.astype(np.float32))
        for comp in ("R", "G", "B", "A"):
            name = f"{layer}.{comp}"
            channels[name] = channel
            pixels[name] = (value if comp in ("R", "A") else zero).tobytes()
    header["channels"] = channels
    out = OpenEXR.OutputFile(str(path), header)
    out.writePixels(pixels)
    out.close()


def test_reads_present_zone_layers_aligned(tmp_path):
    w, h = 4, 4
    trim = np.zeros((h, w), dtype=np.float32)
    trim[:, 0] = 1.0  # left column
    primary = np.zeros((h, w), dtype=np.float32)
    primary[:, 3] = 1.0  # right column
    path = tmp_path / "AOVdir0_f0000.exr"
    _write_zone_exr(path, w, h, {"COLOR_TRIM": trim, "COLOR_PRIMARY": primary})

    masks = read_zone_masks(path)

    assert set(masks) == {"secondary", "primary"}
    assert masks["secondary"].shape == (h, w)
    assert masks["secondary"].dtype == bool
    assert np.array_equal(masks["secondary"], trim > 0.5)
    assert np.array_equal(masks["primary"], primary > 0.5)
    # disjoint, exactly as authored
    assert not np.any(masks["secondary"] & masks["primary"])


def test_absent_layers_are_omitted(tmp_path):
    w, h = 3, 3
    trim = np.ones((h, w), dtype=np.float32)
    path = tmp_path / "AOVdir0_f0000.exr"
    _write_zone_exr(path, w, h, {"COLOR_TRIM": trim})

    masks = read_zone_masks(path)

    # Only the wired-up zone comes back; the others are simply missing.
    assert set(masks) == {"secondary"}
    assert "tertiary" not in masks and "primary" not in masks


def test_all_three_zones(tmp_path):
    w, h = 3, 1
    layers = {
        "COLOR_TRIM": np.array([[1, 0, 0]], dtype=np.float32),
        "COLOR_TERTIARY": np.array([[0, 1, 0]], dtype=np.float32),
        "COLOR_PRIMARY": np.array([[0, 0, 1]], dtype=np.float32),
    }
    path = tmp_path / "AOVdir0_f0000.exr"
    _write_zone_exr(path, w, h, layers)

    masks = read_zone_masks(path)

    assert set(masks) == {"secondary", "tertiary", "primary"}
    assert masks["secondary"][0, 0] and not masks["secondary"][0, 1]
    assert masks["tertiary"][0, 1] and not masks["tertiary"][0, 0]
    assert masks["primary"][0, 2] and not masks["primary"][0, 1]


def test_unknown_layer_is_ignored(tmp_path):
    w, h = 2, 2
    layers = {
        "COLOR_TRIM": np.ones((h, w), dtype=np.float32),
        "COLOR_BOGUS": np.ones((h, w), dtype=np.float32),
    }
    path = tmp_path / "AOVdir0_f0000.exr"
    _write_zone_exr(path, w, h, layers)

    masks = read_zone_masks(path)

    assert set(masks) == {"secondary"}


def test_threshold_is_binary(tmp_path):
    w, h = 2, 1
    # one pixel fully in the zone, one fully out
    trim = np.array([[1.0, 0.0]], dtype=np.float32)
    path = tmp_path / "AOVdir0_f0000.exr"
    _write_zone_exr(path, w, h, {"COLOR_TRIM": trim})

    masks = read_zone_masks(path)

    assert masks["secondary"][0, 0]
    assert not masks["secondary"][0, 1]


def test_layer_map_covers_the_three_remap_zones():
    # Guard the contract the build path relies on.
    assert set(ZONE_LAYER_NAMES.values()) == {"secondary", "tertiary", "primary"}
