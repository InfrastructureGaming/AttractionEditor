"""Wraps `openrct2-cli sprite build` to turn a RideProject's layer stack +
car overlays into images.dat, with sanity checks ported from
feedback_sprite_packaging.md."""

from __future__ import annotations

import json
import os
import re
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from attraction_editor.build.layers import build_composite_frames
from attraction_editor.build.thumbnail import THUMBNAIL_FILENAME, render_thumbnail
from attraction_editor.model.project import DIRECTIONS, RideProject
from attraction_editor.sprites.manifest import THUMBNAIL_COUNT, build_manifest, manifest_image_count
from attraction_editor.sprites.scanner import frame_path

MANIFEST_FILENAME = "sprite_manifest.json"
IMAGES_DAT_FILENAME = "images.dat"

# Below this many bytes per image, images.dat almost certainly contains
# all-transparent sprites (e.g. a Blender export that didn't match the
# palette and was built without `-m closest`).
MIN_BYTES_PER_IMAGE = 256

_FINISHED_RE = re.compile(r"Finished building graphics repository with (\d+) images")


class SpriteBuildError(RuntimeError):
    pass


class BuildAborted(Exception):
    """Raised when a build is cancelled by the user (see build_images_dat's
    should_cancel and ui/build_panel.py's Abort button). Distinct from
    SpriteBuildError so callers can tell a deliberate abort from a real
    failure and report it differently."""


def _run_cancellable(
    cmd: list[str],
    *,
    cwd: Path,
    should_cancel: Callable[[], bool] | None = None,
    poll_interval: float = 0.2,
) -> subprocess.CompletedProcess:
    """Like subprocess.run(cmd, cwd=cwd, capture_output=True, text=True), but
    polls `should_cancel` every `poll_interval` seconds while the process runs
    and terminates it (raising BuildAborted) if it returns True - openrct2-cli's
    sprite build for a large ride can run for a while, so it must be stoppable
    mid-run, not just at Python step boundaries.

    communicate() (not poll()) is what drains the stdout/stderr pipes, so
    looping on its timeout both waits for the process and keeps the pipes from
    filling and deadlocking a chatty CLI. The finally clause guarantees the
    child is killed and reaped on every exit path (including the abort raise),
    with bounded waits throughout so a wind-down can never block forever."""
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=poll_interval)
                return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                # Still running - check for an abort request, then keep draining.
                if should_cancel is not None and should_cancel():
                    raise BuildAborted("Build aborted during image build")
    finally:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                pass


def _car_manifest_path(raw_path: str, project_dir: Path, tmp_dir_path: Path) -> str:
    """Return `raw_path` (a car's frame file, normally project_dir-relative -
    see model.project.CarConfig - but possibly absolute: legacy project data,
    or a sprite folder picked from outside project_dir) re-expressed relative
    to `tmp_dir_path`, the manifest's own directory.

    openrct2-cli resolves every manifest path by joining it directly onto the
    manifest file's directory as plain strings - it has no concept of an
    absolute path overriding that join, so handing it an absolute path
    doesn't make the CLI use it directly, it gets concatenated onto
    tmp_dir_path just like anything else, producing a bogus nested path that
    fails with "libpng error: Not a PNG file" - this was a real, confirmed
    build failure, not a hypothetical. The only thing that reliably works
    regardless of how `raw_path` was originally stored is computing the
    actual relative path from tmp_dir_path to the real file location."""
    absolute = project_dir / raw_path  # a no-op when raw_path is already absolute - pathlib's `/` drops the LHS
    return os.path.relpath(absolute, tmp_dir_path).replace("\\", "/")


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
    should_cancel: Callable[[], bool] | None = None,
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

    `should_cancel()`, if given, is polled before the CLI launches and while
    it runs; returning True raises BuildAborted (the compositing phase is
    cancelled separately, by raising from on_progress - see ui/build_panel.py).

    Raises SpriteBuildError if the CLI fails, the reported image count
    doesn't match the manifest, or images.dat looks too small to contain
    real (non-blank) sprite data. Raises BuildAborted if should_cancel fires.
    """
    if project.project_dir is None:
        raise ValueError("RideProject.project_dir is not set")
    if not project.openrct2_cli_path:
        raise ValueError("RideProject.openrct2_cli_path is not set")

    images_dat_path = project.project_dir / IMAGES_DAT_FILENAME

    # Create tmp_dir INSIDE project_dir so the CLI can reach both the
    # composited structure files and the original car files via relative
    # paths. The CLI always resolves manifest paths by joining them onto the
    # manifest file's own directory as plain strings - an absolute path in
    # the manifest doesn't override that join, it just gets concatenated
    # onto it - so every path written into the manifest, car or structure,
    # must actually be relative to tmp_dir_path (see _car_manifest_path).
    with tempfile.TemporaryDirectory(dir=project.project_dir) as tmp_dir:
        tmp_dir_path = Path(tmp_dir)

        structure_dir = build_composite_frames(project, tmp_dir_path, dither=dither, on_progress=on_progress)

        # Render the New Ride preview thumbnail: the author's image if set,
        # otherwise composited structure frame 0 (dir 0). Either way it's
        # fitted to 112x112 and built "raw" (see manifest/thumbnail), so the
        # ride-picker preview renders correctly even for thumbnail-less projects.
        thumb_source = (
            project.project_dir / project.thumbnail_path
            if project.thumbnail_path
            else frame_path(structure_dir, 0, 0)
        )
        thumb_file = render_thumbnail(thumb_source, tmp_dir_path / THUMBNAIL_FILENAME)
        manifest_entries = build_manifest(project, structure_dir, thumbnail_path=thumb_file)

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

        # Car paths: re-expressed relative to tmp_dir, wherever the original
        # car frames actually live (normally one level up, in project_dir).
        rel_car = []
        for entry in car_entries:
            e = dict(entry)
            e["path"] = _car_manifest_path(entry["path"], project.project_dir, tmp_dir_path)
            rel_car.append(e)

        tmp_manifest = tmp_dir_path / MANIFEST_FILENAME
        tmp_manifest.write_text(json.dumps(rel_structure + rel_car, indent=4), encoding="utf-8")

        # Bail before launching the CLI if the user aborted during compositing,
        # then poll for abort throughout the (potentially long) CLI run itself.
        if should_cancel is not None and should_cancel():
            raise BuildAborted("Build aborted before image build")
        result = _run_cancellable(
            [str(project.openrct2_cli_path), "sprite", "build",
             str(images_dat_path), str(tmp_manifest), "-m", "closest"],
            cwd=tmp_dir_path,
            should_cancel=should_cancel,
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
