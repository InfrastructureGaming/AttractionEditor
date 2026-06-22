"""Ride metadata form, bound to a RideProject.

Rider cars live on the Layers section (layers_panel.py) - they're a sprite
layer concern (rider-overlay frame sets), not project metadata. Default
colour schemes live on the Colours section (colour_preview_panel.py) -
they're a list of presets, not a single project-wide pair."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.model.project import RideProject

RIDE_CATEGORIES = ["transport", "gentle", "rollercoaster", "thrill", "water", "shop"]


class ProjectPanel(QWidget):
    """Ride metadata. Edits are written directly to the bound RideProject;
    `projectChanged` fires after any edit."""

    projectChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None

        self.id_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.description_edit = QLineEdit()
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(RIDE_CATEGORIES)

        self.frames_per_dir_spin = QSpinBox()
        self.frames_per_dir_spin.setRange(1, 65535)

        self.sprite_width_spin = QSpinBox()
        self.sprite_width_spin.setRange(0, 1024)
        self.sprite_height_negative_spin = QSpinBox()
        self.sprite_height_negative_spin.setRange(0, 1024)
        self.sprite_height_positive_spin = QSpinBox()
        self.sprite_height_positive_spin.setRange(0, 1024)

        self.output_name_edit = QLineEdit()
        self.deploy_dir_edit, deploy_row = _path_field(directory=True)
        self.openrct2_cli_edit, cli_row = _path_field(directory=False)

        form = QFormLayout()
        form.addRow("ID", self.id_edit)
        form.addRow("Name", self.name_edit)
        form.addRow("Description", self.description_edit)
        form.addRow("Category", self.category_combo)
        form.addRow("Frames per direction", self.frames_per_dir_spin)
        form.addRow("Sprite width", self.sprite_width_spin)
        form.addRow("Sprite height (negative)", self.sprite_height_negative_spin)
        form.addRow("Sprite height (positive)", self.sprite_height_positive_spin)
        form.addRow("Output name", self.output_name_edit)
        form.addRow("Deploy folder", deploy_row)
        form.addRow("openrct2-cli path", cli_row)

        layout = QVBoxLayout()
        layout.addLayout(form)
        self.setLayout(layout)

        # Wiring
        self.id_edit.textChanged.connect(self._on_simple_field_changed)
        self.name_edit.textChanged.connect(self._on_simple_field_changed)
        self.description_edit.textChanged.connect(self._on_simple_field_changed)
        self.category_combo.currentTextChanged.connect(self._on_simple_field_changed)
        self.frames_per_dir_spin.valueChanged.connect(self._on_simple_field_changed)
        self.sprite_width_spin.valueChanged.connect(self._on_simple_field_changed)
        self.sprite_height_negative_spin.valueChanged.connect(self._on_simple_field_changed)
        self.sprite_height_positive_spin.valueChanged.connect(self._on_simple_field_changed)
        self.output_name_edit.textChanged.connect(self._on_simple_field_changed)
        self.deploy_dir_edit.textChanged.connect(self._on_simple_field_changed)
        self.openrct2_cli_edit.textChanged.connect(self._on_simple_field_changed)

        self._loading = False
        self.setEnabled(False)

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self._loading = True
        try:
            self.id_edit.setText(project.id)
            self.name_edit.setText(project.name)
            self.description_edit.setText(project.description)
            self.category_combo.setCurrentText(project.category)
            self.frames_per_dir_spin.setValue(project.frames_per_dir)
            self.sprite_width_spin.setValue(project.sprite_width)
            self.sprite_height_negative_spin.setValue(project.sprite_height_negative)
            self.sprite_height_positive_spin.setValue(project.sprite_height_positive)
            self.output_name_edit.setText(project.output_name)
            self.deploy_dir_edit.setText(project.deploy_dir or "")
            self.openrct2_cli_edit.setText(project.openrct2_cli_path or "")
        finally:
            self._loading = False
        self.setEnabled(True)

    def _on_simple_field_changed(self, *_args) -> None:
        if self._loading or self.project is None:
            return
        self.project.id = self.id_edit.text()
        self.project.name = self.name_edit.text()
        self.project.description = self.description_edit.text()
        self.project.category = self.category_combo.currentText()
        self.project.frames_per_dir = self.frames_per_dir_spin.value()
        self.project.sprite_width = self.sprite_width_spin.value()
        self.project.sprite_height_negative = self.sprite_height_negative_spin.value()
        self.project.sprite_height_positive = self.sprite_height_positive_spin.value()
        self.project.output_name = self.output_name_edit.text()
        self.project.deploy_dir = self.deploy_dir_edit.text() or None
        self.project.openrct2_cli_path = self.openrct2_cli_edit.text() or None
        self.projectChanged.emit()


def _path_field(directory: bool = False) -> tuple[QLineEdit, QWidget]:
    """A QLineEdit + "Browse..." button packed into a single row widget."""
    edit = QLineEdit()
    browse = QPushButton("Browse...")

    def on_browse() -> None:
        start = edit.text() or str(Path.cwd())
        if directory:
            chosen = QFileDialog.getExistingDirectory(edit, "Select folder", start)
        else:
            chosen, _filter = QFileDialog.getOpenFileName(edit, "Select file", start)
        if chosen:
            edit.setText(chosen)
            # setText() alone doesn't fire editingFinished (only Enter/focus-
            # loss does) - emit it explicitly so Browse-picked paths commit
            # to the model the same way typing-and-pressing-Enter does.
            edit.editingFinished.emit()

    browse.clicked.connect(on_browse)

    row = QWidget()
    row_layout = QHBoxLayout()
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.addWidget(edit)
    row_layout.addWidget(browse)
    row.setLayout(row_layout)
    return edit, row
