"""Smoke tests for MainWindow: instantiate all six panels and load the real
TiltAWhirl project (7 cars, 4 anchors, sprite_width=122)."""

from __future__ import annotations

import pytest

from attraction_editor.ui.anchor_editor_panel import anchor_to_origin
from attraction_editor.ui.main_window import MainWindow
from tests.fixtures.tilt_a_whirl import TILT_A_WHIRL_DIR, make_tilt_a_whirl_project


def test_main_window_constructs(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.project is None
    # Panels start disabled until a project is loaded.
    assert not window.project_panel.isEnabled()
    assert not window.build_panel.isEnabled()


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_main_window_loads_tilt_a_whirl(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_tilt_a_whirl_project()
    window._set_project(project, None)

    assert window.project is project
    assert window.project_panel.isEnabled()
    assert window.project_panel.id_edit.text() == "openrct2dev.ride.tilt_a_whirl"
    assert window.project_panel.car_list.count() == 7
    assert window.project_panel.body_colour_combo.currentText() == "bright_red"

    assert window.sprite_browser_panel.frame_set_list.count() == 8  # Core + 7 cars

    assert window.animation_player_panel.car_checks.keys() == {f"Car{i}" for i in range(7)}

    expected_origin = anchor_to_origin(project.anchors[0])
    pos = window.anchor_editor_panel.crosshair.pos()
    assert (round(pos.x()), round(pos.y())) == expected_origin

    assert window.build_panel.project is project


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_project_panel_edit_propagates_to_other_panels(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_tilt_a_whirl_project()
    window._set_project(project, None)

    window.project_panel.body_colour_combo.setCurrentText("yellow")

    assert project.body_colour == "yellow"
    assert window.colour_preview_panel.body_combo.currentText() == "yellow"

    window.colour_preview_panel.trim_combo.setCurrentText("black")

    assert project.trim_colour == "black"
    assert window.project_panel.trim_colour_combo.currentText() == "black"
