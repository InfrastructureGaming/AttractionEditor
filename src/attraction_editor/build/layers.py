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
from attraction_editor.build.dither import dither_frame_by_algorithm, snap_to_palette
from attraction_editor.build.zone_mask import read_zone_masks
from attraction_editor.model.project import DIRECTIONS, ColourScheme, Layer, RideProject
from attraction_editor.palette.remap import recolour_dithered_zones, remap_preview
from attraction_editor.sprites.scanner import frame_path, static_frame_path, zone_mask_path

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


def _load_zone_masks(project: RideProject, layer: Layer, direction: int, frame: int):
    """Authored remap-zone masks for this (direction, frame), or None when the
    layer has no zone pass (or the frame's EXR is absent) - in which case the
    build falls back to the distance/catch-tolerance classification. Static
    layers reuse frame 0, mirroring _load_layer_source."""
    if not layer.zone_pass_dir or project.project_dir is None:
        return None
    zone_frame = 0 if layer.kind == "static" else frame
    path = zone_mask_path(project.project_dir / layer.zone_pass_dir, direction, zone_frame)
    if not path.exists():
        return None
    return read_zone_masks(path)


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
            zone_masks=_load_zone_masks(project, layer, direction, frame),
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
    trim/tertiary colours so the UI can show what a given colour scheme
    would look like. Never used by the real build path - the result of
    this is never written to disk as a shipped sprite.

    When `dither` is True, this dithers *first* - rendering through the
    exact same render_layer_frame path the real build uses (raw reference
    shades, zone-constrained quantisation) - then recolours the result by
    direct index lookup (recolour_dithered_zones), instead of recolouring
    first and dithering after. This mirrors what the engine itself does at
    runtime: it recolours an already-dithered shipped sprite by index, it
    never dithers a recoloured one. Recolouring first would collapse the
    zone's natural EEVEE gradient into flat per-shade bands before
    dithering had anything left to diffuse error across, which made this
    preview's dithering visibly less detailed than what actually ships -
    confirmed directly: the same frame had 51 distinct colours rendered the
    real way vs only 32 recolour-first.

    When `dither` is False (the fast, responsive preview), there's no
    quantised index yet to look up - the source is still smooth, unquantised
    EEVEE colour - so this still uses remap_preview's distance-based
    classification, with project's catch tolerances applied exactly as the
    real build would catch them.
    """
    is_static = layer.kind == "static"
    cache_key = (layer.sprite_dir, direction, scheme.trim_colour, scheme.tertiary_colour, dither) if is_static else None
    if cache is not None and cache_key is not None and cache_key in cache:
        return cache[cache_key]

    if dither:
        dithered = render_layer_frame(project, layer, direction, frame, dither=True, cache=cache)
        result = recolour_dithered_zones(dithered, scheme.trim_colour, scheme.tertiary_colour)
    else:
        img = _load_layer_source(project, layer, direction, frame)
        result = remap_preview(
            img,
            scheme.trim_colour,
            scheme.tertiary_colour,
            trim_tolerance=project.trim_catch_tolerance,
            tertiary_tolerance=project.tertiary_catch_tolerance,
        )

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
    (default), renders the raw structure exactly as it will actually ship.

    When `dither` is True, the composite is also snapped back onto the
    StandardPalette after layers are merged (see dither.py's
    snap_to_palette) - alpha-compositing partially-transparent layers
    (anti-aliased edges, soft shadows) blends RGB values away from the
    exact palette colours each layer was individually dithered to, which
    openrct2-cli's own (non-dithered) -m closest pass would otherwise
    re-quantise uncontrollably at build time. Skipped when dither is False,
    consistent with that mode already skipping all per-layer palette
    consideration too (fast, responsive, deliberately not paletted)."""
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
    composite = composite_layer_stack(layer_images)
    return snap_to_palette(composite) if dither else composite


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

    When `dither` is True (the default - this is the real build path), each
    composite is snapped back onto the StandardPalette after layers are
    merged (see dither.py's snap_to_palette) for the same reason
    composite_preview_frame does: alpha-compositing partially-transparent
    layers blends RGB away from the exact palette colours each layer was
    individually dithered to, which openrct2-cli's own (non-dithered)
    -m closest pass would otherwise re-quantise uncontrollably, undoing the
    careful per-layer dithering with banding at every layer seam.
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
            if dither:
                composite = snap_to_palette(composite)
            composite.save(frame_path(out_dir, direction, frame))

            done += 1
            if on_progress is not None:
                on_progress(done, total)

    return out_dir
