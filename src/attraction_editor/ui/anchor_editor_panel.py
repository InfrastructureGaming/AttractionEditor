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

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QLabel,
    QSpinBox,
    QStyleOptionGraphicsItem,
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


def _footprint_grid_lines(width: int, length: int) -> list[tuple[QPointF, QPointF, bool]]:
    """Every tile-boundary line segment for a `width` x `length` isometric
    tile grid, in local coordinates centered on the grid's own geometric
    middle (so the item can be positioned at the same pixel as the anchor's
    origin point - see anchor_to_origin - matching PaintGenericRotatingStructure's
    own centered-on-the-plot convention, GenericFlatRide.cpp).

    Pixel math verified against the engine's own projection (world/MapLimits.h's
    kCoordsXYStep=32, Viewport.cpp's Translate3DTo2DWithZ: screenX = y-x,
    screenY = (x+y)/2, 1:1 with screen pixels, no extra scale factor): moving
    one tile along the `width` axis is screen delta (-32, 16); along `length`
    is (32, 16). vertex(row, col) = top + row*rowStep + col*colStep, where
    `top` is the grid's row=0/col=0 corner relative to its own center.

    Returns (start, end, is_outer_edge) - is_outer_edge marks the 4 segments
    forming the outer boundary (row/col at 0 or its max), drawn brighter than
    the interior per-tile gridlines.
    """
    row_step = QPointF(-32, 16)
    col_step = QPointF(32, 16)
    top = QPointF((width - length) * 16, -(width + length) * 8)

    def vertex(row: int, col: int) -> QPointF:
        return QPointF(top.x() + row * row_step.x() + col * col_step.x(), top.y() + row * row_step.y() + col * col_step.y())

    lines: list[tuple[QPointF, QPointF, bool]] = []
    for row in range(width + 1):
        lines.append((vertex(row, 0), vertex(row, length), row in (0, width)))
    for col in range(length + 1):
        lines.append((vertex(0, col), vertex(width, col), col in (0, length)))
    return lines


class _FootprintGridItem(QGraphicsItem):
    """Pixel-accurate isometric outline of the ride's reserved land footprint
    (RideProject.base_footprint_width/length), centered on the same origin
    point as the anchor crosshair. Outline-only - the actual floor/fence/
    support art is drawn by the engine at runtime (see build/object_json.py's
    custom_ride_manifest docstring); this exists purely so an artist can see
    whether their structure's render extends past the reserved plot."""

    def __init__(self, width: int, length: int) -> None:
        super().__init__()
        self._lines = _footprint_grid_lines(width, length)
        self.setZValue(5)  # above the pixmap, below the crosshair (zValue 10)

        xs = [p.x() for line in self._lines for p in line[:2]]
        ys = [p.y() for line in self._lines for p in line[:2]]
        margin = 2
        self._bounding_rect = QRectF(
            min(xs) - margin, min(ys) - margin, max(xs) - min(xs) + 2 * margin, max(ys) - min(ys) + 2 * margin
        )

    def boundingRect(self) -> QRectF:
        return self._bounding_rect

    def paint(self, painter, option: QStyleOptionGraphicsItem, widget=None) -> None:
        outer_pen = QPen(QColor(0, 255, 255, 220), 1)
        inner_pen = QPen(QColor(0, 255, 255, 110), 1)
        for start, end, is_outer in self._lines:
            painter.setPen(outer_pen if is_outer else inner_pen)
            painter.drawLine(start, end)


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

        self.show_grid_check = QCheckBox("Show footprint grid")
        self.show_grid_check.setChecked(False)  # off by default - opt in when checking plot clipping
        self.show_grid_check.setToolTip(
            "Pixel-accurate isometric outline of the ride's reserved land footprint\n"
            "(Project section's Footprint width/length), centered on this direction's\n"
            "anchor - use it to check whether the structure's render clips past the plot."
        )

        form = QFormLayout()
        form.addRow("Origin X", self.x_spin)
        form.addRow("Origin Y", self.y_spin)
        form.addRow("", self.show_grid_check)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        self.x_spin.valueChanged.connect(self._on_spin_changed)
        self.y_spin.valueChanged.connect(self._on_spin_changed)
        self.show_grid_check.toggled.connect(self.reload)

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

        anchor = self.project.anchors[direction]
        x, y = anchor_to_origin(anchor)

        if self.show_grid_check.isChecked():
            grid = _FootprintGridItem(self.project.base_footprint_width, self.project.base_footprint_length)
            grid.setPos(QPointF(x, y))
            self.preview_widget.add_overlay_item(grid)

        self.crosshair = _CrosshairItem(self._on_crosshair_moved)
        self.preview_widget.add_overlay_item(self.crosshair)

        self._set_position(x, y)
        self.preview_widget.refit_view()

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
