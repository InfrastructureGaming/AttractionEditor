"""Compares the generalized manifest builder's output against the shipped,
hand-built sprite_manifest.json for TiltAWhirl (4099 entries, known-good)."""

from __future__ import annotations

import json

import pytest

from attraction_editor.sprites.manifest import build_manifest, manifest_image_count
from tests.fixtures.tilt_a_whirl import TILT_A_WHIRL_DIR, make_tilt_a_whirl_project


def _normalize(entries: list[dict]) -> list[tuple[str, int, int]]:
    return [(e["path"].replace("\\", "/"), e["x"], e["y"]) for e in entries]


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_manifest_matches_shipped_sprite_manifest():
    project = make_tilt_a_whirl_project()

    generated = build_manifest(project)
    shipped = json.loads((TILT_A_WHIRL_DIR / "sprite_manifest.json").read_text(encoding="utf-8-sig"))

    assert len(generated) == len(shipped) == 4099
    assert _normalize(generated) == _normalize(shipped)


def test_manifest_image_count_matches_entry_count():
    project = make_tilt_a_whirl_project()
    assert manifest_image_count(project) == len(build_manifest(project)) == 4099


def test_manifest_image_count_core_only():
    project = make_tilt_a_whirl_project()
    project.cars = []
    # 3 thumbnails + 4 directions x 128 frames = 515, matching the Core-only
    # object.json images range [0..514] from before riders were added.
    assert manifest_image_count(project) == 515
