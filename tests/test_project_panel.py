"""Tests for ui/project_panel.py's single "Sprite height" field, replacing
the old negative/positive split - where the origin sits within that height
is the Anchors section's job now (see RideProject.sprite_height /
build/object_json.py's invalidation_bounds)."""

from __future__ import annotations

from PIL import Image

from attraction_editor.ui.project_panel import ProjectPanel
from tests.fixtures.synthetic import make_synthetic_project


def test_sprite_height_spin_loads_from_project(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    project.sprite_height = 265

    panel.set_project(project)

    assert panel.sprite_height_spin.value() == 265


def test_editing_sprite_height_spin_writes_to_project(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    panel.set_project(project)

    panel.sprite_height_spin.setValue(265)

    assert project.sprite_height == 265


def test_editing_sprite_height_spin_emits_project_changed(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    panel.set_project(project)

    calls = []
    panel.projectChanged.connect(lambda: calls.append(True))
    panel.sprite_height_spin.setValue(200)

    assert len(calls) == 1


def test_panel_has_no_separate_negative_positive_fields(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    assert not hasattr(panel, "sprite_height_negative_spin")
    assert not hasattr(panel, "sprite_height_positive_spin")


def test_footprint_spins_load_from_project(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    project.base_footprint_width = 1
    project.base_footprint_length = 4

    panel.set_project(project)

    assert panel.footprint_width_spin.value() == 1
    assert panel.footprint_length_spin.value() == 4
    assert panel.footprint_error_label.text() == ""


def test_editing_footprint_spins_writes_to_project(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    panel.set_project(project)

    panel.footprint_width_spin.setValue(2)
    panel.footprint_length_spin.setValue(8)

    assert project.base_footprint_width == 2
    assert project.base_footprint_length == 8
    assert panel.footprint_error_label.text() == ""


def test_footprint_exceeding_64_tiles_shows_error_and_does_not_write(qtbot, tmp_path):
    """RideProject only validates the 64-tile cap at construction, not on
    plain attribute assignment - the panel must enforce it itself so an
    invalid combination never reaches the model (and would otherwise only
    surface as a crash much later, on the next save/load round-trip)."""
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    project.base_footprint_width = 6
    project.base_footprint_length = 6
    panel.set_project(project)

    panel.footprint_width_spin.setValue(8)  # 8x6 = 48 tiles - still valid, commits
    panel.footprint_length_spin.setValue(9)  # 8x9 = 72 tiles - over the cap

    assert "72" in panel.footprint_error_label.text()
    assert "64" in panel.footprint_error_label.text()
    # width's own edit committed (8x6 was valid at the time); length's edit
    # didn't, since 8x9 isn't - the model never holds an invalid combination.
    assert project.base_footprint_width == 8
    assert project.base_footprint_length == 6


def test_thumbnail_path_loads_from_project(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    project.thumbnail_path = "thumb.png"

    panel.set_project(project)

    assert panel.thumbnail_edit.text() == "thumb.png"


def test_editing_thumbnail_path_writes_to_project(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    panel.set_project(project)

    panel.thumbnail_edit.setText("Frames/thumb.png")

    assert project.thumbnail_path == "Frames/thumb.png"


def test_blank_thumbnail_clears_to_none_with_auto_preview(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    panel.set_project(project)

    panel.thumbnail_edit.setText("nonexistent.png")
    assert project.thumbnail_path == "nonexistent.png"
    assert panel.thumbnail_preview.text() == "(missing)"

    panel.thumbnail_edit.setText("")
    assert project.thumbnail_path is None
    assert panel.thumbnail_preview.text() == "(auto)"


def test_valid_thumbnail_file_renders_preview_pixmap(qtbot, tmp_path):
    project = make_synthetic_project(tmp_path)
    Image.new("RGBA", (200, 200), (255, 0, 0, 255)).save(project.project_dir / "thumb.png")

    panel = ProjectPanel()
    qtbot.addWidget(panel)
    panel.set_project(project)

    panel.thumbnail_edit.setText("thumb.png")

    assert not panel.thumbnail_preview.pixmap().isNull()


def test_footprint_error_clears_once_back_within_the_limit(qtbot, tmp_path):
    panel = ProjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    panel.set_project(project)

    panel.footprint_width_spin.setValue(8)
    panel.footprint_length_spin.setValue(9)
    assert panel.footprint_error_label.text() != ""

    panel.footprint_length_spin.setValue(8)  # back to 64 tiles - within the cap

    assert panel.footprint_error_label.text() == ""
    assert project.base_footprint_width == 8
    assert project.base_footprint_length == 8
