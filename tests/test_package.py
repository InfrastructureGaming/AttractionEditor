"""Tests for build/package.py: zipping object.json + images.dat into a
.parkobj, deploying it, and writing the separate manifest.json this fork's
CustomRideLoader.cpp needs to discover the ride at all."""

from __future__ import annotations

import json
import zipfile

import pytest

from attraction_editor.build.package import deploy_parkobj, package_parkobj, write_custom_ride_manifest
from tests.fixtures.synthetic import make_synthetic_project


def _write_build_outputs(project_dir):
    (project_dir / "object.json").write_text("{}", encoding="utf-8")
    (project_dir / "images.dat").write_bytes(b"\x00" * 16)


def test_package_parkobj(tmp_path):
    project = make_synthetic_project(tmp_path)
    _write_build_outputs(tmp_path)

    parkobj_path = package_parkobj(project)

    assert parkobj_path == tmp_path / f"{project.output_name}.parkobj"
    assert parkobj_path.exists()

    with zipfile.ZipFile(parkobj_path) as zf:
        assert set(zf.namelist()) == {"object.json", "images.dat"}


def test_package_parkobj_missing_files_raises(tmp_path):
    project = make_synthetic_project(tmp_path)

    with pytest.raises(FileNotFoundError):
        package_parkobj(project)


def test_deploy_parkobj(tmp_path):
    project = make_synthetic_project(tmp_path)
    _write_build_outputs(tmp_path)
    parkobj_path = package_parkobj(project)

    deploy_dir = tmp_path / "deployed"
    project.deploy_dir = str(deploy_dir)

    dest = deploy_parkobj(project, parkobj_path)

    assert dest == deploy_dir / parkobj_path.name
    assert dest.exists()
    assert dest.read_bytes() == parkobj_path.read_bytes()


def test_deploy_parkobj_requires_deploy_dir(tmp_path):
    project = make_synthetic_project(tmp_path)
    _write_build_outputs(tmp_path)
    parkobj_path = package_parkobj(project)

    with pytest.raises(ValueError):
        deploy_parkobj(project, parkobj_path)


def test_write_custom_ride_manifest(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.description = "A synthetic test ride."
    project.authors = ["Jack"]
    deploy_dir = tmp_path / "deployed"
    project.deploy_dir = str(deploy_dir)

    manifest_path = write_custom_ride_manifest(project)

    assert manifest_path == deploy_dir / "manifest.json"
    written = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert written["name"] == project.name
    # "parkobj" must be the ride's object id (how the engine's object
    # repository looks the vehicle object up), not a filename - the bug
    # this whole feature exists to prevent.
    assert written["parkobj"] == project.id
    assert written["description"] == "A synthetic test ride."
    assert written["author"] == "Jack"


def test_write_custom_ride_manifest_omits_empty_optional_fields(tmp_path):
    project = make_synthetic_project(tmp_path)
    project.description = ""
    project.authors = []
    project.deploy_dir = str(tmp_path / "deployed")

    manifest_path = write_custom_ride_manifest(project)

    written = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "description" not in written
    assert "author" not in written


def test_write_custom_ride_manifest_requires_deploy_dir(tmp_path):
    project = make_synthetic_project(tmp_path)

    with pytest.raises(ValueError):
        write_custom_ride_manifest(project)


def test_write_custom_ride_manifest_overwrites_stale_file(tmp_path):
    """A stale/hand-authored manifest.json from before this feature existed
    must be replaced, not merged with - exactly the bug report this fixes
    (a manifest.json with the wrong "parkobj" value silently breaking the
    ride even though the .parkobj itself built fine)."""
    project = make_synthetic_project(tmp_path)
    deploy_dir = tmp_path / "deployed"
    deploy_dir.mkdir(parents=True)
    (deploy_dir / "manifest.json").write_text(
        json.dumps({"name": "Stale Name", "parkobj": "tilt_a_whirl.parkobj"}), encoding="utf-8"
    )
    project.deploy_dir = str(deploy_dir)

    write_custom_ride_manifest(project)

    written = json.loads((deploy_dir / "manifest.json").read_text(encoding="utf-8"))
    assert written["name"] == project.name
    assert written["parkobj"] == project.id
