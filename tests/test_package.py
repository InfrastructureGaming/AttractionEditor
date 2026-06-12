"""Tests for build/package.py: zipping object.json + images.dat into a
.parkobj and deploying it."""

from __future__ import annotations

import zipfile

import pytest

from attraction_editor.build.package import deploy_parkobj, package_parkobj
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
