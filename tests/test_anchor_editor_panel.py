"""Tests for the pure anchor <-> origin coordinate math used by
AnchorEditorPanel's draggable crosshair, plus the footprint grid overlay's
pixel math and its panel-level wiring."""

from __future__ import annotations

from attraction_editor.model.project import DirectionAnchor
from attraction_editor.ui.anchor_editor_panel import _FootprintGridItem, _footprint_grid_lines, anchor_to_origin, origin_to_anchor
from attraction_editor.ui.main_window import MainWindow
from tests.fixtures.synthetic import make_synthetic_project


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


def _diamond_extent(width: int, length: int) -> tuple[float, float]:
    lines = _footprint_grid_lines(width, length)
    xs = [p.x() for line in lines for p in line[:2]]
    ys = [p.y() for line in lines for p in line[:2]]
    return max(xs) - min(xs), max(ys) - min(ys)


def test_footprint_grid_lines_single_tile_matches_the_classic_rct_sprite_scale():
    """Verified against the engine's own projection (world/MapLimits.h's
    kCoordsXYStep=32, Viewport.cpp's Translate3DTo2DWithZ): one tile's
    isometric footprint diamond is exactly 64px wide x 32px tall."""
    width, height = _diamond_extent(1, 1)
    assert (width, height) == (64, 32)


def test_footprint_grid_lines_square_dimensions():
    width, height = _diamond_extent(6, 6)
    assert (width, height) == (384, 192)


def test_footprint_grid_lines_non_square_dimensions():
    width, height = _diamond_extent(1, 4)
    assert (width, height) == (160, 80)


def test_footprint_grid_lines_count_includes_every_tile_boundary():
    lines = _footprint_grid_lines(2, 3)
    assert len(lines) == (2 + 1) + (3 + 1)


def test_footprint_grid_lines_marks_exactly_four_outer_edges():
    lines = _footprint_grid_lines(2, 3)
    assert sum(1 for _start, _end, is_outer in lines if is_outer) == 4


def test_footprint_grid_item_bounding_rect_matches_diamond_extent():
    item = _FootprintGridItem(6, 6)
    rect = item.boundingRect()
    # Margin is symmetric, so width/height match the diamond extent exactly
    # even though the rect itself is padded for pen width.
    assert rect.width() == 384 + 2 * 2
    assert rect.height() == 192 + 2 * 2


def test_footprint_grid_shown_by_default_and_centered_on_anchor(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    project = make_synthetic_project(tmp_path)

    window._set_project(project, None)

    grids = [item for item in window.preview_widget.scene.items() if isinstance(item, _FootprintGridItem)]
    assert len(grids) == 1
    direction = window.direction_combo.currentIndex()
    expected_x, expected_y = anchor_to_origin(project.anchors[direction])
    assert (round(grids[0].pos().x()), round(grids[0].pos().y())) == (expected_x, expected_y)


def test_unchecking_show_grid_removes_the_overlay(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    project = make_synthetic_project(tmp_path)
    window._set_project(project, None)

    window.anchor_editor_panel.show_grid_check.setChecked(False)

    grids = [item for item in window.preview_widget.scene.items() if isinstance(item, _FootprintGridItem)]
    assert grids == []


def test_preview_scene_rect_expands_to_include_the_footprint_grid(qtbot, tmp_path):
    """The synthetic project's 80x60 canvas is far smaller than a 6x6
    footprint's 384x192 diamond - the scene must grow to show the part of
    the grid extending past the rendered frame, not clip it away."""
    window = MainWindow()
    qtbot.addWidget(window)
    project = make_synthetic_project(tmp_path)

    window._set_project(project, None)

    scene_rect = window.preview_widget.scene.sceneRect()
    assert scene_rect.width() > 80
    assert scene_rect.height() > 60
