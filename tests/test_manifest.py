"""Tests for the generalized manifest builder: entry count vs.
manifest_image_count's own math stays consistent for any project shape,
checked against a synthetic project rather than one specific ride's
hardcoded totals (every ride has its own frame count/car count, so a fixed
expected number isn't a meaningful regression check going forward)."""

from __future__ import annotations

from attraction_editor.sprites.manifest import build_manifest, manifest_image_count
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
