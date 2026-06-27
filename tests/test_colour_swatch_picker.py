"""Tests for the ColourSwatchPicker that replaces the Trim/Tertiary colour
combos - it must stay drop-in compatible with the QComboBox API the colour
panel calls (currentText/setCurrentText/currentTextChanged)."""

from __future__ import annotations

from attraction_editor.ui.colour_swatch_picker import (
    GRID_COLUMNS,
    GRID_ROWS,
    ColourSwatchPicker,
    _SwatchGridPopup,
    humanize_colour,
    palette_colours,
)


def test_grid_holds_exactly_the_54_selectable_colours():
    colours = palette_colours()
    assert len(colours) == GRID_COLUMNS * GRID_ROWS == 54
    assert "invisible" not in colours and "void" not in colours
    assert colours[0] == "black"  # engine Colour-enum order


def test_humanize_colour_is_readable():
    assert humanize_colour("dull_brown_dark") == "Dull Brown Dark"


def test_default_current_text_is_first_palette_colour(qtbot):
    picker = ColourSwatchPicker()
    qtbot.addWidget(picker)
    assert picker.currentText() == palette_colours()[0]


def test_set_current_text_changes_value_and_emits(qtbot):
    picker = ColourSwatchPicker()
    qtbot.addWidget(picker)
    seen = []
    picker.currentTextChanged.connect(seen.append)

    picker.setCurrentText("moss_green")

    assert picker.currentText() == "moss_green"
    assert seen == ["moss_green"]


def test_set_current_text_to_same_value_does_not_emit(qtbot):
    picker = ColourSwatchPicker()
    qtbot.addWidget(picker)
    picker.setCurrentText("teal")
    seen = []
    picker.currentTextChanged.connect(seen.append)

    picker.setCurrentText("teal")

    assert seen == []


def test_set_current_text_ignores_unknown_colour(qtbot):
    """QComboBox ignores a value not in its list; the picker mirrors that
    rather than crashing on a missing ramp."""
    picker = ColourSwatchPicker()
    qtbot.addWidget(picker)
    before = picker.currentText()
    seen = []
    picker.currentTextChanged.connect(seen.append)

    picker.setCurrentText("not_a_real_colour")

    assert picker.currentText() == before
    assert seen == []


def test_popup_exposes_every_grid_colour_and_emits_pick(qtbot):
    popup = _SwatchGridPopup(current="black")
    qtbot.addWidget(popup)
    # one swatch button per grid colour
    assert popup.layout().count() == len(palette_colours())

    picked = []
    popup.colourPicked.connect(picked.append)
    popup._pick("bright_red")

    assert picked == ["bright_red"]
