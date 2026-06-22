"""Per-direction sprite anchor editor: a draggable crosshair on the dir0_f0000
frame, bound to RideProject.anchors[direction].

A DirectionAnchor (x, y) is the offset from the sprite's origin point to the
image's top-left corner (the sprite_manifest.json / G1 xOffset/yOffset
convention), so the origin point itself sits at image pixel (-x, -y).

Renders into the shared PreviewWidget (see ui/preview_widget.py) rather than
owning its own QGraphicsView - set_preview_widget()/set_direction_combo() must
be called before set_project()."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.build.layers import composite_preview_frame
from attraction_editor.model.project import ColourScheme, DirectionAnchor, RideProject
from attraction_editor.ui.preview_widget import PreviewWidget

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
        self.preview_widget: PreviewWidget | None = None
        self.direction_combo: QComboBox | None = None
        self.dither_check: QCheckBox | None = None
        self._active_scheme_getter: Callable[[], ColourScheme | None] | None = None
        self._updating = False

        self.x_spin = QSpinBox()
        self.x_spin.setRange(-2000, 2000)
        self.y_spin = QSpinBox()
        self.y_spin.setRange(-2000, 2000)

        form = QFormLayout()
        form.addRow("Origin X", self.x_spin)
        form.addRow("Origin Y", self.y_spin)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        self.x_spin.valueChanged.connect(self._on_spin_changed)
        self.y_spin.valueChanged.connect(self._on_spin_changed)

        self.setEnabled(False)

    def set_preview_widget(self, preview_widget: PreviewWidget) -> None:
        self.preview_widget = preview_widget

    def set_direction_combo(self, direction_combo: QComboBox) -> None:
        self.direction_combo = direction_combo

    def set_active_scheme_getter(self, getter: Callable[[], ColourScheme | None]) -> None:
        """`getter` returns the session's currently-applied colour scheme
        (see ColourPreviewPanel.get_active_scheme), or None for raw sprites."""
        self._active_scheme_getter = getter

    def set_dither_checkbox(self, dither_check: QCheckBox) -> None:
        """The "Preview dithering" checkbox lives on the Colours section
        (ColourPreviewPanel) - this panel just reads the same shared widget."""
        self.dither_check = dither_check

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self.setEnabled(True)
        self.reload()

    def reload(self, *_args) -> None:
        if self.project is None or self.project.project_dir is None or self.preview_widget is None:
            return

        direction = self.direction_combo.currentIndex()
        scheme = self._active_scheme_getter() if self._active_scheme_getter else None
        dither = self.dither_check.isChecked() if self.dither_check is not None else False

        try:
            composite = composite_preview_frame(self.project, direction, dither=dither, scheme=scheme)
        except FileNotFoundError as exc:
            composite = None
            self.status_label.setText(f"Preview unavailable - {exc}")
        else:
            self.status_label.setText("")

        if composite is not None:
            self.preview_widget.set_image(composite)
        else:
            self.preview_widget.clear()

        self.crosshair = _CrosshairItem(self._on_crosshair_moved)
        self.preview_widget.add_overlay_item(self.crosshair)

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
