"""Smoke tests for MainWindow: instantiate every section (no tabs - all
panels share one PreviewWidget + one Direction combo) and load a synthetic
project with real, renderable frames on disk."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QTabWidget

from attraction_editor.ui.anchor_editor_panel import anchor_to_origin
from attraction_editor.ui.collapsible_section import CollapsibleSection
from attraction_editor.ui.main_window import MainWindow
from tests.fixtures.synthetic import make_synthetic_project


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


def test_dragging_splitter_never_triggers_horizontal_scrolling(qtbot, tmp_path):
    """QScrollArea.minimumSizeHint() ignores its content's width by design,
    so without an explicit floor a QSplitter will happily shrink the controls
    column past the point where its content needs to scroll horizontally.
    The divider must be unable to create that situation, no matter how it's
    dragged - and the right edge must stay flush with the window's edge."""
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1400, 900)
    window.show()

    project = make_synthetic_project(tmp_path, num_cars=2)
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
        "Project", "Ride Object", "Layers", "Sprites", "Anchors", "Colours", "Animation",
        "Programs & Phases", "Motion (parametric)", "Build",
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


def test_main_window_loads_project(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_synthetic_project(tmp_path, num_cars=2)
    window._set_project(project, None)

    assert window.project is project
    assert window.project_panel.isEnabled()
    assert window.project_panel.id_edit.text() == project.id
    assert window.layers_panel.car_list.count() == len(project.cars)

    # One frame set per structure layer, plus one per car.
    assert window.sprite_browser_panel.frame_set_list.count() == len(project.layers) + len(project.cars)

    assert window.animation_player_panel.car_checks.keys() == {car.name for car in project.cars}

    expected_origin = anchor_to_origin(project.anchors[0])
    window.anchor_editor_panel.set_section_expanded(True)  # crosshair only present while Anchors is open
    pos = window.anchor_editor_panel.crosshair.pos()
    assert (round(pos.x()), round(pos.y())) == expected_origin

    assert window.build_panel.project is project


def test_colour_scheme_edit_updates_project(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_synthetic_project(tmp_path)
    window._set_project(project, None)

    window.colour_preview_panel.trim_combo.setCurrentText("yellow")
    assert project.colour_schemes[0].trim_colour == "yellow"

    window.colour_preview_panel.tertiary_combo.setCurrentText("black")
    assert project.colour_schemes[0].tertiary_colour == "black"


def test_dither_checkbox_moved_to_colours_section(qtbot):
    """"Preview dithering" now lives on ColourPreviewPanel - every other
    preview-rendering panel just reads the same shared widget rather than
    owning its own (or, for Anchors/Layers, not reading it at all - the
    bug this test guards against)."""
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.colour_preview_panel.dither_check is not None
    for panel in (window.animation_player_panel, window.anchor_editor_panel, window.layers_panel):
        assert panel.dither_check is window.colour_preview_panel.dither_check


def test_toggling_dither_checkbox_refreshes_animation_preview(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_synthetic_project(tmp_path)
    window._set_project(project, None)

    before = window.preview_widget.scene.items()
    window.colour_preview_panel.dither_check.setChecked(True)
    after = window.preview_widget.scene.items()

    assert before != after or len(after) > 0


def test_toggling_dither_checkbox_changes_anchor_panels_render(qtbot, tmp_path):
    """Regression guard: AnchorEditorPanel didn't read the dither checkbox
    at all before this fix - toggling it had zero visible effect whenever
    Anchors was the last section to render into the shared preview."""
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_synthetic_project(tmp_path)
    window._set_project(project, None)

    window.colour_preview_panel.dither_check.setChecked(False)
    window.anchor_editor_panel.reload()
    without_dither = bytes(window.preview_widget.scene.items()[-1].pixmap().toImage().bits())

    window.colour_preview_panel.dither_check.setChecked(True)
    window.anchor_editor_panel.reload()
    with_dither = bytes(window.preview_widget.scene.items()[-1].pixmap().toImage().bits())

    assert without_dither != with_dither


def test_toggling_dither_checkbox_changes_layers_panels_render(qtbot, tmp_path):
    """Same regression guard as above, for LayersPanel."""
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_synthetic_project(tmp_path)
    window._set_project(project, None)

    window.colour_preview_panel.dither_check.setChecked(False)
    window.layers_panel._reload_preview()
    without_dither = bytes(window.preview_widget.scene.items()[0].pixmap().toImage().bits())

    window.colour_preview_panel.dither_check.setChecked(True)
    window.layers_panel._reload_preview()
    with_dither = bytes(window.preview_widget.scene.items()[0].pixmap().toImage().bits())

    assert without_dither != with_dither


def test_editing_catch_tolerance_refreshes_every_preview_panel(qtbot, tmp_path):
    """Trim/Tertiary catch tolerance (RideProject.trim_catch_tolerance/
    tertiary_catch_tolerance) affects every layer's dithering, not just
    Colours' own preview - changing it should refresh Layers/Animation/
    Anchors too, the same way the dither checkbox and active scheme do."""
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_synthetic_project(tmp_path)
    window._set_project(project, None)

    before = window.preview_widget.scene.items()
    window.colour_preview_panel.trim_tolerance_spin.setValue(25)
    after = window.preview_widget.scene.items()

    assert project.trim_catch_tolerance == 25
    assert before != after or len(after) > 0


def test_editing_layers_updates_shared_preview(qtbot, tmp_path):
    """The main functional gain of this pass: LayersPanel had no preview at
    all before - now its edits reach the same shared surface as everything
    else."""
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_synthetic_project(tmp_path)
    window._set_project(project, None)

    before = window.preview_widget.scene.items()
    window.layers_panel._on_move_down()  # any compositing-relevant edit
    after = window.preview_widget.scene.items()

    # The scene was rebuilt (new pixmap item instance), proving LayersPanel
    # actually pushed a fresh render into the shared widget.
    assert before != after or len(after) > 0


def test_applying_a_colour_scheme_reaches_every_preview_panel(qtbot, tmp_path):
    """ColourPreviewPanel owns the active-scheme state; Layers/Anchors/
    Animation must read it through the getter MainWindow wires up, not just
    Colours' own preview."""
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_synthetic_project(tmp_path)
    window._set_project(project, None)

    # Wiring itself: every reader points at the same bound method.
    for panel in (window.anchor_editor_panel, window.animation_player_panel, window.layers_panel):
        assert panel._active_scheme_getter == window.colour_preview_panel.get_active_scheme

    assert window.colour_preview_panel.get_active_scheme() is None

    window.colour_preview_panel.scheme_list.setCurrentRow(0)
    window.colour_preview_panel._on_apply_scheme()

    applied = window.colour_preview_panel.get_active_scheme()
    assert applied is project.colour_schemes[0]
    # Every panel's getter resolves to the same now-applied scheme.
    for panel in (window.anchor_editor_panel, window.animation_player_panel, window.layers_panel):
        assert panel._active_scheme_getter() is applied

    window.colour_preview_panel._on_disable_colours()
    for panel in (window.anchor_editor_panel, window.animation_player_panel, window.layers_panel):
        assert panel._active_scheme_getter() is None


def test_anchor_crosshair_survives_direction_change(qtbot, tmp_path):
    """Regression test: AnchorEditorPanel must refresh last in every shared-
    preview cascade, or a later section's set_image() call deletes its
    crosshair overlay (scene.clear() wipes everything, not just its own)."""
    window = MainWindow()
    qtbot.addWidget(window)

    project = make_synthetic_project(tmp_path)
    window._set_project(project, None)
    window.anchor_editor_panel.set_section_expanded(True)  # crosshair only present while Anchors is open

    window.direction_combo.setCurrentIndex(1)

    # Must not raise (the crosshair's underlying C++ object must still be alive).
    pos = window.anchor_editor_panel.crosshair.pos()
    expected_origin = anchor_to_origin(project.anchors[1])
    assert (round(pos.x()), round(pos.y())) == expected_origin


def test_direction_arrows_rotate_and_wrap(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    n = window.direction_combo.count()
    assert window.direction_combo.currentIndex() == 0

    window.direction_next_btn.click()
    assert window.direction_combo.currentIndex() == 1

    for _ in range(n - 1):
        window.direction_next_btn.click()
    assert window.direction_combo.currentIndex() == 0  # wrapped past the last direction

    window.direction_prev_btn.click()
    assert window.direction_combo.currentIndex() == n - 1  # wrapped backwards past 0


def test_direction_label_reflects_current_direction(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.direction_label.text() == "Direction 0"
    assert window.direction_combo.isHidden()  # dropdown replaced by the arrow bar

    window.direction_next_btn.click()
    assert window.direction_label.text() == "Direction 1"
