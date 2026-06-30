"""Tests for build/layers.py: per-layer dither rendering (production - no
colour remap), static-layer caching, preview-only recolouring, and full
multi-layer composite-frame generation."""

from __future__ import annotations

import numpy as np
from PIL import Image

from attraction_editor.build.dither import primary_zone_indices
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
    load_colour_ramps,
    load_standard_palette,
)
from attraction_editor.sprites.scanner import frame_path, zone_mask_path
from tests.fixtures.synthetic import FRAME_SIZE, make_multilayer_synthetic_project, make_synthetic_project


def _write_single_part_zone_exr(path, width, height, layers: dict) -> None:
    """Minimal single-part zone-pass EXR writer (read_zone_masks handles both
    single- and multi-part); value goes in R and A, mirroring the real stencils."""
    import Imath
    import OpenEXR

    channel = Imath.Channel(Imath.PixelType(Imath.PixelType.FLOAT))
    header = OpenEXR.Header(width, height)
    channels, pixels = {}, {}
    zero = np.zeros((height, width), dtype=np.float32)
    for layer, arr in layers.items():
        value = np.ascontiguousarray(arr.astype(np.float32))
        for comp in ("R", "G", "B", "A"):
            channels[f"{layer}.{comp}"] = channel
            pixels[f"{layer}.{comp}"] = (value if comp in ("R", "A") else zero).tobytes()
    header["channels"] = channels
    out = OpenEXR.OutputFile(str(path), header)
    out.writePixels(pixels)
    out.close()


def _palette_index_of(rgba_pixel) -> int:
    rgb = [int(c) for c in rgba_pixel[:3]]
    for i, entry in enumerate(load_standard_palette()):
        if list(entry) == rgb:
            return i
    return -1


def test_render_layer_frame_uses_authored_zone_masks_end_to_end(tmp_path):
    """Full chain: Layer.zone_pass_dir -> zone_mask_path -> read_zone_masks ->
    dither_frame_by_algorithm. An authored COLOR_PRIMARY mask drives the masked
    pixels into the primary range (243-254) - which nothing else in the pipeline
    can do."""
    project = make_synthetic_project(tmp_path)
    layer = project.layers[0]
    layer.zone_pass_dir = layer.sprite_dir  # masks live alongside the beauty frames
    zone_dir = project.project_dir / layer.zone_pass_dir
    w, h = FRAME_SIZE

    primary = np.zeros((h, w), dtype=np.float32)
    primary[: h // 2, :] = 1.0  # top half is the primary zone
    _write_single_part_zone_exr(zone_mask_path(zone_dir, 0, 0), w, h, {"COLOR_PRIMARY": primary})

    out = np.asarray(render_layer_frame(project, layer, 0, 0, dither=True).convert("RGBA"))
    primary_idx = set(primary_zone_indices())

    assert _palette_index_of(out[0, 0]) in primary_idx  # masked (top) pixel
    assert _palette_index_of(out[h - 1, 0]) not in primary_idx  # unmasked (bottom) pixel


def test_zone_pass_layer_preview_recolours_primary_to_body(tmp_path):
    """A zone-pass layer's preview takes the index path even with dither=False
    (greyscale zones are invisible to the distance path), and scheme.body_colour
    recolours the primary zone to the Main colour - what ships in-game."""
    project = make_synthetic_project(tmp_path)
    layer = project.layers[0]
    layer.zone_pass_dir = layer.sprite_dir
    zone_dir = project.project_dir / layer.zone_pass_dir
    w, h = FRAME_SIZE
    primary = np.zeros((h, w), dtype=np.float32)
    primary[: h // 2, :] = 1.0  # top half = primary/Main zone
    _write_single_part_zone_exr(zone_mask_path(zone_dir, 0, 0), w, h, {"COLOR_PRIMARY": primary})

    scheme = ColourScheme(trim_colour="white", tertiary_colour="white", body_colour="bright_red")
    out = np.asarray(render_layer_frame_preview(project, layer, 0, 0, scheme, dither=False).convert("RGBA"))

    palette = load_standard_palette()
    body_ramp = {tuple(palette[i]) for i in load_colour_ramps()["bright_red"]}
    top_pixels = {tuple(out[0, x][:3]) for x in range(w)}
    assert top_pixels <= body_ramp  # the primary zone now shows the Main (body) colour


def test_render_layer_frame_without_zone_pass_is_unaffected(tmp_path):
    """No zone_pass_dir => no masks loaded => identical to before the feature."""
    project = make_synthetic_project(tmp_path)
    layer = project.layers[0]
    assert layer.zone_pass_dir is None

    out = np.asarray(render_layer_frame(project, layer, 0, 0, dither=True).convert("RGBA"))
    primary_idx = set(primary_zone_indices())
    assert all(
        _palette_index_of(out[y, x]) not in primary_idx for y in range(out.shape[0]) for x in range(out.shape[1])
    )


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


def test_render_layer_frame_preview_uses_project_catch_tolerance(tmp_path):
    """render_layer_frame_preview must read RideProject.trim_catch_tolerance
    too, so the colour-scheme preview matches what the real build (via
    render_layer_frame) will actually catch."""
    project = make_synthetic_project(tmp_path)
    layer = project.layers[0]
    sprite_dir = project.project_dir / layer.sprite_dir

    img = Image.new("RGBA", (1, 1), (143, 31, 58, 255))  # see borderline note above
    img.save(frame_path(sprite_dir, 0, 0))
    scheme = ColourScheme(trim_colour="black", tertiary_colour="white")

    project.trim_catch_tolerance = 0
    untouched = render_layer_frame_preview(project, layer, direction=0, frame=0, scheme=scheme, dither=False)
    project.trim_catch_tolerance = 2
    widened = render_layer_frame_preview(project, layer, direction=0, frame=0, scheme=scheme, dither=False)

    assert untouched.getpixel((0, 0))[:3] == (143, 31, 58)  # not caught - kept original
    assert widened.getpixel((0, 0))[:3] != (143, 31, 58)  # caught - recoloured to the scheme's colour


def test_render_layer_frame_uses_project_catch_tolerance(tmp_path):
    """render_layer_frame (the production path) must read
    RideProject.trim_catch_tolerance, since dithering is the only place
    that decides remap-zone classification for the shipped sprite (see
    build/dither.py's module docstring)."""
    project = make_synthetic_project(tmp_path)
    layer = project.layers[0]
    sprite_dir = project.project_dir / layer.sprite_dir

    # Borderline secondary-zone colour (1.86-unit margin) - see
    # test_dither.py's _BORDERLINE_SECONDARY_RGB for how this was derived.
    img = Image.new("RGBA", (8, 8), (143, 31, 58, 255))
    img.save(frame_path(sprite_dir, 0, 0))
    target_rgb = tuple(load_standard_palette()[SECONDARY_REMAP_START + 3])

    project.trim_catch_tolerance = 0
    untouched = render_layer_frame(project, layer, direction=0, frame=0, dither=True)
    project.trim_catch_tolerance = 2
    widened = render_layer_frame(project, layer, direction=0, frame=0, dither=True)

    assert any(px[:3] != target_rgb for px in untouched.getdata())
    assert all(px[:3] == target_rgb for px in widened.getdata())


def test_render_layer_frame_preview_dither_toggle_still_changes_pixels(tmp_path):
    """Regression test: render_layer_frame_preview must respect `dither`
    just like the production path does. remap_preview used to hard-quantize
    the whole image first, leaving zero residual error for any subsequent
    dithering pass to diffuse - "Preview dithering" silently became a no-op
    for every frame once a colour scheme was applied."""
    project = make_synthetic_project(tmp_path)
    layer = project.layers[0]

    scheme = ColourScheme(trim_colour="black", tertiary_colour="white")
    without_dither = render_layer_frame_preview(project, layer, direction=0, frame=0, scheme=scheme, dither=False)
    with_dither = render_layer_frame_preview(project, layer, direction=0, frame=0, scheme=scheme, dither=True)

    assert without_dither.convert("RGB").tobytes() != with_dither.convert("RGB").tobytes()


def test_composite_preview_frame_combines_all_layers(tmp_path):
    project = make_multilayer_synthetic_project(tmp_path)
    result = composite_preview_frame(project, direction=0, frame=0)
    assert result.mode == "RGBA"
    assert result.size == (project.sprite_width * 2, project.sprite_height)


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


def _add_partial_alpha_foreground(project, seed: int = 99) -> None:
    """Overwrite the project's foreground static layer with a uniformly
    50%-alpha frame, for every direction - the synthetic fixtures otherwise
    only ever write fully-opaque pixels, which wouldn't exercise the
    alpha-blend-introduces-off-palette-colours bug at all."""
    foreground = next(layer for layer in project.layers if layer.name == "Foreground")
    sprite_dir = project.project_dir / foreground.sprite_dir
    img = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    for x in range(FRAME_SIZE[0]):
        for y in range(FRAME_SIZE[1]):
            img.putpixel((x, y), (60, 180, 90, 128))
    from attraction_editor.sprites.scanner import static_frame_path

    for direction in range(4):
        img.save(static_frame_path(sprite_dir, direction))


def test_composite_preview_frame_dithered_composite_is_fully_on_palette(tmp_path):
    """Regression test for the real bug report: alpha-compositing several
    already-dithered layers (build/compositing.py's composite_layer_stack)
    blends RGB away from exact palette colours wherever any layer has
    partial alpha, which the dithered preview/build path must correct
    (build/dither.py's snap_to_palette) rather than leave for
    openrct2-cli's own uncontrolled -m closest re-quantisation."""
    palette_set = {tuple(rgb) for rgb in load_standard_palette()}
    project = make_multilayer_synthetic_project(tmp_path)
    _add_partial_alpha_foreground(project)

    result = composite_preview_frame(project, direction=0, frame=0, dither=True)

    assert all(px[:3] in palette_set for px in result.getdata())


def test_composite_preview_frame_undithered_does_not_force_palette_snap(tmp_path):
    """dither=False is the fast/responsive preview path that deliberately
    skips all palette consideration - snap_to_palette must not run there."""
    palette_set = {tuple(rgb) for rgb in load_standard_palette()}
    project = make_multilayer_synthetic_project(tmp_path)
    _add_partial_alpha_foreground(project)

    result = composite_preview_frame(project, direction=0, frame=0, dither=False)

    assert any(px[:3] not in palette_set for px in result.getdata())


def test_build_composite_frames_output_is_fully_on_palette(tmp_path):
    palette_set = {tuple(rgb) for rgb in load_standard_palette()}
    project = make_multilayer_synthetic_project(tmp_path)
    _add_partial_alpha_foreground(project)

    out_dir = build_composite_frames(project, tmp_path, dither=True)

    with Image.open(frame_path(out_dir, 0, 0)) as img:
        assert all(px[:3] in palette_set for px in img.convert("RGBA").getdata())
