"""Per-car/direction frame grid with blank-frame / duplicate-trajectory
validation status (Phase 2's validate.py)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.model.project import Layer, RideProject
from attraction_editor.sprites.scanner import frame_path, static_frame_path
from attraction_editor.sprites.validate import SAMPLE_FRAMES, FrameSetReport, validate_project
from attraction_editor.ui.pil_qt import pil_to_pixmap

THUMBNAIL_SIZE = 64


class SpriteBrowserPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self.reports: dict[str, FrameSetReport] = {}

        self.frame_set_list = QListWidget()
        self.direction_combo = QComboBox()
        self.direction_combo.addItems([f"Direction {d}" for d in range(4)])

        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbnail_list.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self.thumbnail_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumbnail_list.setMovement(QListWidget.Movement.Static)

        self.issues_text = QTextEdit()
        self.issues_text.setReadOnly(True)

        validate_btn = QPushButton("Run validation")
        validate_btn.clicked.connect(self.run_validation)

        left = QVBoxLayout()
        left.addWidget(validate_btn)
        left.addWidget(self.frame_set_list)
        left.addWidget(self.issues_text)
        left_widget = QWidget()
        left_widget.setLayout(left)

        right = QVBoxLayout()
        right.addWidget(self.direction_combo)
        right.addWidget(self.thumbnail_list)
        right_widget = QWidget()
        right_widget.setLayout(right)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)

        layout = QHBoxLayout()
        layout.addWidget(splitter)
        self.setLayout(layout)

        self.frame_set_list.currentRowChanged.connect(self._reload_thumbnails)
        self.direction_combo.currentIndexChanged.connect(self._reload_thumbnails)

        self.setEnabled(False)

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self.reports = {}
        self._reload_frame_set_list()
        self.setEnabled(True)

    def _frame_set_names(self) -> list[str]:
        if self.project is None:
            return []
        return [layer.name for layer in self.project.layers] + [car.name for car in self.project.cars]

    def _layer_for(self, name: str) -> Layer | None:
        if self.project is None:
            return None
        for layer in self.project.layers:
            if layer.name == name:
                return layer
        return None

    def _sprite_dir_for(self, name: str) -> str:
        layer = self._layer_for(name)
        if layer is not None:
            return layer.sprite_dir
        for car in self.project.cars:
            if car.name == name:
                return car.sprite_dir
        raise KeyError(name)

    def _reload_frame_set_list(self) -> None:
        current = self.frame_set_list.currentRow()
        self.frame_set_list.clear()
        for name in self._frame_set_names():
            report = self.reports.get(name)
            status = _status_label(report)
            self.frame_set_list.addItem(QListWidgetItem(f"{status} {name}"))
        if current >= 0 and current < self.frame_set_list.count():
            self.frame_set_list.setCurrentRow(current)
        elif self.frame_set_list.count() > 0:
            self.frame_set_list.setCurrentRow(0)

    def run_validation(self) -> None:
        if self.project is None:
            return
        self.reports = validate_project(self.project)
        self._reload_frame_set_list()
        self._update_issues()

    def _update_issues(self) -> None:
        names = self._frame_set_names()
        row = self.frame_set_list.currentRow()
        if row < 0 or row >= len(names):
            self.issues_text.clear()
            return
        report = self.reports.get(names[row])
        if report is None:
            self.issues_text.setPlainText("Not yet validated. Click \"Run validation\".")
            return
        if not report.issues:
            self.issues_text.setPlainText("No issues found.")
            return
        lines = [f"[{issue.severity.upper()}] {issue.message}" for issue in report.issues]
        self.issues_text.setPlainText("\n".join(lines))

    def _reload_thumbnails(self, *_args) -> None:
        self.thumbnail_list.clear()
        self._update_issues()
        if self.project is None or self.project.project_dir is None:
            return
        names = self._frame_set_names()
        row = self.frame_set_list.currentRow()
        if row < 0 or row >= len(names):
            return

        sprite_dir = Path(self.project.project_dir) / self._sprite_dir_for(names[row])
        direction = self.direction_combo.currentIndex()
        layer = self._layer_for(names[row])

        if layer is not None and layer.kind == "static":
            # A static layer has exactly one frame per direction - nothing to sample.
            path = static_frame_path(sprite_dir, direction)
            if path.exists():
                with Image.open(path) as img:
                    thumb = img.copy()
                thumb.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE))
                icon = QIcon(pil_to_pixmap(thumb))
                self.thumbnail_list.addItem(QListWidgetItem(icon, "static"))
            return

        samples = [f for f in SAMPLE_FRAMES if f < self.project.frames_per_dir]
        for frame in samples:
            path = frame_path(sprite_dir, direction, frame)
            if not path.exists():
                continue
            with Image.open(path) as img:
                thumb = img.copy()
            thumb.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE))
            icon = QIcon(pil_to_pixmap(thumb))
            self.thumbnail_list.addItem(QListWidgetItem(icon, f"f{frame:04d}"))


def _status_label(report: FrameSetReport | None) -> str:
    if report is None:
        return "[?]"
    if any(issue.severity == "error" for issue in report.issues):
        return "[ERROR]"
    if any(issue.severity == "warning" for issue in report.issues):
        return "[WARN]"
    return "[OK]"
