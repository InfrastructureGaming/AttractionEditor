"""Per-layer rendering (dither) and composite-frame generation for a
RideProject's structure layers (see model.project.Layer). This is the
project-aware orchestration that sits between the pure pixel ops in
build.dither/build.compositing and the filesystem/manifest layer in
build.sprite_builder - and is also what UI preview panels call directly
(composite_preview_frame) for an in-memory, no-disk-writes look at the result.

render_layer_frame (the production path, used by build_composite_frames) does
NOT apply any colour remap - the artist's render is dithered as-is. Baking a
specific colour in at build time would erase the secondary/tertiary palette
zone pixels the engine needs to recolour the ride live at render time (see
palette/remap.py's module docstring for the full explanation). Colour
remapping only ever happens in render_layer_frame_preview, for UI preview."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image

from attraction_editor.build.compositing import composite_layer_stack
from attraction_editor.build.dither import dither_frame_by_algorithm
from attraction_editor.model.project import DIRECTIONS, ColourScheme, Layer, RideProject
from attraction_editor.palette.remap import remap_preview
from attraction_editor.sprites.scanner import frame_path, static_frame_path

# Cache key: (layer.sprite_dir, direction). Only meaningful for static layers,
# since there are only DIRECTIONS possible inputs total regardless of frame.
_RenderCache = dict[tuple[str, int], Image.Image]


def _load_layer_source(project: RideProject, layer: Layer, direction: int, frame: int) -> Image.Image:
    if project.project_dir is None:
        raise ValueError("RideProject.project_dir is not set")
    sprite_dir = project.project_dir / layer.sprite_dir
    is_static = layer.kind == "static"
    src_path = static_frame_path(sprite_dir, direction) if is_static else frame_path(sprite_dir, direction, frame)
    with Image.open(src_path) as img:
        return img.copy()


def render_layer_frame(
    project: RideProject,
    layer: Layer,
    direction: int,
    frame: int,
    *,
    dither: bool,
    cache: _RenderCache | None = None,
) -> Image.Image:
    """Render one layer's contribution to (direction, frame) for the real
    build: load the source PNG and dither per the layer's own algorithm/
    strength if `dither` is True. No colour remap - this is what ships.

    `frame` is ignored for static layers - there's only one frame per
    direction. If `cache` is supplied, a static layer's result is computed
    once per direction and reused for every subsequent call with the same
    (layer.sprite_dir, direction), since the dither work is otherwise
    identical across every frame request.
    """
    is_static = layer.kind == "static"
    cache_key = (layer.sprite_dir, direction) if is_static else None
    if cache is not None and cache_key is not None and cache_key in cache:
        return cache[cache_key]

    img = _load_layer_source(project, layer, direction, frame)
    result = (
        dither_frame_by_algorithm(
            img,
            layer.dither_algorithm,
            strength=layer.dither_strength,
            trim_tolerance=project.trim_catch_tolerance,
            tertiary_tolerance=project.tertiary_catch_tolerance,
        )
        if dither
        else img.convert("RGBA")
    )

    if cache is not None and cache_key is not None:
        cache[cache_key] = result
    return result


def render_layer_frame_preview(
    project: RideProject,
    layer: Layer,
    direction: int,
    frame: int,
    scheme: ColourScheme,
    *,
    dither: bool = False,
    cache: _RenderCache | None = None,
) -> Image.Image:
    """Preview-only: like render_layer_frame, but applies `scheme`'s
    trim/tertiary colours via remap_preview before dithering, so the UI can
    show what a given default colour scheme would look like. Never used by
    the real build path - the result of this is never written to disk as a
    shipped sprite.

    remap_preview already classifies pixels using project's catch tolerances
    (so this preview matches what the real build will catch); the
    dithering step that follows is passed tolerance=0 (its default) since
    there's nothing left for it to (re)classify - every pixel remap_preview
    decided to catch has already been recoloured to the scheme's colour,
    not the raw reference shade dither_frame_by_algorithm's bias looks for.
    """
    is_static = layer.kind == "static"
    cache_key = (layer.sprite_dir, direction, scheme.trim_colour, scheme.tertiary_colour) if is_static else None
    if cache is not None and cache_key is not None and cache_key in cache:
        return cache[cache_key]

    img = _load_layer_source(project, layer, direction, frame)
    remapped = remap_preview(
        img,
        scheme.trim_colour,
        scheme.tertiary_colour,
        trim_tolerance=project.trim_catch_tolerance,
        tertiary_tolerance=project.tertiary_catch_tolerance,
    )
    result = dither_frame_by_algorithm(remapped, layer.dither_algorithm, strength=layer.dither_strength) if dither else remapped

    if cache is not None and cache_key is not None:
        cache[cache_key] = result
    return result


def composite_preview_frame(
    project: RideProject,
    direction: int,
    frame: int = 0,
    *,
    dither: bool = False,
    scheme: ColourScheme | None = None,
) -> Image.Image:
    """In-memory composite of every structure layer at (direction, frame), for
    UI preview panels - no disk writes. `dither` defaults to False for a fast,
    responsive preview; pass True (e.g. in an animation player) to actually
    see what a layer's chosen dithering algorithm will look like in motion.

    `scheme`, if given, renders with that colour scheme's preview recolour
    applied (cosmetic only - see render_layer_frame_preview). If None
    (default), renders the raw structure exactly as it will actually ship."""
    cache: _RenderCache = {}
    if scheme is None:
        layer_images = [
            render_layer_frame(project, layer, direction, frame, dither=dither, cache=cache) for layer in project.layers
        ]
    else:
        layer_images = [
            render_layer_frame_preview(project, layer, direction, frame, scheme, dither=dither, cache=cache)
            for layer in project.layers
        ]
    return composite_layer_stack(layer_images)


def build_composite_frames(
    project: RideProject,
    tmp_dir: Path,
    *,
    dither: bool = True,
    on_progress: Callable[[int, int], None] | None = None,
) -> Path:
    """Render and composite every (direction, frame) pair for `project`,
    writing the flattened results to tmp_dir/composited/dir{d}_f{f:04d}.png.
    Returns that directory. `on_progress(done, total)` fires after each
    composited frame is written.
    """
    out_dir = tmp_dir / "composited"
    out_dir.mkdir(parents=True, exist_ok=True)

    cache: _RenderCache = {}
    total = DIRECTIONS * project.frames_per_dir
    done = 0

    for direction in range(DIRECTIONS):
        for frame in range(project.frames_per_dir):
            layer_images = [
                render_layer_frame(project, layer, direction, frame, dither=dither, cache=cache)
                for layer in project.layers
            ]
            composite = composite_layer_stack(layer_images)
            composite.save(frame_path(out_dir, direction, frame))

            done += 1
            if on_progress is not None:
                on_progress(done, total)

    return out_dir
