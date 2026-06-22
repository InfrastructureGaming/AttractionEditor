"""Plays a direction's frame sequence at an adjustable FPS: the live
structure composite (every Layer dithered/flattened in z-order, see
build.layers.composite_preview_frame) with rider cars (toggleable per car)
layered on top. This is the place to actually see whether a layer's chosen
dithering algorithm jitters in motion - toggle "Preview dithering" while
playing back.

Deliberately previews with no colour scheme applied (composite_preview_frame's
default) - this shows exactly what will ship, since the real build never
recolours either. For previewing a specific default colour scheme, see the
Colours section (colour_preview_panel.py).

Renders into the shared PreviewWidget (see ui/preview_widget.py) rather than
its own QLabel - set_preview_widget()/set_direction_combo() must be called
before set_project()."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.build.layers import composite_preview_frame
from attraction_editor.model.project import RideProject
from attraction_editor.sprites.scanner import frame_path
from attraction_editor.ui.preview_widget import PreviewWidget

DEFAULT_FPS = 20


class AnimationPlayerPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self.preview_widget: PreviewWidget | None = None
        self.direction_combo: QComboBox | None = None
        self.frame_index = 0
        self.car_checks: dict[str, QCheckBox] = {}

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)

        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setValue(DEFAULT_FPS)

        self.play_button = QPushButton("Play")
        self.play_button.setCheckable(True)

        self.dither_check = QCheckBox("Preview dithering")

        self.frame_counter_label = QLabel("Frame 0")

        self.car_checks_layout = QVBoxLayout()

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        form = QFormLayout()
        form.addRow("FPS", self.fps_spin)
        controls.addLayout(form)
        controls.addWidget(self.dither_check)
        controls.addWidget(self.frame_counter_label)

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addLayout(self.car_checks_layout)
        self.setLayout(layout)

        self.play_button.toggled.connect(self._on_play_toggled)
        self.fps_spin.valueChanged.connect(self._on_fps_changed)
        self.dither_check.stateChanged.connect(self._update_frame)

        self.setEnabled(False)

    def set_preview_widget(self, preview_widget: PreviewWidget) -> None:
        self.preview_widget = preview_widget

    def set_direction_combo(self, direction_combo: QComboBox) -> None:
        self.direction_combo = direction_combo

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self.frame_index = 0
        self.timer.stop()
        self.play_button.setChecked(False)
        self.play_button.setText("Play")
        self._reload_car_checks()
        self._update_frame()
        self.setEnabled(True)

    def _reload_car_checks(self) -> None:
        while self.car_checks_layout.count():
            item = self.car_checks_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.car_checks.clear()

        for car in self.project.cars:
            checkbox = QCheckBox(car.name)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._update_frame)
            self.car_checks_layout.addWidget(checkbox)
            self.car_checks[car.name] = checkbox

    def _on_play_toggled(self, checked: bool) -> None:
        if checked:
            self.timer.start(1000 // self.fps_spin.value())
            self.play_button.setText("Pause")
            self.dither_check.setEnabled(False)
        else:
            self.timer.stop()
            self.play_button.setText("Play")
            self.dither_check.setEnabled(True)
            self._update_frame()

    def _on_fps_changed(self, value: int) -> None:
        if self.timer.isActive():
            self.timer.start(1000 // value)

    def _advance(self) -> None:
        if self.project is None:
            return
        self.frame_index = (self.frame_index + 1) % self.project.frames_per_dir
        self._update_frame()

    def _update_frame(self, *_args) -> None:
        self.frame_counter_label.setText(f"Frame {self.frame_index}")
        if self.project is None or self.project.project_dir is None or self.direction_combo is None:
            return
        if self.preview_widget is None:
            return

        direction = self.direction_combo.currentIndex()
        project_dir = Path(self.project.project_dir)

        try:
            composite = composite_preview_frame(
                self.project, direction, self.frame_index, dither=self.dither_check.isChecked()
            )
        except FileNotFoundError as exc:
            self.frame_counter_label.setText(f"Frame {self.frame_index} - preview unavailable ({exc})")
            return

        for car in self.project.cars:
            checkbox = self.car_checks.get(car.name)
            if checkbox is None or not checkbox.isChecked():
                continue
            car_path = frame_path(project_dir / car.sprite_dir, direction, self.frame_index)
            if not car_path.exists():
                continue
            with Image.open(car_path) as car_img:
                composite = Image.alpha_composite(composite, car_img.convert("RGBA"))

        self.preview_widget.set_image(composite)
