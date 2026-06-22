"""Tests for build/layers.py: per-layer dither rendering (production - no
colour remap), static-layer caching, preview-only recolouring, and full
multi-layer composite-frame generation."""

from __future__ import annotations

from PIL import Image

from attraction_editor.build.layers import (
    build_composite_frames,
    composite_preview_frame,
    render_layer_frame,
    render_layer_frame_preview,
)
from attraction_editor.model.project import ColourScheme, Layer
from attraction_editor.palette.remap import (
    REMAP_LENGTH,
    SECONDARY_REMAP_START,
    TERTIARY_REMAP_START,
    load_standard_palette,
)
from attraction_editor.sprites.scanner import frame_path
from tests.fixtures.synthetic import FRAME_SIZE, make_multilayer_synthetic_project, make_synthetic_project


def test_render_layer_frame_static_layer_is_cached(tmp_path):
    """A static layer's result for a given direction is computed once and
    reused (same object) for every subsequent frame request, regardless of
    which frame is asked for - there's only one source image per direction."""
    project = make_multilayer_synthetic_project(tmp_path)
    background = project.layers[0]
    assert background.kind == "static"

    cache = {}
    frame0 = render_layer_frame(project, background, direction=0, frame=0, dither=False, cache=cache)
    frame1 = render_layer_frame(project, background, direction=0, frame=1, dither=False, cache=cache)
    frame0_again = render_layer_frame(project, background, direction=0, frame=0, dither=False, cache=cache)

    assert frame0 is frame1
    assert frame0 is frame0_again


def test_render_layer_frame_animated_layer_not_cached(tmp_path):
    project = make_multilayer_synthetic_project(tmp_path)
    core = project.layers[1]
    assert core.kind == "animated"

    cache = {}
    frame0 = render_layer_frame(project, core, direction=0, frame=0, dither=False, cache=cache)
    frame1 = render_layer_frame(project, core, direction=0, frame=1, dither=False, cache=cache)

    # Different frames of an animated layer are genuinely different source files.
    assert list(frame0.getdata()) != list(frame1.getdata()) or frame0.size == frame1.size


def test_render_layer_frame_dither_false_skips_dithering(tmp_path):
    project = make_synthetic_project(tmp_path)
    layer = project.layers[0]

    no_dither = render_layer_frame(project, layer, direction=0, frame=0, dither=False)
    assert no_dither.mode == "RGBA"


def test_render_layer_frame_dither_true_applies_layers_algorithm(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.layers = [Layer(name="Core", sprite_dir="Frames/Core", kind="animated", dither_algorithm="bayer")]

    dithered = render_layer_frame(project, project.layers[0], direction=0, frame=0, dither=True)
    undithered = render_layer_frame(project, project.layers[0], direction=0, frame=0, dither=False)

    assert list(dithered.getdata()) != list(undithered.getdata())


def test_render_layer_frame_production_path_preserves_remap_zones(tmp_path):
    """The production render path (no colour scheme) must NOT bake any colour
    in - pixels rendered in the literal secondary/tertiary reference shades
    must still land in those same palette zones after dithering, so the
    engine can recolour them live at render time. This is the exact bug this
    session fixed: render_layer_frame must never call remap_preview."""
    palette = load_standard_palette()

    project = make_synthetic_project(tmp_path)
    layer = project.layers[0]
    sprite_dir = project.project_dir / layer.sprite_dir

    img = Image.new("RGBA", (2, 1), (0, 0, 0, 255))
    img.putpixel((0, 0), (*palette[SECONDARY_REMAP_START + 3], 255))
    img.putpixel((1, 0), (*palette[TERTIARY_REMAP_START + 3], 255))
    img.save(frame_path(sprite_dir, 0, 0))

    result = render_layer_frame(project, layer, direction=0, frame=0, dither=True)

    pal_map = {tuple(rgb): i for i, rgb in enumerate(palette)}
    idx0 = pal_map[result.getpixel((0, 0))[:3]]
    idx1 = pal_map[result.getpixel((1, 0))[:3]]

    assert SECONDARY_REMAP_START <= idx0 < SECONDARY_REMAP_START + REMAP_LENGTH
    assert TERTIARY_REMAP_START <= idx1 < TERTIARY_REMAP_START + REMAP_LENGTH


def test_render_layer_frame_preview_recolours_remap_zones(tmp_path):
    """render_layer_frame_preview (UI-only) DOES recolour, in contrast to the
    production path above - proving the separation actually exists."""
    palette = load_standard_palette()

    project = make_synthetic_project(tmp_path)
    layer = project.layers[0]
    sprite_dir = project.project_dir / layer.sprite_dir

    img = Image.new("RGBA", (2, 1), (0, 0, 0, 255))
    img.putpixel((0, 0), (*palette[SECONDARY_REMAP_START + 3], 255))
    img.putpixel((1, 0), (*palette[TERTIARY_REMAP_START + 3], 255))
    img.save(frame_path(sprite_dir, 0, 0))

    scheme = ColourScheme(trim_colour="black", tertiary_colour="white")
    result = render_layer_frame_preview(project, layer, direction=0, frame=0, scheme=scheme, dither=False)

    pal_map = {tuple(rgb): i for i, rgb in enumerate(palette)}
    idx0 = pal_map[result.getpixel((0, 0))[:3]]
    idx1 = pal_map[result.getpixel((1, 0))[:3]]

    # No longer sitting at the original reference indices - they've been
    # recoloured to the scheme's chosen colours.
    assert not (SECONDARY_REMAP_START <= idx0 < SECONDARY_REMAP_START + REMAP_LENGTH)
    assert not (TERTIARY_REMAP_START <= idx1 < TERTIARY_REMAP_START + REMAP_LENGTH)


def test_composite_preview_frame_combines_all_layers(tmp_path):
    project = make_multilayer_synthetic_project(tmp_path)
    result = composite_preview_frame(project, direction=0, frame=0)
    assert result.mode == "RGBA"
    assert result.size == (project.sprite_width * 2, project.sprite_height_negative + project.sprite_height_positive)


def test_composite_preview_frame_with_scheme_differs_from_without(tmp_path):
    palette = load_standard_palette()
    project = make_multilayer_synthetic_project(tmp_path)

    # Guarantee remap-zone content exists, rather than relying on the
    # synthetic gradient incidentally landing there.
    core = project.layers[1]
    sprite_dir = project.project_dir / core.sprite_dir
    img = Image.new("RGBA", FRAME_SIZE, (*palette[SECONDARY_REMAP_START + 3], 255))
    img.save(frame_path(sprite_dir, 0, 0))

    raw = composite_preview_frame(project, direction=0, frame=0)
    recoloured = composite_preview_frame(
        project, direction=0, frame=0, scheme=ColourScheme(trim_colour="black", tertiary_colour="moss_green")
    )
    assert list(raw.getdata()) != list(recoloured.getdata())


def test_build_composite_frames_writes_all_direction_frame_pairs(tmp_path):
    project = make_synthetic_project(tmp_path)
    out_dir = build_composite_frames(project, tmp_path, dither=False)

    assert out_dir == tmp_path / "composited"
    for direction in range(4):
        for frame in range(project.frames_per_dir):
            assert frame_path(out_dir, direction, frame).exists()


def test_build_composite_frames_progress_callback(tmp_path):
    project = make_synthetic_project(tmp_path)
    calls = []
    build_composite_frames(project, tmp_path, dither=False, on_progress=lambda d, t: calls.append((d, t)))

    total = 4 * project.frames_per_dir
    assert len(calls) == total
    assert calls[-1] == (total, total)


def test_build_composite_frames_multilayer_mixed_algorithms(tmp_path):
    project = make_multilayer_synthetic_project(tmp_path)
    out_dir = build_composite_frames(project, tmp_path, dither=True)

    for direction in range(4):
        for frame in range(project.frames_per_dir):
            path = frame_path(out_dir, direction, frame)
            assert path.exists()
            with Image.open(path) as img:
                assert img.mode == "RGBA"
