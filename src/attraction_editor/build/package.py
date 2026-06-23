"""Packages object.json + images.dat into a .parkobj and optionally deploys it
(plus the separate manifest.json this fork's CustomRideLoader.cpp needs to
find the ride at all - see write_custom_ride_manifest)."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from attraction_editor.build.object_json import OBJECT_JSON_FILENAME, custom_ride_manifest
from attraction_editor.build.sprite_builder import IMAGES_DAT_FILENAME
from attraction_editor.model.project import RideProject

CUSTOM_RIDE_MANIFEST_FILENAME = "manifest.json"


def package_parkobj(project: RideProject) -> Path:
    """Zip project_dir/object.json + project_dir/images.dat into
    project_dir/<output_name>.parkobj. Returns the .parkobj path."""
    if project.project_dir is None:
        raise ValueError("RideProject.project_dir is not set")

    object_json_path = project.project_dir / OBJECT_JSON_FILENAME
    images_dat_path = project.project_dir / IMAGES_DAT_FILENAME
    for path in (object_json_path, images_dat_path):
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist - run the build step first")

    parkobj_path = project.project_dir / f"{project.output_name}.parkobj"
    with zipfile.ZipFile(parkobj_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(object_json_path, OBJECT_JSON_FILENAME)
        zf.write(images_dat_path, IMAGES_DAT_FILENAME)

    return parkobj_path


def deploy_parkobj(project: RideProject, parkobj_path: Path) -> Path:
    """Copy `parkobj_path` into project.deploy_dir, creating it if needed.
    Returns the deployed file's path."""
    if not project.deploy_dir:
        raise ValueError("RideProject.deploy_dir is not set")

    deploy_dir = Path(project.deploy_dir)
    deploy_dir.mkdir(parents=True, exist_ok=True)
    dest = deploy_dir / parkobj_path.name
    shutil.copy2(parkobj_path, dest)
    return dest


def write_custom_ride_manifest(project: RideProject) -> Path:
    """Write manifest.json into project.deploy_dir (the same folder
    deploy_parkobj copies the .parkobj into) - see
    build/object_json.py's custom_ride_manifest for what this file is and
    why it's separate from object.json. Without it, CustomRideLoader.cpp
    never discovers the ride exists at all, regardless of whether the
    .parkobj itself is valid. Always overwrites, same as deploy_parkobj.
    Returns the written path."""
    if not project.deploy_dir:
        raise ValueError("RideProject.deploy_dir is not set")

    deploy_dir = Path(project.deploy_dir)
    deploy_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = deploy_dir / CUSTOM_RIDE_MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(custom_ride_manifest(project), indent=4) + "\n", encoding="utf-8")
    return manifest_path
