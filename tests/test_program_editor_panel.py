"""Smoke tests for ProgramEditorPanel: program/phase list management, field
editing, and the transition-continuity preview, using the synthetic project
fixture (2 frames/dir Core sprites)."""

from __future__ import annotations

from attraction_editor.model.project import AnimationPhase, AnimationProgram
from attraction_editor.ui.program_editor_panel import ProgramEditorPanel
from tests.fixtures.synthetic import make_synthetic_project


def test_program_editor_panel_disabled_by_default(qtbot):
    panel = ProgramEditorPanel()
    qtbot.addWidget(panel)

    assert not panel.isEnabled()


def test_set_project_loads_existing_programs(qtbot, tmp_path):
    project = make_synthetic_project(tmp_path)
    project.programs = [
        AnimationProgram(
            name="Normal",
            phases=[
                AnimationPhase(name="Start", frame_start=0, frame_count=1, next_phase=1),
                AnimationPhase(
                    name="Loop",
                    frame_start=1,
                    frame_count=1,
                    next_phase=1,
                    repeat_until_rotations_complete=True,
                ),
            ],
        )
    ]

    panel = ProgramEditorPanel()
    qtbot.addWidget(panel)
    panel.set_project(project)

    assert panel.isEnabled()
    assert panel.program_list.count() == 1
    assert panel.program_list.item(0).text() == "Normal"
    assert panel.program_name_edit.text() == "Normal"

    assert panel.phase_list.count() == 2
    assert panel.phase_list.item(0).text() == "Start"
    assert panel.phase_list.item(1).text() == "Loop"
    assert panel.next_phase_combo.count() == 2

    # First phase ("Start") is selected by default.
    assert panel.frame_start_spin.value() == 0
    assert panel.frame_count_spin.value() == 1
    assert panel.next_phase_combo.currentIndex() == 1
    assert not panel.repeat_check.isChecked()
    assert not panel.reset_rotations_check.isChecked()


def test_add_program_and_phase(qtbot, tmp_path):
    project = make_synthetic_project(tmp_path)
    assert project.programs == []

    panel = ProgramEditorPanel()
    qtbot.addWidget(panel)
    panel.set_project(project)

    changed = []
    panel.projectChanged.connect(lambda: changed.append(True))

    panel._on_add_program()

    assert len(project.programs) == 1
    assert project.programs[0].name == "Program0"
    assert panel.program_list.count() == 1
    assert panel.program_list.currentRow() == 0
    assert changed

    changed.clear()
    panel._on_add_phase()

    assert len(project.programs[0].phases) == 1
    phase = project.programs[0].phases[0]
    assert phase.name == "Phase0"
    assert phase.frame_start == 0
    assert phase.frame_count == 1
    assert panel.phase_list.count() == 1
    assert changed


def test_phase_field_edits_update_project(qtbot, tmp_path):
    project = make_synthetic_project(tmp_path)
    project.programs = [
        AnimationProgram(
            name="Normal",
            phases=[
                AnimationPhase(name="Start", frame_start=0, frame_count=1, next_phase=1),
                AnimationPhase(name="Loop", frame_start=1, frame_count=1, next_phase=1),
            ],
        )
    ]

    panel = ProgramEditorPanel()
    qtbot.addWidget(panel)
    panel.set_project(project)

    phase = project.programs[0].phases[0]

    changed = []
    panel.projectChanged.connect(lambda: changed.append(True))

    panel.frame_count_spin.setValue(2)
    assert phase.frame_count == 2
    assert changed

    changed.clear()
    panel.repeat_check.setChecked(True)
    assert phase.repeat_until_rotations_complete is True
    assert changed

    changed.clear()
    panel.final_check.setChecked(True)
    assert phase.is_final_phase is True
    assert changed

    changed.clear()
    panel.next_phase_combo.setCurrentIndex(0)
    assert phase.next_phase == 0
    assert changed

    changed.clear()
    panel.reset_rotations_check.setChecked(True)
    assert phase.reset_rotations_on_entry is True
    assert changed


def test_remove_program_and_phase(qtbot, tmp_path):
    project = make_synthetic_project(tmp_path)
    project.programs = [
        AnimationProgram(
            name="Normal",
            phases=[AnimationPhase(name="Only", frame_start=0, frame_count=1, is_final_phase=True)],
        )
    ]

    panel = ProgramEditorPanel()
    qtbot.addWidget(panel)
    panel.set_project(project)

    panel._on_remove_phase()
    assert project.programs[0].phases == []
    assert panel.phase_list.count() == 0

    panel._on_remove_program()
    assert project.programs == []
    assert panel.program_list.count() == 0


def test_transition_continuity_preview(qtbot, tmp_path):
    project = make_synthetic_project(tmp_path)
    # Single phase covering both Core frames (0, 1), looping back to itself:
    # last frame (1) and next_phase's first frame (0) should both render.
    project.programs = [
        AnimationProgram(
            name="Normal",
            phases=[AnimationPhase(name="Loop", frame_start=0, frame_count=2, next_phase=0)],
        )
    ]

    panel = ProgramEditorPanel()
    qtbot.addWidget(panel)
    panel.set_project(project)

    assert not panel.preview_last_label.pixmap().isNull()
    assert "Last frame (1)" in panel.preview_last_label.toolTip()

    assert not panel.preview_first_label.pixmap().isNull()
    assert "first frame (0)" in panel.preview_first_label.toolTip()
