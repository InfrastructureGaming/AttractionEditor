"""Alpha-over flattening of a ride's structure layers (see model.project.Layer)
into one final frame per direction/frame, in z-order, before sprite-building.

Each input image is expected to already be palette-quantized (dithered or
explicitly not, per Layer.dither_algorithm) - compositing is purely a pixel
operation, with no knowledge of layers, projects, or the filesystem."""

from __future__ import annotations

from PIL import Image


def composite_layer_stack(images: list[Image.Image]) -> Image.Image:
    """Alpha-over composite `images` in order: images[0] is furthest back,
    images[-1] is furthest front. All images must share one size - layers are
    rendered from the same camera per direction, so this should always hold;
    a mismatch indicates a scanning/validation bug upstream, not a recoverable
    runtime case, hence the plain ValueError rather than a silent resize.
    """
    if not images:
        raise ValueError("composite_layer_stack requires at least one image")

    base = images[0].convert("RGBA")
    for img in images[1:]:
        rgba = img.convert("RGBA")
        if rgba.size != base.size:
            raise ValueError(f"Layer size mismatch: {rgba.size} vs {base.size}")
        base = Image.alpha_composite(base, rgba)
    return base
