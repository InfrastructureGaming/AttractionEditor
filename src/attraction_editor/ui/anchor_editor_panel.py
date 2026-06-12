"""Per-direction sprite anchor editor: a draggable crosshair on the dir0_f0000
frame, bound to RideProject.anchors[direction].

A DirectionAnchor (x, y) is the offset from the sprite's origin point to the
image's top-left corner (the sprite_manifest.json / G1 xOffset/yOffset
convention), so the origin point itself sits at image pixel (-x, -y).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.model.project import DIRECTIONS, DirectionAnchor, RideProject
from attraction_editor.sprites.scanner import frame_path
from attraction_editor.ui.pil_qt import pil_to_pixmap

CROSSHAIR_RADIUS = 5


def anchor_to_origin(anchor: DirectionAnchor) -> tuple[int, int]:
    """The origin point's pixel position within the image, for `anchor`."""
    return (-anchor.x, -anchor.y)


def origin_to_anchor(x: float, y: float) -> DirectionAnchor:
    """The DirectionAnchor for an origin point at image pixel (x, y)."""
    return DirectionAnchor(x=-round(x), y=-round(y))


class _CrosshairItem(QGraphicsEllipseItem):
    def __init__(self, on_moved) -> None:
        r = CROSSHAIR_RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.setBrush(QBrush(QColor(255, 0, 0, 180)))
        self.setPen(QPen(QColor(255, 255, 0), 1))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(10)
        self._on_moved = on_moved

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._on_moved(value)
        return super().itemChange(change, value)


class AnchorEditorPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self._updating = False

        self.direction_combo = QComboBox()
        self.direction_combo.addItems([f"Direction {d}" for d in range(DIRECTIONS)])

        self.x_spin = QSpinBox()
        self.x_spin.setRange(-2000, 2000)
        self.y_spin = QSpinBox()
        self.y_spin.setRange(-2000, 2000)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)

        form = QFormLayout()
        form.addRow("Origin X", self.x_spin)
        form.addRow("Origin Y", self.y_spin)

        controls = QHBoxLayout()
        controls.addWidget(self.direction_combo)
        controls.addLayout(form)

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.view)
        self.setLayout(layout)

        self.direction_combo.currentIndexChanged.connect(self.reload)
        self.x_spin.valueChanged.connect(self._on_spin_changed)
        self.y_spin.valueChanged.connect(self._on_spin_changed)

        self.setEnabled(False)

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self.setEnabled(True)
        self.reload()

    def reload(self, *_args) -> None:
        if self.project is None or self.project.project_dir is None:
            return

        direction = self.direction_combo.currentIndex()
        core_dir = Path(self.project.project_dir) / self.project.core_sprite_dir
        path = frame_path(core_dir, direction, 0)

        self.scene.clear()
        if path.exists():
            with Image.open(path) as img:
                pixmap = pil_to_pixmap(img)
            self.scene.addPixmap(pixmap)
            self.scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
            self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

        self.crosshair = _CrosshairItem(self._on_crosshair_moved)
        self.scene.addItem(self.crosshair)

        anchor = self.project.anchors[direction]
        x, y = anchor_to_origin(anchor)
        self._set_position(x, y)

    def _set_position(self, x: float, y: float) -> None:
        self._updating = True
        try:
            self.crosshair.setPos(QPointF(x, y))
            self.x_spin.setValue(round(x))
            self.y_spin.setValue(round(y))
        finally:
            self._updating = False

    def _on_crosshair_moved(self, pos: QPointF) -> None:
        if self._updating or self.project is None:
            return
        self._updating = True
        try:
            self.x_spin.setValue(round(pos.x()))
            self.y_spin.setValue(round(pos.y()))
        finally:
            self._updating = False
        self._write_anchor(pos.x(), pos.y())

    def _on_spin_changed(self, *_args) -> None:
        if self._updating or self.project is None:
            return
        x, y = self.x_spin.value(), self.y_spin.value()
        self._set_position(x, y)
        self._write_anchor(x, y)

    def _write_anchor(self, x: float, y: float) -> None:
        direction = self.direction_combo.currentIndex()
        self.project.anchors[direction] = origin_to_anchor(x, y)
