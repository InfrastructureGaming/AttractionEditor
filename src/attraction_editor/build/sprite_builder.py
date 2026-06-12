"""Wraps `openrct2-cli sprite build` to turn a RideProject's frame folders into
images.dat, with sanity checks ported from feedback_sprite_packaging.md."""

from __future__ import annotations

import json
import re
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

from attraction_editor.model.project import RideProject
from attraction_editor.sprites.manifest import build_manifest, manifest_image_count

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
    """Regenerate sprite_manifest.json from `project` (overwriting any
    existing file) and return its path."""
    if project.project_dir is None:
        raise ValueError("RideProject.project_dir is not set")

    manifest_path = project.project_dir / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(build_manifest(project), indent=4), encoding="utf-8")
    return manifest_path


def read_images_dat_header(images_dat_path: Path) -> tuple[int, int]:
    """Return (numEntries, totalDataSize) from images.dat's 8-byte header."""
    with images_dat_path.open("rb") as f:
        header = f.read(8)
    if len(header) != 8:
        raise SpriteBuildError(f"{images_dat_path} is too small to be a valid images.dat")
    return struct.unpack("<II", header)


def build_images_dat(project: RideProject) -> SpriteBuildResult:
    """Regenerate sprite_manifest.json, then run
    `openrct2-cli sprite build images.dat sprite_manifest.json -m closest`
    in project_dir and sanity-check the result.

    Raises SpriteBuildError if the CLI fails, the reported image count
    doesn't match the manifest, or images.dat looks too small to contain
    real (non-blank) sprite data.
    """
    if project.project_dir is None:
        raise ValueError("RideProject.project_dir is not set")
    if not project.openrct2_cli_path:
        raise ValueError("RideProject.openrct2_cli_path is not set")

    manifest_path = write_manifest(project)
    images_dat_path = project.project_dir / IMAGES_DAT_FILENAME

    result = subprocess.run(
        [str(project.openrct2_cli_path), "sprite", "build", str(images_dat_path), str(manifest_path), "-m", "closest"],
        cwd=project.project_dir,
        capture_output=True,
        text=True,
    )
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
