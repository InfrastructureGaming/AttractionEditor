"""Live secondary/tertiary colour-remap preview (Phase 3's remap_preview),
with body/trim Colour pickers kept in sync with the bound RideProject."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from attraction_editor.model.project import DIRECTIONS, RideProject
from attraction_editor.palette.remap import load_colour_ramps, remap_preview
from attraction_editor.sprites.scanner import frame_path
from attraction_editor.ui.pil_qt import pil_to_pixmap


class ColourPreviewPanel(QWidget):
    """projectChanged fires when this panel edits body_colour/trim_colour,
    so other panels (and ProjectPanel's combos) can stay in sync."""

    projectChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self._loading = False

        colours = sorted(load_colour_ramps().keys())

        self.body_combo = QComboBox()
        self.body_combo.addItems(colours)
        self.trim_combo = QComboBox()
        self.trim_combo.addItems(colours)

        self.direction_combo = QComboBox()
        self.direction_combo.addItems([f"Direction {d}" for d in range(DIRECTIONS)])

        self.preview_label = QLabel("No preview available")

        form = QFormLayout()
        form.addRow("Body colour", self.body_combo)
        form.addRow("Trim colour", self.trim_combo)
        form.addRow("Direction", self.direction_combo)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.preview_label)
        self.setLayout(layout)

        self.body_combo.currentTextChanged.connect(self._on_colour_changed)
        self.trim_combo.currentTextChanged.connect(self._on_colour_changed)
        self.direction_combo.currentIndexChanged.connect(self._reload_preview)

        self.setEnabled(False)

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self.setEnabled(True)
        self.refresh_from_project()

    def refresh_from_project(self) -> None:
        """Re-sync the colour combos from `self.project` and re-render the
        preview, without emitting projectChanged (for use when another panel
        edited body_colour/trim_colour)."""
        if self.project is None:
            return
        self._loading = True
        try:
            self.body_combo.setCurrentText(self.project.body_colour)
            self.trim_combo.setCurrentText(self.project.trim_colour)
        finally:
            self._loading = False
        self._reload_preview()

    def _on_colour_changed(self, *_args) -> None:
        if self._loading or self.project is None:
            return
        self.project.body_colour = self.body_combo.currentText()
        self.project.trim_colour = self.trim_combo.currentText()
        self._reload_preview()
        self.projectChanged.emit()

    def _reload_preview(self, *_args) -> None:
        if self.project is None or self.project.project_dir is None:
            self.preview_label.setText("No preview available")
            return

        direction = self.direction_combo.currentIndex()
        core_dir = Path(self.project.project_dir) / self.project.core_sprite_dir
        path = frame_path(core_dir, direction, 0)
        if not path.exists():
            self.preview_label.setText(f"Frame not found: {path}")
            return

        with Image.open(path) as img:
            preview = remap_preview(img.convert("RGBA"), self.project.body_colour, self.project.trim_colour)

        self.preview_label.setPixmap(pil_to_pixmap(preview))
