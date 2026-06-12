"""Tests for build/sprite_builder.py: manifest regeneration, images.dat header
parsing, and an end-to-end build against the real openrct2-cli using a small
synthetic project."""

from __future__ import annotations

import json
import struct

import pytest

from attraction_editor.build.sprite_builder import (
    SpriteBuildError,
    build_images_dat,
    read_images_dat_header,
    write_manifest,
)
from attraction_editor.sprites.manifest import build_manifest, manifest_image_count
from tests.fixtures.synthetic import OPENRCT2_CLI_PATH, make_synthetic_project


def test_write_manifest(tmp_path):
    project = make_synthetic_project(tmp_path)

    manifest_path = write_manifest(project)

    assert manifest_path == tmp_path / "sprite_manifest.json"
    written = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert written == build_manifest(project)


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
