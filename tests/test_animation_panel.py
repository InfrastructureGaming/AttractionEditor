"""Tests for ui/animation_panel.py: the method dropdown that swaps between the
Programs & Phases editor and the Motion editor and drives RideProject.animation_method."""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton

from attraction_editor.ui.animation_panel import AnimationPanel
from tests.fixtures.synthetic import make_synthetic_project


def _panel(qtbot, tmp_path, method="frame_sequence"):
    panel = AnimationPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    project.animation_method = method
    panel.set_project(project)
    return panel, project


def test_frame_sequence_shows_programs_editor(qtbot, tmp_path):
    panel, _project = _panel(qtbot, tmp_path, "frame_sequence")
    assert panel.stack.currentWidget() is panel.program_editor_panel


def test_swing_shows_motion_editor(qtbot, tmp_path):
    panel, _project = _panel(qtbot, tmp_path, "swing")
    assert panel.stack.currentWidget() is panel.motion_editor_panel


def test_changing_method_updates_project_and_stack_and_emits(qtbot, tmp_path):
    panel, project = _panel(qtbot, tmp_path, "frame_sequence")
    calls = []
    panel.projectChanged.connect(lambda: calls.append(True))

    panel.method_combo.setCurrentIndex(panel.method_combo.findData("swing"))

    assert project.animation_method == "swing"
    assert panel.stack.currentWidget() is panel.motion_editor_panel
    assert len(calls) == 1


def test_rotation_method_listed_but_disabled(qtbot, tmp_path):
    panel, _project = _panel(qtbot, tmp_path)
    index = panel.method_combo.findData("rotation")
    assert index >= 0  # present as a roadmap signpost
    assert not panel.method_combo.model().item(index).isEnabled()  # not selectable yet


def test_set_project_forwards_to_both_sub_panels(qtbot, tmp_path):
    panel, project = _panel(qtbot, tmp_path, "swing")
    assert panel.program_editor_panel.project is project
    assert panel.motion_editor_panel.project is project


def test_sub_panel_edits_bubble_up_as_project_changed(qtbot, tmp_path):
    panel, project = _panel(qtbot, tmp_path, "swing")
    calls = []
    panel.projectChanged.connect(lambda: calls.append(True))

    add_swing = next(b for b in panel.motion_editor_panel.findChildren(QPushButton) if b.text() == "Add swing")
    add_swing.click()

    assert len(project.motion) == 1
    assert len(calls) >= 1  # motion editor's projectChanged re-emitted by AnimationPanel
