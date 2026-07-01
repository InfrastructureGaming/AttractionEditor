"""Tests for build/thumbnail.py: fitting any source image to the engine's
112x112 preview size (transparent padding, centered, never upscaled)."""

from __future__ import annotations

from PIL import Image

from attraction_editor.build.thumbnail import THUMBNAIL_SIZE, fit_to_thumbnail, render_thumbnail


def test_fit_oversized_image_downscales_into_box_preserving_aspect():
    # 2:1 and far larger than the box -> 112x56, centered with transparent bands.
    src = Image.new("RGBA", (448, 224), (255, 0, 0, 255))
    out = fit_to_thumbnail(src)

    assert out.size == (THUMBNAIL_SIZE, THUMBNAIL_SIZE)
    assert out.getpixel((0, 0))[3] == 0  # top-left is padding
    assert out.getpixel((THUMBNAIL_SIZE // 2, THUMBNAIL_SIZE // 2))[3] == 255  # content at centre


def test_fit_exact_size_keeps_full_content():
    src = Image.new("RGBA", (THUMBNAIL_SIZE, THUMBNAIL_SIZE), (0, 128, 0, 255))
    out = fit_to_thumbnail(src)

    assert out.size == (THUMBNAIL_SIZE, THUMBNAIL_SIZE)
    assert out.getpixel((0, 0))[3] == 255  # no padding introduced
    assert out.getpixel((THUMBNAIL_SIZE - 1, THUMBNAIL_SIZE - 1))[3] == 255


def test_fit_smaller_image_is_centered_not_upscaled():
    src = Image.new("RGBA", (40, 40), (0, 0, 255, 255))
    out = fit_to_thumbnail(src)

    assert out.size == (THUMBNAIL_SIZE, THUMBNAIL_SIZE)
    assert out.getpixel((0, 0))[3] == 0  # padding, not upscaled to fill
    offset = (THUMBNAIL_SIZE - 40) // 2  # 36
    assert out.getpixel((offset - 1, offset - 1))[3] == 0  # just outside the centred block
    assert out.getpixel((THUMBNAIL_SIZE // 2, THUMBNAIL_SIZE // 2))[3] == 255  # inside it


def test_render_thumbnail_writes_a_112_file(tmp_path):
    src_path = tmp_path / "src.png"
    Image.new("RGBA", (300, 300), (200, 100, 50, 255)).save(src_path)
    out_path = tmp_path / "out" / "_thumbnail.png"

    result = render_thumbnail(src_path, out_path)

    assert result == out_path
    assert out_path.exists()
    with Image.open(out_path) as im:
        assert im.size == (THUMBNAIL_SIZE, THUMBNAIL_SIZE)


def test_fit_output_is_on_palette_and_avoids_remap_zones():
    """Off-palette source colours (arbitrary author images) and the LANCZOS/alpha
    blends the fit introduces are snapped to real, NON-remap StandardPalette
    colours - so the thumbnail renders identically in-engine (it looked fine in
    the tool but wrong at runtime before) and can never be accidentally
    recoloured by a pixel that drifted into a remap zone."""
    import numpy as np

    from attraction_editor.build.dither import structure_indices
    from attraction_editor.palette.remap import load_standard_palette

    palette = load_standard_palette()
    allowed_codes = {(r << 16) | (g << 8) | b for i in structure_indices() for r, g, b in [palette[i]]}

    # A gradient full of off-palette colours; the downscale blends yet more.
    xs = np.arange(224)
    arr = np.zeros((224, 224, 4), dtype=np.uint8)
    arr[..., 0] = (xs[None, :] * 7) % 256
    arr[..., 1] = (xs[:, None] * 5) % 256
    arr[..., 2] = (xs[None, :] + xs[:, None]) % 256
    arr[..., 3] = 255

    out = np.asarray(fit_to_thumbnail(Image.fromarray(arr, "RGBA")))
    opaque = out[out[..., 3] > 0][:, :3].astype(int)
    codes = set(((opaque[:, 0] << 16) | (opaque[:, 1] << 8) | opaque[:, 2]).tolist())

    assert codes <= allowed_codes  # every visible pixel is a non-remap palette colour
