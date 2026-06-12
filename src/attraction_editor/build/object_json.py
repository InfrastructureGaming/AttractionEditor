"""Updates a ride's object.json "images" range from the project's computed
manifest image count (see sprites/manifest.py)."""

from __future__ import annotations

import json
from pathlib import Path

from attraction_editor.model.project import RideProject
from attraction_editor.sprites.manifest import manifest_image_count

OBJECT_JSON_FILENAME = "object.json"


def images_range_string(project: RideProject) -> str:
    """The `$LGX:images.dat[0..N-1]` range string for `project`'s manifest."""
    count = manifest_image_count(project)
    return f"$LGX:images.dat[0..{count - 1}]"


def update_object_json(project: RideProject) -> dict:
    """Load project_dir/object.json, update its "images" field to match the
    current manifest image count, and write it back. Returns the updated
    object.json data."""
    if project.project_dir is None:
        raise ValueError("RideProject.project_dir is not set")

    object_json_path = project.project_dir / OBJECT_JSON_FILENAME
    data = json.loads(object_json_path.read_text(encoding="utf-8"))
    data["images"] = [images_range_string(project)]
    object_json_path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
    return data
