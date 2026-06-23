"""Tests for ui/project_panel.py's single "Sprite height" field, replacing
the old negative/positive split - where the origin sits within that height
is the Anchors section's job now (see RideProject.sprite_height /
build/object_json.py's invalidation_bounds)."""

from __future__ import annotations

from attraction_editor.ui.project_panel import ProjectPanel
from tests.fixtures.synthetic import make_synthetic_project


def test_sprite_height_spin_loads_from_project(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    project.sprite_height = 265

    panel.set_project(project)

    assert panel.sprite_height_spin.value() == 265


def test_editing_sprite_height_spin_writes_to_project(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    panel.set_project(project)

    panel.sprite_height_spin.setValue(265)

    assert project.sprite_height == 265


def test_editing_sprite_height_spin_emits_project_changed(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    panel.set_project(project)

    calls = []
    panel.projectChanged.connect(lambda: calls.append(True))
    panel.sprite_height_spin.setValue(200)

    assert len(calls) == 1


def test_panel_has_no_separate_negative_positive_fields(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    assert not hasattr(panel, "sprite_height_negative_spin")
    assert not hasattr(panel, "sprite_height_positive_spin")
