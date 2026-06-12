"""Tests for build/object_json.py: computing the "images" range string and
updating an existing object.json in place."""

from __future__ import annotations

import json

from attraction_editor.build.object_json import images_range_string, update_object_json
from tests.fixtures.synthetic import make_synthetic_project
from tests.fixtures.tilt_a_whirl import TILT_A_WHIRL_DIR, make_tilt_a_whirl_project

import pytest


def test_images_range_string_synthetic(tmp_path):
    project = make_synthetic_project(tmp_path)

    assert images_range_string(project) == "$LGX:images.dat[0..10]"


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_images_range_string_tilt_a_whirl():
    project = make_tilt_a_whirl_project()

    assert images_range_string(project) == "$LGX:images.dat[0..4098]"


def test_update_object_json_preserves_other_fields(tmp_path):
    project = make_synthetic_project(tmp_path)

    original = {
        "id": project.id,
        "authors": ["OpenRCT2 Dev Fork"],
        "version": "1.0",
        "objectType": "ride",
        "properties": {"type": "synthetic", "category": "thrill"},
        "images": ["$LGX:images.dat[0..999]"],
        "strings": {"name": {"en-GB": "Synthetic"}},
    }
    (tmp_path / "object.json").write_text(json.dumps(original, indent=4), encoding="utf-8")

    updated = update_object_json(project)

    assert updated["images"] == ["$LGX:images.dat[0..10]"]
    assert updated["properties"] == original["properties"]
    assert updated["strings"] == original["strings"]

    on_disk = json.loads((tmp_path / "object.json").read_text(encoding="utf-8"))
    assert on_disk == updated
