"""Tests for ui/colour_preview_panel.py: the session-only "active preview
scheme" concept (Apply Scheme / Disable Colours), which is read by every
other preview-rendering panel via get_active_scheme()/set_active_scheme_getter
but never written to the project or the shipped sprites."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox

from attraction_editor.model.project import ColourScheme
from attraction_editor.ui.colour_preview_panel import ColourPreviewPanel
from attraction_editor.ui.preview_widget import PreviewWidget
from tests.fixtures.synthetic import make_synthetic_project


def _panel_with_project(qtbot, tmp_path, *, with_preview: bool = False):
    panel = ColourPreviewPanel()
    qtbot.addWidget(panel)

    if with_preview:
        direction_combo = QComboBox()
        direction_combo.addItems([f"Direction {d}" for d in range(4)])
        panel.set_preview_widget(PreviewWidget())
        panel.set_direction_combo(direction_combo)

    project = make_synthetic_project(tmp_path)
    project.colour_schemes = [
        ColourScheme(trim_colour="bright_red", tertiary_colour="white"),
        ColourScheme(trim_colour="moss_green", tertiary_colour="yellow"),
    ]
    panel.set_project(project)
    return panel, project


def test_active_scheme_starts_none(qtbot, tmp_path):
    panel, _project = _panel_with_project(qtbot, tmp_path)
    assert panel.get_active_scheme() is None
    assert "disabled" in panel.active_label.text().lower()


def test_selecting_a_scheme_does_not_apply_it(qtbot, tmp_path):
    """Browsing the list only loads the scheme into the form fields - it
    must not change the active preview scheme on its own."""
    panel, project = _panel_with_project(qtbot, tmp_path)

    panel.scheme_list.setCurrentRow(1)
    assert panel.trim_combo.currentText() == "moss_green"
    assert panel.get_active_scheme() is None


def test_apply_scheme_sets_active_scheme(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)
    panel.scheme_list.setCurrentRow(1)

    calls = []
    panel.activeSchemeChanged.connect(lambda: calls.append(True))
    panel._on_apply_scheme()

    assert panel.get_active_scheme() is project.colour_schemes[1]
    assert len(calls) == 1
    assert "moss_green" in panel.active_label.text()


def test_disable_colours_clears_active_scheme(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)
    panel.scheme_list.setCurrentRow(0)
    panel._on_apply_scheme()
    assert panel.get_active_scheme() is not None

    calls = []
    panel.activeSchemeChanged.connect(lambda: calls.append(True))
    panel._on_disable_colours()

    assert panel.get_active_scheme() is None
    assert len(calls) == 1
    assert "disabled" in panel.active_label.text().lower()


def test_applied_scheme_persists_through_further_browsing(qtbot, tmp_path):
    """Once applied, the active scheme must stay applied even as the user
    selects other rows to look at/edit them, until Apply or Disable fires again."""
    panel, project = _panel_with_project(qtbot, tmp_path)
    panel.scheme_list.setCurrentRow(0)
    panel._on_apply_scheme()
    applied = panel.get_active_scheme()

    panel.scheme_list.setCurrentRow(1)  # just browsing
    assert panel.get_active_scheme() is applied

    panel.scheme_list.setCurrentRow(0)
    assert panel.get_active_scheme() is applied


def test_removing_the_active_scheme_disables_colours(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)
    panel.scheme_list.setCurrentRow(0)
    panel._on_apply_scheme()

    calls = []
    panel.activeSchemeChanged.connect(lambda: calls.append(True))
    panel.scheme_list.setCurrentRow(0)
    panel._on_remove_scheme()

    assert panel.get_active_scheme() is None
    assert len(calls) == 1


def test_removing_a_different_scheme_keeps_active_scheme(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)
    panel.scheme_list.setCurrentRow(0)
    panel._on_apply_scheme()
    applied = panel.get_active_scheme()

    panel.scheme_list.setCurrentRow(1)
    panel._on_remove_scheme()

    assert panel.get_active_scheme() is applied


def test_editing_the_active_scheme_is_reflected_live(qtbot, tmp_path):
    """Editing the trim/tertiary combos while the active scheme is selected
    mutates the same object get_active_scheme() returns - no extra plumbing
    needed, just object identity."""
    panel, project = _panel_with_project(qtbot, tmp_path)
    panel.scheme_list.setCurrentRow(0)
    panel._on_apply_scheme()

    panel.trim_combo.setCurrentText("black")

    assert panel.get_active_scheme().trim_colour == "black"
    assert "black" in panel.active_label.text()


def test_editing_a_non_active_scheme_does_not_affect_active_scheme(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)
    panel.scheme_list.setCurrentRow(0)
    panel._on_apply_scheme()
    applied = panel.get_active_scheme()
    applied_trim_before = applied.trim_colour

    panel.scheme_list.setCurrentRow(1)
    panel.trim_combo.setCurrentText("black")

    assert applied.trim_colour == applied_trim_before


def test_set_project_resets_active_scheme(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)
    panel.scheme_list.setCurrentRow(0)
    panel._on_apply_scheme()
    assert panel.get_active_scheme() is not None

    other_project = make_synthetic_project(tmp_path / "other")
    panel.set_project(other_project)

    assert panel.get_active_scheme() is None


def test_dither_checkbox_starts_unchecked(qtbot, tmp_path):
    """Moved here from Animation - dithering and colour remapping are both
    palette-level concerns best judged together."""
    panel, _project = _panel_with_project(qtbot, tmp_path)
    assert not panel.dither_check.isChecked()


def test_toggling_dither_checkbox_changes_the_rendered_preview(qtbot, tmp_path):
    panel, _project = _panel_with_project(qtbot, tmp_path, with_preview=True)
    panel.scheme_list.setCurrentRow(0)
    panel._on_apply_scheme()  # populates the preview - nothing renders until applied

    panel.dither_check.setChecked(False)
    without_dither = bytes(panel.preview_widget.scene.items()[0].pixmap().toImage().bits())

    panel.dither_check.setChecked(True)
    with_dither = bytes(panel.preview_widget.scene.items()[0].pixmap().toImage().bits())

    assert without_dither != with_dither


def test_catch_tolerance_spinboxes_load_from_project(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)
    project.trim_catch_tolerance = 15
    project.tertiary_catch_tolerance = -7

    panel.set_project(project)

    assert panel.trim_tolerance_spin.value() == 15
    assert panel.tertiary_tolerance_spin.value() == -7


def test_editing_catch_tolerance_writes_to_project(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)

    panel.trim_tolerance_spin.setValue(20)
    panel.tertiary_tolerance_spin.setValue(-15)

    assert project.trim_catch_tolerance == 20
    assert project.tertiary_catch_tolerance == -15


def test_editing_catch_tolerance_emits_catch_tolerance_changed(qtbot, tmp_path):
    panel, _project = _panel_with_project(qtbot, tmp_path)

    calls = []
    panel.catchToleranceChanged.connect(lambda: calls.append(True))
    panel.trim_tolerance_spin.setValue(30)

    assert len(calls) == 1


def test_set_project_does_not_spuriously_emit_catch_tolerance_changed(qtbot, tmp_path):
    """Loading a project's existing tolerance into the spinboxes must not
    look like a user edit (the _loading guard) - otherwise switching
    projects would needlessly re-trigger every other panel's refresh."""
    panel, project = _panel_with_project(qtbot, tmp_path)
    project.trim_catch_tolerance = 42

    calls = []
    panel.catchToleranceChanged.connect(lambda: calls.append(True))
    panel.set_project(project)

    assert len(calls) == 0
