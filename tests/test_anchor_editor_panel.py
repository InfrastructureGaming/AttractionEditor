"""Tests for the pure anchor <-> origin coordinate math used by
AnchorEditorPanel's draggable crosshair."""

from __future__ import annotations

from attraction_editor.model.project import DirectionAnchor
from attraction_editor.ui.anchor_editor_panel import anchor_to_origin, origin_to_anchor


def test_anchor_to_origin():
    assert anchor_to_origin(DirectionAnchor(-138, -77)) == (138, 77)
    assert anchor_to_origin(DirectionAnchor(0, 0)) == (0, 0)


def test_origin_to_anchor():
    assert origin_to_anchor(138, 77) == DirectionAnchor(-138, -77)
    assert origin_to_anchor(0, 0) == DirectionAnchor(0, 0)


def test_anchor_origin_round_trip():
    anchor = DirectionAnchor(-112, -95)
    x, y = anchor_to_origin(anchor)
    assert origin_to_anchor(x, y) == anchor


def test_origin_to_anchor_rounds_float_positions():
    assert origin_to_anchor(137.6, 94.4) == DirectionAnchor(-138, -94)
