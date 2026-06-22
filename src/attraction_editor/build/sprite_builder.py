"""Wraps `openrct2-cli sprite build` to turn a RideProject's layer stack +
car overlays into images.dat, with sanity checks ported from
feedback_sprite_packaging.md."""

from __future__ import annotations

import json
import re
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from attraction_editor.build.layers import build_composite_frames
from attraction_editor.model.project import DIRECTIONS, RideProject
from attraction_editor.sprites.manifest import THUMBNAIL_COUNT, build_manifest, manifest_image_count

MANIFEST_FILENAME = "sprite_manifest.json"
IMAGES_DAT_FILENAME = "images.dat"

# Below this many bytes per image, images.dat almost certainly contains
# all-transparent sprites (e.g. a Blender export that didn't match the
# palette and was built without `-m closest`).
MIN_BYTES_PER_IMAGE = 256

_FINISHED_RE = re.compile(r"Finished building graphics repository with (\d+) images")


class SpriteBuildError(RuntimeError):
    pass


@dataclass
class SpriteBuildResult:
    image_count: int
    total_data_size: int
    manifest_path: Path
    images_dat_path: Path


def write_manifest(project: RideProject) -> Path:
    """Regenerate the persisted, documentary sprite_manifest.json from
    `project` and return its path. Points the structure section at the
    first layer's raw source directory - this file is informational only;
    a real build always re-composites every layer into a temp directory
    that's cleaned up once the build finishes, so this can't (and isn't
    meant to) reflect the literal build inputs of a dithered build."""
    if project.project_dir is None:
        raise ValueError("RideProject.project_dir is not set")

    structure_frame_dir = project.project_dir / project.layers[0].sprite_dir
    manifest_path = project.project_dir / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(build_manifest(project, structure_frame_dir), indent=4), encoding="utf-8"
    )
    return manifest_path


def read_images_dat_header(images_dat_path: Path) -> tuple[int, int]:
    """Return (numEntries, totalDataSize) from images.dat's 8-byte header."""
    with images_dat_path.open("rb") as f:
        header = f.read(8)
    if len(header) != 8:
        raise SpriteBuildError(f"{images_dat_path} is too small to be a valid images.dat")
    return struct.unpack("<II", header)


def build_images_dat(
    project: RideProject,
    *,
    dither: bool = True,
    on_progress: Callable[[int, int], None] | None = None,
) -> SpriteBuildResult:
    """Composite every structure layer (optionally dithered per its own
    algorithm/strength - see model.project.Layer), then run
    `openrct2-cli sprite build images.dat sprite_manifest.json -m closest`
    and sanity-check the result.

    Compositing always happens, dithered or not - once there's more than one
    raw layer, something has to flatten them into one image before the CLI
    can build images.dat. `dither=True` (default) applies each layer's
    configured dithering before compositing; `dither=False` composites the
    raw remapped layers untouched, for a quick test build.

    `on_progress(done, total)` is called after each composited frame is
    written, so callers can report progress during large builds.

    Raises SpriteBuildError if the CLI fails, the reported image count
    doesn't match the manifest, or images.dat looks too small to contain
    real (non-blank) sprite data.
    """
    if project.project_dir is None:
        raise ValueError("RideProject.project_dir is not set")
    if not project.openrct2_cli_path:
        raise ValueError("RideProject.openrct2_cli_path is not set")

    images_dat_path = project.project_dir / IMAGES_DAT_FILENAME

    # Create tmp_dir INSIDE project_dir so the CLI can reach both the
    # composited structure files and the original car files via relative
    # paths. The CLI always resolves manifest paths relative to the manifest
    # file, so absolute paths don't work; ../car_path steps back up one level.
    with tempfile.TemporaryDirectory(dir=project.project_dir) as tmp_dir:
        tmp_dir_path = Path(tmp_dir)

        structure_dir = build_composite_frames(project, tmp_dir_path, dither=dither, on_progress=on_progress)
        manifest_entries = build_manifest(project, structure_dir)

        # Split at the structure/car boundary — riders are never dithered or composited.
        structure_count = THUMBNAIL_COUNT + DIRECTIONS * project.frames_per_dir
        structure_entries = manifest_entries[:structure_count]
        car_entries = manifest_entries[structure_count:]

        # Structure paths: relative to tmp_dir (composited files live there).
        rel_structure = []
        for entry in structure_entries:
            e = dict(entry)
            e["path"] = str(Path(entry["path"]).relative_to(tmp_dir_path)).replace("\\", "/")
            rel_structure.append(e)

        # Car paths: one level up from tmp_dir lands in project_dir where
        # the original car frames live.
        rel_car = []
        for entry in car_entries:
            e = dict(entry)
            e["path"] = "../" + entry["path"]
            rel_car.append(e)

        tmp_manifest = tmp_dir_path / MANIFEST_FILENAME
        tmp_manifest.write_text(json.dumps(rel_structure + rel_car, indent=4), encoding="utf-8")

        result = subprocess.run(
            [str(project.openrct2_cli_path), "sprite", "build",
             str(images_dat_path), str(tmp_manifest), "-m", "closest"],
            cwd=tmp_dir_path,
            capture_output=True,
            text=True,
        )

    manifest_path = write_manifest(project)  # documentary, written after tmp cleanup

    if result.returncode != 0:
        raise SpriteBuildError(
            f"openrct2-cli sprite build failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        )

    match = _FINISHED_RE.search(result.stdout)
    if not match:
        raise SpriteBuildError(f"Could not parse image count from openrct2-cli output:\n{result.stdout}")
    image_count = int(match.group(1))

    expected = manifest_image_count(project)
    if image_count != expected:
        raise SpriteBuildError(f"images.dat has {image_count} images, expected {expected} from the manifest")

    _num_entries, total_data_size = read_images_dat_header(images_dat_path)
    min_size = MIN_BYTES_PER_IMAGE * image_count
    if total_data_size < min_size:
        raise SpriteBuildError(
            f"images.dat totalDataSize is {total_data_size} bytes for {image_count} images "
            f"(< {min_size} bytes minimum) - sprites likely rendered blank. "
            "Was the source PNG built with `-m closest`?"
        )

    return SpriteBuildResult(
        image_count=image_count,
        total_data_size=total_data_size,
        manifest_path=manifest_path,
        images_dat_path=images_dat_path,
    )
