"""Tests for ui/motion_editor_panel.py: authoring RideProject.motion (parametric
swing/loop segment dicts, compiled at build - see build/motion.py)."""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton

from attraction_editor.ui.motion_editor_panel import MotionEditorPanel
from tests.fixtures.synthetic import make_synthetic_project


def _panel(qtbot, tmp_path):
    panel = MotionEditorPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    panel.set_project(project)
    return panel, project


def _btn(panel, text):
    return next(b for b in panel.findChildren(QPushButton) if b.text() == text)


def test_add_swing_and_loop_append_defaults(qtbot, tmp_path):
    panel, project = _panel(qtbot, tmp_path)
    assert project.motion == []

    _btn(panel, "Add swing").click()
    _btn(panel, "Add loop").click()

    assert [s["kind"] for s in project.motion] == ["swing", "loop"]
    assert panel.segment_list.count() == 2


def test_editing_swing_fields_writes_to_segment(qtbot, tmp_path):
    panel, project = _panel(qtbot, tmp_path)
    _btn(panel, "Add swing").click()

    panel.amplitude_spin.setValue(120)
    panel.cycles_spin.setValue(3)
    panel.ticks_spin.setValue(200)
    panel.easing_combo.setCurrentText("linear")

    seg = project.motion[0]
    assert (seg["amplitude"], seg["cycles"], seg["ticks"], seg["easing"]) == (120, 3, 200, "linear")


def test_editing_loop_direction(qtbot, tmp_path):
    panel, project = _panel(qtbot, tmp_path)
    _btn(panel, "Add loop").click()

    panel.turns_spin.setValue(3)
    panel.direction_combo.setCurrentIndex(1)  # reverse

    assert project.motion[0]["turns"] == 3
    assert project.motion[0]["direction"] == -1


def test_remove_deletes_selected_segment(qtbot, tmp_path):
    panel, project = _panel(qtbot, tmp_path)
    _btn(panel, "Add swing").click()
    _btn(panel, "Add loop").click()

    panel.segment_list.setCurrentRow(0)
    _btn(panel, "Remove").click()

    assert [s["kind"] for s in project.motion] == ["loop"]


def test_move_up_reorders(qtbot, tmp_path):
    panel, project = _panel(qtbot, tmp_path)
    _btn(panel, "Add swing").click()
    _btn(panel, "Add loop").click()

    panel.segment_list.setCurrentRow(1)  # the loop
    _btn(panel, "Move up").click()

    assert [s["kind"] for s in project.motion] == ["loop", "swing"]


def test_kind_specific_fields_toggle_with_selection(qtbot, tmp_path):
    panel, _project = _panel(qtbot, tmp_path)
    _btn(panel, "Add swing").click()
    assert panel.swing_fields.isVisibleTo(panel)
    assert not panel.loop_fields.isVisibleTo(panel)

    _btn(panel, "Add loop").click()  # selects the new loop
    assert panel.loop_fields.isVisibleTo(panel)
    assert not panel.swing_fields.isVisibleTo(panel)


def test_set_project_loads_existing_motion(qtbot, tmp_path):
    panel = MotionEditorPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    project.motion = [{"kind": "swing", "amplitude": 45, "cycles": 2, "ticks": 100, "easing": "sine"}]

    panel.set_project(project)

    assert panel.segment_list.count() == 1
    panel.segment_list.setCurrentRow(0)
    assert panel.amplitude_spin.value() == 45
    assert panel.cycles_spin.value() == 2


def test_add_frames_appends_door_default(qtbot, tmp_path):
    panel, project = _panel(qtbot, tmp_path)
    _btn(panel, "Add frames").click()
    seg = project.motion[0]
    assert seg["kind"] == "frames"
    assert (seg["start"], seg["end"]) == (391, 361)  # door-close default


def test_editing_frames_fields_writes_to_segment(qtbot, tmp_path):
    panel, project = _panel(qtbot, tmp_path)
    _btn(panel, "Add frames").click()

    panel.frames_start_spin.setValue(361)
    panel.frames_end_spin.setValue(391)
    panel.frame_ticks_spin.setValue(2)

    seg = project.motion[0]
    assert (seg["start"], seg["end"], seg["ticks_per_frame"]) == (361, 391, 2)


def test_loop_repeatable_checkbox_writes(qtbot, tmp_path):
    panel, project = _panel(qtbot, tmp_path)
    _btn(panel, "Add loop").click()

    panel.repeatable_check.setChecked(True)

    assert project.motion[0]["repeatable"] is True


def test_frames_selection_hides_shared_ticks_and_easing(qtbot, tmp_path):
    panel, _project = _panel(qtbot, tmp_path)
    _btn(panel, "Add frames").click()
    assert panel.frames_fields.isVisibleTo(panel)
    assert not panel.shared_fields.isVisibleTo(panel)  # frames time per-frame
    assert not panel.swing_fields.isVisibleTo(panel)

    _btn(panel, "Add swing").click()  # selects the new swing
    assert panel.shared_fields.isVisibleTo(panel)
    assert not panel.frames_fields.isVisibleTo(panel)


def test_panel_disabled_until_project_set(qtbot):
    panel = MotionEditorPanel()
    qtbot.addWidget(panel)
    assert not panel.isEnabled()
