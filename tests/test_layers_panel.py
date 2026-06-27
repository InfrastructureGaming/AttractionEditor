"""Tests for ui/layers_panel.py, focused on the Browse-button-commits-
immediately regression: clicking "Browse..." calls QLineEdit.setText(), which
does NOT fire editingFinished on its own (only Enter/focus-loss does) - the
on_browse() callback must emit it explicitly or the picked path never reaches
the model."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QPushButton

from attraction_editor.build.layers import composite_preview_frame
from attraction_editor.sprites.scanner import frame_path
from attraction_editor.ui import layers_panel as layers_panel_module
from attraction_editor.ui.layers_panel import LayersPanel
from attraction_editor.ui.preview_widget import PreviewWidget
from tests.fixtures.synthetic import make_synthetic_project, write_animated_layer_frames


def _browse_button_for(line_edit) -> QPushButton:
    """The Browse... button sharing `line_edit`'s row container (LayersPanel
    has two Browse buttons now - one for the layer's sprite folder, one for
    the selected rider car's - so finding "the" Browse button by text alone
    is ambiguous)."""
    candidates = [b for b in line_edit.parentWidget().findChildren(QPushButton) if b.text() == "Browse..."]
    assert len(candidates) == 1, "expected exactly one Browse... button sharing this field's row"
    return candidates[0]


def test_browse_button_commits_sprite_dir_without_extra_interaction(qtbot, tmp_path, monkeypatch):
    panel = LayersPanel()
    qtbot.addWidget(panel)

    project = make_synthetic_project(tmp_path)
    panel.set_project(project)
    panel.layer_list.setCurrentRow(0)

    new_dir = tmp_path / "Frames" / "PickedViaBrowse"
    new_dir.mkdir(parents=True)
    monkeypatch.setattr(
        layers_panel_module.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **kw: str(new_dir))
    )

    _browse_button_for(panel.sprite_dir_edit).click()

    # No Enter press, no focus change - the model must already reflect the
    # pick. Stored relative to project_dir, not the dialog's raw absolute
    # path - Layer.sprite_dir is always project_dir-relative (see
    # model.project.Layer), and storing it absolute corrupts every
    # downstream path build (sprite_builder.py's "../" car-path prefixing
    # assumes relative - this was a real, confirmed build failure).
    assert project.layers[0].sprite_dir == "Frames/PickedViaBrowse"
    assert panel.sprite_dir_edit.text() == "Frames/PickedViaBrowse"


def test_browse_button_picking_a_folder_outside_project_dir_falls_back_to_absolute(qtbot, tmp_path, monkeypatch):
    panel = LayersPanel()
    qtbot.addWidget(panel)

    project = make_synthetic_project(tmp_path)
    panel.set_project(project)
    panel.layer_list.setCurrentRow(0)

    outside_dir = tmp_path.parent / "OutsideProject"
    outside_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        layers_panel_module.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **kw: str(outside_dir))
    )

    _browse_button_for(panel.sprite_dir_edit).click()

    # No relative path expresses a folder outside project_dir - keep it absolute.
    assert project.layers[0].sprite_dir == str(outside_dir)


def test_browse_button_cancelled_dialog_does_not_clear_sprite_dir(qtbot, tmp_path, monkeypatch):
    panel = LayersPanel()
    qtbot.addWidget(panel)

    project = make_synthetic_project(tmp_path)
    original_dir = project.layers[0].sprite_dir
    panel.set_project(project)
    panel.layer_list.setCurrentRow(0)

    monkeypatch.setattr(layers_panel_module.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **kw: ""))

    _browse_button_for(panel.sprite_dir_edit).click()

    assert project.layers[0].sprite_dir == original_dir


def test_car_browse_button_commits_sprite_dir_without_extra_interaction(qtbot, tmp_path, monkeypatch):
    """Rider cars moved into LayersPanel (from ProjectPanel) - same
    Browse-commits-immediately fix must hold for the car sprite folder field."""
    panel = LayersPanel()
    qtbot.addWidget(panel)

    project = make_synthetic_project(tmp_path, num_cars=1)
    panel.set_project(project)
    panel.car_list.setCurrentRow(0)

    new_dir = tmp_path / "Frames" / "Riders" / "PickedViaBrowse"
    new_dir.mkdir(parents=True)
    monkeypatch.setattr(
        layers_panel_module.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **kw: str(new_dir))
    )

    _browse_button_for(panel.car_sprite_dir_edit).click()

    assert project.cars[0].sprite_dir == "Frames/Riders/PickedViaBrowse"
    assert panel.car_sprite_dir_edit.text() == "Frames/Riders/PickedViaBrowse"


def _panel_with_preview(qtbot, project):
    panel = LayersPanel()
    qtbot.addWidget(panel)
    captured: list = []
    preview = PreviewWidget()
    preview.set_image = lambda img: captured.append(img)  # capture the final composite
    panel.set_preview_widget(preview)
    direction_combo = QComboBox()
    direction_combo.addItems([f"Direction {d}" for d in range(4)])
    panel.set_direction_combo(direction_combo)
    panel.set_project(project)
    return panel, captured


def test_preview_overlays_rider_cars_on_the_structure(qtbot, tmp_path):
    """The Layers section's preview must show the rider cars composited on top
    of the structure (they share the structure's per-direction anchor, so they
    align pixel-for-pixel) - previously it rendered structure layers only, so
    riders never appeared in this section's preview at all."""
    project = make_synthetic_project(tmp_path, num_cars=1)
    # Re-render the car frames with a distinct, fully-opaque seed so the
    # overlay is detectable: it completely covers the structure where present.
    write_animated_layer_frames(project.project_dir / project.cars[0].sprite_dir, seed=99)

    panel, captured = _panel_with_preview(qtbot, project)

    assert captured, "preview should have been rendered on set_project"
    rendered = captured[-1].convert("RGBA")
    structure_only = composite_preview_frame(project, direction=0, frame=0).convert("RGBA")
    car_frame = frame_path(project.project_dir / project.cars[0].sprite_dir, 0, 0)
    from PIL import Image

    with Image.open(car_frame) as img:
        car_rgba = img.convert("RGBA")

    # The fully-opaque car overlay replaces the structure: the render matches
    # the car frame, not the structure-only composite.
    assert list(rendered.getdata()) == list(car_rgba.getdata())
    assert list(rendered.getdata()) != list(structure_only.getdata())


def test_preview_without_cars_is_structure_only(qtbot, tmp_path):
    """With no rider cars, the preview is exactly the structure composite -
    the overlay loop is a no-op."""
    project = make_synthetic_project(tmp_path, num_cars=0)
    panel, captured = _panel_with_preview(qtbot, project)

    rendered = captured[-1].convert("RGBA")
    structure_only = composite_preview_frame(project, direction=0, frame=0).convert("RGBA")
    assert list(rendered.getdata()) == list(structure_only.getdata())
