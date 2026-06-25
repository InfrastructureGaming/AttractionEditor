"""Tests for build/sprite_builder.py: manifest regeneration, images.dat header
parsing, and an end-to-end build against the real openrct2-cli using a small
synthetic project."""

from __future__ import annotations

import json
import struct

import pytest

from attraction_editor.build.sprite_builder import (
    SpriteBuildError,
    _car_manifest_path,
    build_images_dat,
    read_images_dat_header,
    write_manifest,
)
from attraction_editor.sprites.manifest import build_manifest, manifest_image_count
from tests.fixtures.synthetic import OPENRCT2_CLI_PATH, make_synthetic_project


def test_car_manifest_path_relative_path_steps_up_to_project_dir(tmp_path):
    project_dir = tmp_path
    tmp_dir_path = project_dir / "tmpXXXXXX"

    result = _car_manifest_path("Frames/Riders/Car0/dir0_f0000.png", project_dir, tmp_dir_path)

    assert result == "../Frames/Riders/Car0/dir0_f0000.png"


def test_car_manifest_path_absolute_path_resolves_the_same_as_relative(tmp_path):
    """Regression test: an absolute car sprite_dir used to get "../" blindly
    prepended (the original code did `"../" + entry["path"]` unconditionally),
    producing a bogus path like ".../ProjectDir/G:/elsewhere/..." that
    openrct2-cli read as a literal subfolder named "G:", not a drive.

    The next attempt skipped the "../" prefix for absolute paths instead -
    but openrct2-cli doesn't special-case absolute paths at all, it joins
    every manifest path onto the manifest's own directory as a plain string
    regardless, so an unprefixed absolute path got joined onto tmp_dir_path
    too, producing the same doubled-path failure with tmp_dir_path now
    inserted in the middle. The only fix that actually works regardless of
    how sprite_dir was stored is computing the real relative path from
    tmp_dir_path - which must come out identical whether sprite_dir was
    given as absolute or as project-relative."""
    project_dir = tmp_path
    tmp_dir_path = project_dir / "tmpXXXXXX"
    absolute = str(project_dir / "Frames" / "Riders" / "Car0" / "dir0_f0000.png")

    result = _car_manifest_path(absolute, project_dir, tmp_dir_path)

    assert result == "../Frames/Riders/Car0/dir0_f0000.png"
    assert not result.startswith(str(project_dir))


def test_write_manifest(tmp_path):
    project = make_synthetic_project(tmp_path)

    manifest_path = write_manifest(project)

    assert manifest_path == tmp_path / "sprite_manifest.json"
    written = json.loads(manifest_path.read_text(encoding="utf-8"))
    structure_frame_dir = project.project_dir / project.layers[0].sprite_dir
    assert written == build_manifest(project, structure_frame_dir)


def test_read_images_dat_header(tmp_path):
    images_dat = tmp_path / "images.dat"
    images_dat.write_bytes(struct.pack("<II", 11, 56760) + b"\x00" * 16)

    num_entries, total_data_size = read_images_dat_header(images_dat)

    assert num_entries == 11
    assert total_data_size == 56760


def test_read_images_dat_header_too_small(tmp_path):
    images_dat = tmp_path / "images.dat"
    images_dat.write_bytes(b"\x00\x00\x00")

    with pytest.raises(SpriteBuildError):
        read_images_dat_header(images_dat)


@pytest.mark.skipif(not OPENRCT2_CLI_PATH.exists(), reason="openrct2-cli.exe not available")
def test_build_images_dat_synthetic_core_only(tmp_path):
    project = make_synthetic_project(tmp_path)

    result = build_images_dat(project)

    assert result.image_count == manifest_image_count(project) == 11
    assert result.images_dat_path == tmp_path / "images.dat"
    assert result.images_dat_path.exists()

    num_entries, total_data_size = read_images_dat_header(result.images_dat_path)
    assert num_entries == 11
    assert total_data_size > 256 * 11


@pytest.mark.skipif(not OPENRCT2_CLI_PATH.exists(), reason="openrct2-cli.exe not available")
def test_build_images_dat_synthetic_with_cars(tmp_path):
    project = make_synthetic_project(tmp_path, num_cars=2)

    result = build_images_dat(project)

    # 3 thumbnails + 8 core + 2 * 8 car frames = 27
    assert result.image_count == manifest_image_count(project) == 27


@pytest.mark.skipif(not OPENRCT2_CLI_PATH.exists(), reason="openrct2-cli.exe not available")
def test_build_images_dat_with_absolute_car_sprite_dir(tmp_path):
    """End-to-end regression test for the real reported failure: a car's
    sprite_dir stored as an absolute path (e.g. picked via the old, buggy
    Browse... behaviour - see ui/layers_panel.py) must still build
    successfully, not surface as "libpng error: Not a PNG file" with the
    project directory doubled in the path."""
    project = make_synthetic_project(tmp_path, num_cars=1)
    project.cars[0].sprite_dir = str(project.project_dir / project.cars[0].sprite_dir)

    result = build_images_dat(project)

    assert result.image_count == manifest_image_count(project) == 19
