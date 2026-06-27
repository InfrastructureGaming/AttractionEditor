"""A colour picker that shows the engine's colour palette as a grid of
swatches instead of a text list - the colours are hard to picture from names
like "dull_brown_dark" alone.

Drop-in API-compatible with the QComboBox it replaces: currentText() /
setCurrentText() / a currentTextChanged(str) signal that fires on user picks
and on programmatic changes, exactly like QComboBox, so callers (and their
tests) don't care which widget is underneath.

Layout mirrors the in-game ride colour dropdown: a 9-wide x 6-tall grid of
the 54 selectable normal colours, in engine Colour-enum order (the same order
colour_ramps.json stores them - black=0 .. dull_brown_light=53). The two
trailing ramps the tool also knows, 'invisible' and 'void', are engine
special-cases the in-game grid doesn't offer, so they're left out of the grid
(but setCurrentText() still renders one if a legacy project carries it)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QToolButton,
    QWidget,
)

from attraction_editor.palette.remap import colour_swatch_rgb, load_colour_ramps

GRID_COLUMNS = 9
GRID_ROWS = 6
# Engine special-cases not shown in the in-game ride colour grid.
_NON_GRID_COLOURS = {"invisible", "void"}

_GRID_SWATCH = 22  # px, each cell in the popup grid
_BUTTON_SWATCH = 16  # px, the swatch shown on the collapsed picker button


def palette_colours() -> list[str]:
    """The 54 selectable colours, in engine order - exactly fills the 9x6 grid."""
    return [c for c in load_colour_ramps() if c not in _NON_GRID_COLOURS]


def humanize_colour(name: str) -> str:
    return name.replace("_", " ").title()


def _swatch_pixmap(colour: str, size: int) -> QPixmap:
    r, g, b = colour_swatch_rgb(colour)
    pm = QPixmap(size, size)
    pm.fill(QColor(r, g, b))
    painter = QPainter(pm)
    painter.setPen(QColor(0, 0, 0, 90))  # thin contrast border so light swatches read on a light bg
    painter.drawRect(0, 0, size - 1, size - 1)
    painter.end()
    return pm


class _SwatchGridPopup(QFrame):
    """The pop-up grid itself. Qt.Popup so a click outside dismisses it."""

    colourPicked = Signal(str)

    def __init__(self, current: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        grid = QGridLayout(self)
        grid.setSpacing(2)
        grid.setContentsMargins(4, 4, 4, 4)

        for i, colour in enumerate(palette_colours()):
            row, col = divmod(i, GRID_COLUMNS)
            btn = QToolButton(self)
            btn.setAutoRaise(True)
            btn.setFixedSize(_GRID_SWATCH + 6, _GRID_SWATCH + 6)
            btn.setIcon(QIcon(_swatch_pixmap(colour, _GRID_SWATCH)))
            btn.setIconSize(QSize(_GRID_SWATCH, _GRID_SWATCH))
            btn.setToolTip(humanize_colour(colour))
            if colour == current:
                btn.setStyleSheet("QToolButton { border: 2px solid palette(highlight); }")
            btn.clicked.connect(lambda _checked=False, c=colour: self._pick(c))
            grid.addWidget(btn, row, col)

    def _pick(self, colour: str) -> None:
        self.colourPicked.emit(colour)
        self.close()


class ColourSwatchPicker(QWidget):
    """A swatch + name button that opens the 9x6 palette grid on click.

    `currentTextChanged(str)` fires whenever the selected colour changes,
    whether from a user pick or a setCurrentText() call (matching QComboBox,
    whose consumers rely on a _loading guard to ignore programmatic changes)."""

    currentTextChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._colour = palette_colours()[0]

        self._button = QPushButton(self)
        self._button.clicked.connect(self._open_popup)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._button)

        self._refresh_button()

    # QComboBox-compatible surface ------------------------------------------

    def currentText(self) -> str:
        return self._colour

    def setCurrentText(self, colour: str) -> None:
        # QComboBox ignores a value it doesn't know and a value already
        # current (the latter emits nothing) - mirror both.
        if colour == self._colour or colour not in load_colour_ramps():
            return
        self._colour = colour
        self._refresh_button()
        self.currentTextChanged.emit(colour)

    # -----------------------------------------------------------------------

    def _refresh_button(self) -> None:
        self._button.setIcon(QIcon(_swatch_pixmap(self._colour, _BUTTON_SWATCH)))
        self._button.setIconSize(QSize(_BUTTON_SWATCH, _BUTTON_SWATCH))
        self._button.setText("  " + humanize_colour(self._colour))

    def _open_popup(self) -> None:
        popup = _SwatchGridPopup(self._colour, self)
        popup.colourPicked.connect(self.setCurrentText)
        popup.move(self.mapToGlobal(self.rect().bottomLeft()))
        popup.show()
