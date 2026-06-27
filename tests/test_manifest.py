"""Tests for the generalized manifest builder: entry count vs.
manifest_image_count's own math stays consistent for any project shape,
checked against a synthetic project rather than one specific ride's
hardcoded totals (every ride has its own frame count/car count, so a fixed
expected number isn't a meaningful regression check going forward)."""

from __future__ import annotations

from attraction_editor.sprites.manifest import THUMBNAIL_COUNT, build_manifest, manifest_image_count
from tests.fixtures.synthetic import make_synthetic_project


def _structure_frame_dir(project):
    return project.layers[0].sprite_dir


def test_manifest_image_count_matches_entry_count(tmp_path):
    project = make_synthetic_project(tmp_path, num_cars=2)
    assert manifest_image_count(project) == len(build_manifest(project, _structure_frame_dir(project)))


def test_manifest_image_count_excludes_cars_when_none_configured(tmp_path):
    project = make_synthetic_project(tmp_path, num_cars=2)
    with_cars = manifest_image_count(project)

    project.cars = []
    without_cars = manifest_image_count(project)

    assert without_cars < with_cars


def test_thumbnail_path_emits_raw_format_preview_entries(tmp_path):
    """A dedicated thumbnail fills all 3 preview slots as flat "raw" sprites
    (G1Flag::hasTransparency) at offset 0,0 - what the engine's masked New Ride
    preview path requires - without changing the total image count."""
    project = make_synthetic_project(tmp_path)
    entries = build_manifest(project, _structure_frame_dir(project), thumbnail_path="thumb.png")

    thumbs = entries[:THUMBNAIL_COUNT]
    assert len(thumbs) == THUMBNAIL_COUNT
    for thumb in thumbs:
        assert thumb["path"].endswith("thumb.png")
        assert thumb["format"] == "raw"
        assert thumb["x"] == 0 and thumb["y"] == 0
    assert len(entries) == manifest_image_count(project)


def test_no_thumbnail_path_falls_back_to_frame_zero_without_format(tmp_path):
    """The legacy fallback (no dedicated thumbnail) reuses structure frame 0 and
    emits no 'format' key, so it builds RLE exactly as before."""
    project = make_synthetic_project(tmp_path)
    entries = build_manifest(project, _structure_frame_dir(project))

    for thumb in entries[:THUMBNAIL_COUNT]:
        assert "format" not in thumb
