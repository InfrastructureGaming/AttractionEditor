"""Ride metadata form and rider-car list, bound to a RideProject."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.model.project import CarConfig, RideProject
from attraction_editor.palette.remap import load_colour_ramps

RIDE_CATEGORIES = ["transport", "gentle", "rollercoaster", "thrill", "water", "shop"]


class ProjectPanel(QWidget):
    """Ride metadata + rider-car list. Edits are written directly to the
    bound RideProject; `projectChanged` fires after any edit."""

    projectChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None

        colours = sorted(load_colour_ramps().keys())

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

        self.core_sprite_dir_edit, core_row = _path_field()
        self.output_name_edit = QLineEdit()
        self.deploy_dir_edit, deploy_row = _path_field(directory=True)
        self.openrct2_cli_edit, cli_row = _path_field(directory=False)

        self.body_colour_combo = QComboBox()
        self.body_colour_combo.addItems(colours)
        self.trim_colour_combo = QComboBox()
        self.trim_colour_combo.addItems(colours)

        form = QFormLayout()
        form.addRow("ID", self.id_edit)
        form.addRow("Name", self.name_edit)
        form.addRow("Description", self.description_edit)
        form.addRow("Category", self.category_combo)
        form.addRow("Frames per direction", self.frames_per_dir_spin)
        form.addRow("Sprite width", self.sprite_width_spin)
        form.addRow("Sprite height (negative)", self.sprite_height_negative_spin)
        form.addRow("Sprite height (positive)", self.sprite_height_positive_spin)
        form.addRow("Core sprite folder", core_row)
        form.addRow("Body colour", self.body_colour_combo)
        form.addRow("Trim colour", self.trim_colour_combo)
        form.addRow("Output name", self.output_name_edit)
        form.addRow("Deploy folder", deploy_row)
        form.addRow("openrct2-cli path", cli_row)

        self.car_list = QListWidget()
        self.car_name_edit = QLineEdit()
        self.car_sprite_dir_edit, car_dir_row = _path_field()
        add_car_btn = QPushButton("Add car")
        remove_car_btn = QPushButton("Remove car")

        car_buttons = QHBoxLayout()
        car_buttons.addWidget(add_car_btn)
        car_buttons.addWidget(remove_car_btn)

        car_form = QFormLayout()
        car_form.addRow("Name", self.car_name_edit)
        car_form.addRow("Sprite folder", car_dir_row)

        car_box = QGroupBox("Rider cars")
        car_layout = QVBoxLayout()
        car_layout.addWidget(self.car_list)
        car_layout.addLayout(car_buttons)
        car_layout.addLayout(car_form)
        car_box.setLayout(car_layout)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(car_box)
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
        self.core_sprite_dir_edit.textChanged.connect(self._on_simple_field_changed)
        self.output_name_edit.textChanged.connect(self._on_simple_field_changed)
        self.deploy_dir_edit.textChanged.connect(self._on_simple_field_changed)
        self.openrct2_cli_edit.textChanged.connect(self._on_simple_field_changed)
        self.body_colour_combo.currentTextChanged.connect(self._on_simple_field_changed)
        self.trim_colour_combo.currentTextChanged.connect(self._on_simple_field_changed)

        self.car_list.currentRowChanged.connect(self._on_car_selected)
        self.car_name_edit.editingFinished.connect(self._on_car_field_changed)
        self.car_sprite_dir_edit.editingFinished.connect(self._on_car_field_changed)
        add_car_btn.clicked.connect(self._on_add_car)
        remove_car_btn.clicked.connect(self._on_remove_car)

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
            self.core_sprite_dir_edit.setText(project.core_sprite_dir)
            self.output_name_edit.setText(project.output_name)
            self.deploy_dir_edit.setText(project.deploy_dir or "")
            self.openrct2_cli_edit.setText(project.openrct2_cli_path or "")
            self.body_colour_combo.setCurrentText(project.body_colour)
            self.trim_colour_combo.setCurrentText(project.trim_colour)
            self._reload_car_list()
        finally:
            self._loading = False
        self.setEnabled(True)

    def refresh_colours_from_project(self) -> None:
        """Re-sync the body/trim colour combos from `self.project` without
        emitting projectChanged (for use when another panel edited them)."""
        if self.project is None:
            return
        self._loading = True
        try:
            self.body_colour_combo.setCurrentText(self.project.body_colour)
            self.trim_colour_combo.setCurrentText(self.project.trim_colour)
        finally:
            self._loading = False

    def _reload_car_list(self) -> None:
        self.car_list.clear()
        for car in self.project.cars:
            self.car_list.addItem(QListWidgetItem(f"{car.name}: {car.sprite_dir}"))

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
        self.project.core_sprite_dir = self.core_sprite_dir_edit.text()
        self.project.output_name = self.output_name_edit.text()
        self.project.deploy_dir = self.deploy_dir_edit.text() or None
        self.project.openrct2_cli_path = self.openrct2_cli_edit.text() or None
        self.project.body_colour = self.body_colour_combo.currentText()
        self.project.trim_colour = self.trim_colour_combo.currentText()
        self.projectChanged.emit()

    def _on_car_selected(self, row: int) -> None:
        if self.project is None or row < 0 or row >= len(self.project.cars):
            self.car_name_edit.clear()
            self.car_sprite_dir_edit.clear()
            return
        car = self.project.cars[row]
        self._loading = True
        try:
            self.car_name_edit.setText(car.name)
            self.car_sprite_dir_edit.setText(car.sprite_dir)
        finally:
            self._loading = False

    def _on_car_field_changed(self) -> None:
        if self._loading or self.project is None:
            return
        row = self.car_list.currentRow()
        if row < 0 or row >= len(self.project.cars):
            return
        car = self.project.cars[row]
        car.name = self.car_name_edit.text()
        car.sprite_dir = self.car_sprite_dir_edit.text()
        self.car_list.item(row).setText(f"{car.name}: {car.sprite_dir}")
        self.projectChanged.emit()

    def _on_add_car(self) -> None:
        if self.project is None:
            return
        index = len(self.project.cars)
        car = CarConfig(name=f"Car{index}", sprite_dir=f"Frames/Riders/Car{index}")
        self.project.cars.append(car)
        self._reload_car_list()
        self.car_list.setCurrentRow(index)
        self.projectChanged.emit()

    def _on_remove_car(self) -> None:
        if self.project is None:
            return
        row = self.car_list.currentRow()
        if row < 0 or row >= len(self.project.cars):
            return
        del self.project.cars[row]
        self._reload_car_list()
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

    browse.clicked.connect(on_browse)

    row = QWidget()
    row_layout = QHBoxLayout()
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.addWidget(edit)
    row_layout.addWidget(browse)
    row.setLayout(row_layout)
    return edit, row
