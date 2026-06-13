"""Programs & Phases editor: authors RideProject.programs (AnimationProgram /
AnimationPhase), the multi-phase/multi-program animation graph consumed by
build/handoff.py's generate_animation_program_cpp().

Includes a transition-continuity preview - the last frame of the selected
phase next to the first frame of its next_phase - so the animator can confirm
the two line up before handoff."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.model.project import AnimationPhase, AnimationProgram, RideProject
from attraction_editor.sprites.scanner import frame_path
from attraction_editor.ui.pil_qt import pil_to_pixmap

PREVIEW_WIDTH = 160


class ProgramEditorPanel(QWidget):
    """Programs (left) -> Phases (right) -> phase fields + transition preview
    (bottom). Edits are written directly to the bound RideProject;
    `projectChanged` fires after any edit."""

    projectChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self._loading = False

        # Programs column
        self.program_list = QListWidget()
        self.program_name_edit = QLineEdit()
        add_program_btn = QPushButton("Add program")
        remove_program_btn = QPushButton("Remove program")

        program_buttons = QHBoxLayout()
        program_buttons.addWidget(add_program_btn)
        program_buttons.addWidget(remove_program_btn)

        program_box = QGroupBox("Programs")
        program_layout = QVBoxLayout()
        program_layout.addWidget(self.program_list)
        program_layout.addLayout(program_buttons)
        program_layout.addWidget(QLabel("Name"))
        program_layout.addWidget(self.program_name_edit)
        program_box.setLayout(program_layout)

        # Phases column
        self.phase_list = QListWidget()
        add_phase_btn = QPushButton("Add phase")
        remove_phase_btn = QPushButton("Remove phase")

        phase_buttons = QHBoxLayout()
        phase_buttons.addWidget(add_phase_btn)
        phase_buttons.addWidget(remove_phase_btn)

        self.phase_name_edit = QLineEdit()
        self.frame_start_spin = QSpinBox()
        self.frame_start_spin.setRange(0, 1023)
        self.frame_count_spin = QSpinBox()
        self.frame_count_spin.setRange(1, 1024)
        self.ticks_per_frame_spin = QSpinBox()
        self.ticks_per_frame_spin.setRange(1, 60)
        self.next_phase_combo = _NoWheelComboBox()
        self.repeat_check = QCheckBox("Repeat until ride.rotations complete")
        self.final_check = QCheckBox("Final phase (ends program -> arriving)")
        self.reset_rotations_check = QCheckBox("Reset rotation count on entry")

        phase_form = QFormLayout()
        phase_form.addRow("Name", self.phase_name_edit)
        phase_form.addRow("Frame start", self.frame_start_spin)
        phase_form.addRow("Frame count", self.frame_count_spin)
        phase_form.addRow("Ticks per frame", self.ticks_per_frame_spin)
        phase_form.addRow("Next phase", self.next_phase_combo)
        phase_form.addRow(self.repeat_check)
        phase_form.addRow(self.final_check)
        phase_form.addRow(self.reset_rotations_check)

        phase_box = QGroupBox("Phases")
        phase_layout = QVBoxLayout()
        phase_layout.addWidget(self.phase_list)
        phase_layout.addLayout(phase_buttons)
        phase_layout.addLayout(phase_form)
        phase_box.setLayout(phase_layout)

        # Transition continuity preview
        self.preview_last_label = QLabel("Last frame")
        self.preview_first_label = QLabel("Next phase's first frame")
        preview_images = QHBoxLayout()
        preview_images.addWidget(self.preview_last_label)
        preview_images.addWidget(self.preview_first_label)

        preview_box = QGroupBox("Transition continuity preview")
        preview_layout = QVBoxLayout()
        preview_layout.addLayout(preview_images)
        preview_box.setLayout(preview_layout)

        columns = QHBoxLayout()
        columns.addWidget(program_box)
        columns.addWidget(phase_box)

        layout = QVBoxLayout()
        layout.addLayout(columns)
        layout.addWidget(preview_box)
        self.setLayout(layout)

        # Wiring
        self.program_list.currentRowChanged.connect(self._on_program_selected)
        self.program_name_edit.editingFinished.connect(self._on_program_name_changed)
        add_program_btn.clicked.connect(self._on_add_program)
        remove_program_btn.clicked.connect(self._on_remove_program)

        self.phase_list.currentRowChanged.connect(self._on_phase_selected)
        add_phase_btn.clicked.connect(self._on_add_phase)
        remove_phase_btn.clicked.connect(self._on_remove_phase)

        self.phase_name_edit.editingFinished.connect(self._on_phase_field_changed)
        self.frame_start_spin.valueChanged.connect(self._on_phase_field_changed)
        self.frame_count_spin.valueChanged.connect(self._on_phase_field_changed)
        self.ticks_per_frame_spin.valueChanged.connect(self._on_phase_field_changed)
        self.next_phase_combo.currentIndexChanged.connect(self._on_phase_field_changed)
        self.repeat_check.toggled.connect(self._on_phase_field_changed)
        self.final_check.toggled.connect(self._on_phase_field_changed)
        self.reset_rotations_check.toggled.connect(self._on_phase_field_changed)

        self.setEnabled(False)

    # -- project binding -------------------------------------------------

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self._reload_program_list()
        self.setEnabled(True)

    def _reload_program_list(self) -> None:
        self.program_list.clear()
        for program in self.project.programs:
            self.program_list.addItem(program.name)
        if self.project.programs:
            self.program_list.setCurrentRow(0)
        else:
            self._on_program_selected(-1)

    # -- programs ----------------------------------------------------------

    def _current_program(self) -> AnimationProgram | None:
        if self.project is None:
            return None
        row = self.program_list.currentRow()
        if row < 0 or row >= len(self.project.programs):
            return None
        return self.project.programs[row]

    def _on_program_selected(self, row: int) -> None:
        program = self._current_program()
        self._loading = True
        try:
            self.program_name_edit.setText(program.name if program else "")
        finally:
            self._loading = False

        self._reload_phase_list()

    def _on_program_name_changed(self) -> None:
        if self._loading:
            return
        program = self._current_program()
        if program is None:
            return
        program.name = self.program_name_edit.text()
        self.program_list.item(self.program_list.currentRow()).setText(program.name)
        self.projectChanged.emit()

    def _on_add_program(self) -> None:
        if self.project is None:
            return
        index = len(self.project.programs)
        self.project.programs.append(AnimationProgram(name=f"Program{index}", phases=[]))
        self._reload_program_list()
        self.program_list.setCurrentRow(index)
        self.projectChanged.emit()

    def _on_remove_program(self) -> None:
        if self.project is None:
            return
        row = self.program_list.currentRow()
        if row < 0 or row >= len(self.project.programs):
            return
        del self.project.programs[row]
        self._reload_program_list()
        self.projectChanged.emit()

    # -- phases --------------------------------------------------------------

    def _current_phase(self) -> AnimationPhase | None:
        program = self._current_program()
        if program is None:
            return None
        row = self.phase_list.currentRow()
        if row < 0 or row >= len(program.phases):
            return None
        return program.phases[row]

    def _reload_phase_list(self) -> None:
        program = self._current_program()
        self.phase_list.clear()
        if program is not None:
            for phase in program.phases:
                self.phase_list.addItem(phase.name)
        if program and program.phases:
            self.phase_list.setCurrentRow(0)
        else:
            self._on_phase_selected(-1)

    def _on_phase_selected(self, row: int) -> None:
        phase = self._current_phase()
        program = self._current_program()
        self._loading = True
        try:
            self._reload_next_phase_combo(program)
            if phase is None:
                self.phase_name_edit.setText("")
                self.frame_start_spin.setValue(0)
                self.frame_count_spin.setValue(1)
                self.ticks_per_frame_spin.setValue(1)
                self.repeat_check.setChecked(False)
                self.final_check.setChecked(False)
                self.reset_rotations_check.setChecked(False)
            else:
                self.phase_name_edit.setText(phase.name)
                self.frame_start_spin.setValue(phase.frame_start)
                self.frame_count_spin.setValue(phase.frame_count)
                self.ticks_per_frame_spin.setValue(phase.ticks_per_frame)
                if 0 <= phase.next_phase < self.next_phase_combo.count():
                    self.next_phase_combo.setCurrentIndex(phase.next_phase)
                self.repeat_check.setChecked(phase.repeat_until_rotations_complete)
                self.final_check.setChecked(phase.is_final_phase)
                self.reset_rotations_check.setChecked(phase.reset_rotations_on_entry)
        finally:
            self._loading = False

        self._update_preview()

    def _reload_next_phase_combo(self, program: AnimationProgram | None) -> None:
        self.next_phase_combo.clear()
        if program is None:
            return
        for phase in program.phases:
            self.next_phase_combo.addItem(phase.name)

    def _on_add_phase(self) -> None:
        program = self._current_program()
        if program is None:
            return
        index = len(program.phases)
        program.phases.append(AnimationPhase(name=f"Phase{index}", frame_start=0, frame_count=1))
        self._reload_phase_list()
        self.phase_list.setCurrentRow(index)
        self.projectChanged.emit()

    def _on_remove_phase(self) -> None:
        program = self._current_program()
        if program is None:
            return
        row = self.phase_list.currentRow()
        if row < 0 or row >= len(program.phases):
            return
        del program.phases[row]
        self._reload_phase_list()
        self.projectChanged.emit()

    def _on_phase_field_changed(self, *_args) -> None:
        if self._loading:
            return
        phase = self._current_phase()
        if phase is None:
            return

        phase.name = self.phase_name_edit.text()
        phase.frame_start = self.frame_start_spin.value()
        phase.frame_count = self.frame_count_spin.value()
        phase.ticks_per_frame = self.ticks_per_frame_spin.value()
        phase.next_phase = max(0, self.next_phase_combo.currentIndex())
        phase.repeat_until_rotations_complete = self.repeat_check.isChecked()
        phase.is_final_phase = self.final_check.isChecked()
        phase.reset_rotations_on_entry = self.reset_rotations_check.isChecked()

        self.phase_list.item(self.phase_list.currentRow()).setText(phase.name)
        # Renaming this phase may affect other phases' next_phase combo labels.
        self._loading = True
        try:
            self._reload_next_phase_combo(self._current_program())
            if 0 <= phase.next_phase < self.next_phase_combo.count():
                self.next_phase_combo.setCurrentIndex(phase.next_phase)
        finally:
            self._loading = False

        self._update_preview()
        self.projectChanged.emit()

    # -- transition continuity preview ---------------------------------------

    def _update_preview(self) -> None:
        self.preview_last_label.clear()
        self.preview_last_label.setText("Last frame")
        self.preview_first_label.clear()
        self.preview_first_label.setText("Next phase's first frame")

        if self.project is None or self.project.project_dir is None:
            return
        program = self._current_program()
        phase = self._current_phase()
        if program is None or phase is None or phase.frame_count <= 0:
            return

        core_dir = Path(self.project.project_dir) / self.project.core_sprite_dir
        last_frame = phase.frame_start + phase.frame_count - 1
        self._set_preview(self.preview_last_label, core_dir, last_frame, f"Last frame ({last_frame})")

        if 0 <= phase.next_phase < len(program.phases):
            next_phase = program.phases[phase.next_phase]
            first_frame = next_phase.frame_start
            self._set_preview(
                self.preview_first_label,
                core_dir,
                first_frame,
                f"{next_phase.name!r} first frame ({first_frame})",
            )

    def _set_preview(self, label: QLabel, core_dir: Path, frame: int, caption: str) -> None:
        path = frame_path(core_dir, 0, frame)
        if not path.exists():
            label.setText(f"{caption}\n(not found: {path.name})")
            return

        with Image.open(path) as img:
            pixmap = pil_to_pixmap(img)
        if pixmap.width() > PREVIEW_WIDTH:
            pixmap = pixmap.scaledToWidth(PREVIEW_WIDTH, Qt.TransformationMode.SmoothTransformation)
        label.setPixmap(pixmap)
        label.setToolTip(caption)


class _NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse-wheel scrolling, so scrolling the panel
    doesn't accidentally change the selected next_phase."""

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt override
        event.ignore()
