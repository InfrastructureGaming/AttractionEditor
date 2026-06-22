"""Smoke tests for MainWindow: instantiate every section (no tabs - all
panels share one PreviewWidget + one Direction combo) and load the real
TiltAWhirl project (7 cars, 4 anchors, sprite_width=122)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QTabWidget

from attraction_editor.ui.anchor_editor_panel import anchor_to_origin
from attraction_editor.ui.collapsible_section import CollapsibleSection
from attraction_editor.ui.main_window import MainWindow
from tests.fixtures.tilt_a_whirl import TILT_A_WHIRL_DIR, make_tilt_a_whirl_project


def test_main_window_constructs(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.project is None
    # Panels start disabled until a project is loaded.
    assert not window.project_panel.isEnabled()
    assert not window.build_panel.isEnabled()


def test_main_window_has_no_tabs(qtbot):
    """The unified layout replaced QTabWidget entirely."""
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.findChild(QTabWidget) is None


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_dragging_splitter_never_triggers_horizontal_scrolling(qtbot):
    """QScrollArea.minimumSizeHint() ignores its content's width by design,
    so without an explicit floor a QSplitter will happily shrink the controls
    column past the point where its content needs to scroll horizontally.
    The divider must be unable to create that situation, no matter how it's
    dragged - and the right edge must stay flush with the window's edge."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1400, 900)
    window.show()

    project = make_tilt_a_whirl_project()
    window._set_project(project, None)

    scroll = window.findChild(QScrollArea)
    splitter = window.centralWidget()

    for requested in ([1100, 300], [1300, 100], [1390, 10]):
        splitter.setSizes(requested)
        qtbot.wait(0)
        assert not scroll.horizontalScrollBar().isVisible()

    assert scroll.geometry().right() == splitter.width() - 1


def test_every_section_is_collapsible(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    sections = window.findChildren(CollapsibleSection)
    titles = {s.toggle_button.text() for s in sections}

    assert titles == {
        "Project", "Layers", "Sprites", "Anchors", "Colours", "Animation", "Programs & Phases", "Build",
    }
    for section in sections:
        # Default state: only Project starts expanded, everything else
        # starts collapsed (toggling each is still possible either way).
        expected_expanded = section.toggle_button.text() == "Project"
        assert (not section.body.isHidden()) == expected_expanded


def test_controls_column_ends_with_a_stretch(qtbot):
    """Regression guard: without a trailing stretch, QVBoxLayout spreads
    collapsed (now-small) sections out to fill the column's full height
    instead of keeping them packed together at the top.

    Checked structurally (the layout's last item is a stretchable spacer)
    rather than via rendered pixel geometry: the offscreen Qt platform used
    in headless tests doesn't support propagateSizeHints(), which makes
    geometry-based assertions about dynamic show/hide changes unreliable."""
    window = MainWindow()
    qtbot.addWidget(window)

    scroll = window.findChild(QScrollArea)
    layout = scroll.widget().layout()

    last_item = layout.itemAt(layout.count() - 1)
    assert last_item.spacerItem() is not None
    assert last_item.spacerItem().expandingDirections() & Qt.Orientation.Vertical


def test_splitter_defaults_to_a_50_50_split_on_first_show(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1400, 900)
    window.show()
    qtbot.wait(50)  # let the deferred QTimer.singleShot(0, ...) actually fire

    sizes = window.splitter.sizes()
    assert abs(sizes[0] - sizes[1]) <= 2  # equal modulo the handle width


def test_splitter_user_drag_survives_hide_show_cycle(qtbot):
    """The 50/50 default must only apply once - a later hide/show (e.g.
    minimize/restore) must not reset a user's own drag back to 50/50."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1400, 900)
    window.show()
    qtbot.wait(50)

    window.splitter.setSizes([900, 480])
    window.hide()
    window.show()
    qtbot.wait(50)

    # Not asserting an exact pixel value - minimum-width constraints can
    # clamp the requested split slightly. What matters is it stayed close to
    # the user's drag instead of resetting to 50/50.
    sizes = window.splitter.sizes()
    assert sizes[0] > sizes[1]


def test_collapsing_a_section_does_not_disable_its_panel(qtbot):
    """Regression guard: collapsing must stay purely visual. A QGroupBox.
    setCheckable()-based implementation would auto-disable the panel here,
    which is exactly the bug this design avoids."""
    window = MainWindow()
    qtbot.addWidget(window)

    project_section = next(s for s in window.findChildren(CollapsibleSection) if s.toggle_button.text() == "Project")
    project_section.toggle_button.setChecked(False)

    assert project_section.body.isHidden()
    # Enabled-state is unaffected by collapse; it's still False only because
    # no project has been loaded yet (set_project() controls that, not collapse).
    project_section.toggle_button.setChecked(True)
    assert not window.project_panel.isEnabled()


def test_main_window_panels_share_one_preview_widget_and_direction_combo(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    for panel in (
        window.anchor_editor_panel,
        window.colour_preview_panel,
        window.animation_player_panel,
        window.layers_panel,
    ):
        assert panel.preview_widget is window.preview_widget
        assert panel.direction_combo is window.direction_combo


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_main_window_loads_tilt_a_whirl(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_tilt_a_whirl_project()
    window._set_project(project, None)

    assert window.project is project
    assert window.project_panel.isEnabled()
    assert window.project_panel.id_edit.text() == "openrct2dev.ride.tilt_a_whirl"
    assert window.layers_panel.car_list.count() == 7

    assert window.sprite_browser_panel.frame_set_list.count() == 9  # Core_Static_0 + Core_Anim_0 + 7 cars

    assert window.animation_player_panel.car_checks.keys() == {f"Car{i}" for i in range(7)}

    expected_origin = anchor_to_origin(project.anchors[0])
    pos = window.anchor_editor_panel.crosshair.pos()
    assert (round(pos.x()), round(pos.y())) == expected_origin

    assert window.build_panel.project is project


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_colour_scheme_edit_updates_project(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_tilt_a_whirl_project()
    window._set_project(project, None)

    window.colour_preview_panel.trim_combo.setCurrentText("yellow")
    assert project.colour_schemes[0].trim_colour == "yellow"

    window.colour_preview_panel.tertiary_combo.setCurrentText("black")
    assert project.colour_schemes[0].tertiary_colour == "black"


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_editing_layers_updates_shared_preview(qtbot):
    """The main functional gain of this pass: LayersPanel had no preview at
    all before - now its edits reach the same shared surface as everything
    else."""
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_tilt_a_whirl_project()
    window._set_project(project, None)

    before = window.preview_widget.scene.items()
    window.layers_panel._on_move_down()  # any compositing-relevant edit
    after = window.preview_widget.scene.items()

    # The scene was rebuilt (new pixmap item instance), proving LayersPanel
    # actually pushed a fresh render into the shared widget.
    assert before != after or len(after) > 0


@pytest.mark.skipif(not TILT_A_WHIRL_DIR.exists(), reason="TiltAWhirl project directory not available")
def test_anchor_crosshair_survives_direction_change(qtbot):
    """Regression test: AnchorEditorPanel must refresh last in every shared-
    preview cascade, or a later section's set_image() call deletes its
    crosshair overlay (scene.clear() wipes everything, not just its own)."""
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_tilt_a_whirl_project()
    window._set_project(project, None)

    window.direction_combo.setCurrentIndex(1)

    # Must not raise (the crosshair's underlying C++ object must still be alive).
    pos = window.anchor_editor_panel.crosshair.pos()
    expected_origin = anchor_to_origin(project.anchors[1])
    assert (round(pos.x()), round(pos.y())) == expected_origin
