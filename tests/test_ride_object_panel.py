"""Tests for ui/ride_object_panel.py: engine ride-object metadata authored
into object.json on build (see build/object_json.py's write_object_json),
not derivable from sprites/anchors/animation programs."""

from __future__ import annotations

from attraction_editor.ui.ride_object_panel import RideObjectPanel
from tests.fixtures.synthetic import make_synthetic_project


def _panel_with_project(qtbot, tmp_path):
    panel = RideObjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    panel.set_project(project)
    return panel, project


def test_fields_load_from_project(qtbot, tmp_path):
    panel = RideObjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    project.car_tab_offset = -20
    project.car_tab_scale = 0.5
    project.car_num_seats = 24
    project.car_visual = 1
    project.car_draw_order = 6
    project.capacity_text = "24 passengers"
    project.authors = ["Jack", "Custom Rides Inc."]
    project.version = "2.0"
    project.build_cost = 1500
    project.rating_excitement = 7
    project.rating_intensity = 6
    project.rating_nausea = 4

    panel.set_project(project)

    assert panel.car_tab_offset_spin.value() == -20
    assert panel.car_tab_scale_spin.value() == 0.5
    assert panel.car_num_seats_spin.value() == 24
    assert panel.car_visual_spin.value() == 1
    assert panel.car_draw_order_spin.value() == 6
    assert panel.capacity_text_edit.text() == "24 passengers"
    assert panel.authors_edit.text() == "Jack, Custom Rides Inc."
    assert panel.version_edit.text() == "2.0"
    assert panel.build_cost_spin.value() == 1500
    assert panel.rating_excitement_spin.value() == 7
    assert panel.rating_intensity_spin.value() == 6
    assert panel.rating_nausea_spin.value() == 4


def test_editing_fields_writes_to_project(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)

    panel.car_tab_offset_spin.setValue(10)
    panel.car_tab_scale_spin.setValue(0.25)
    panel.car_num_seats_spin.setValue(42)
    panel.car_visual_spin.setValue(2)
    panel.car_draw_order_spin.setValue(7)
    panel.capacity_text_edit.setText("42 passengers")
    panel.authors_edit.setText("Solo Author")
    panel.version_edit.setText("3.0")
    panel.build_cost_spin.setValue(2000)
    panel.rating_excitement_spin.setValue(8)
    panel.rating_intensity_spin.setValue(5)
    panel.rating_nausea_spin.setValue(3)

    assert project.car_tab_offset == 10
    assert project.car_tab_scale == 0.25
    assert project.car_num_seats == 42
    assert project.car_visual == 2
    assert project.car_draw_order == 7
    assert project.capacity_text == "42 passengers"
    assert project.authors == ["Solo Author"]
    assert project.version == "3.0"
    assert project.build_cost == 2000
    assert project.rating_excitement == 8
    assert project.rating_intensity == 5
    assert project.rating_nausea == 3


def test_draw_order_spin_clamped_to_valid_range(qtbot, tmp_path):
    panel, _project = _panel_with_project(qtbot, tmp_path)
    assert panel.car_draw_order_spin.maximum() == 15


def test_rating_spins_clamped_to_valid_range(qtbot, tmp_path):
    panel, _project = _panel_with_project(qtbot, tmp_path)
    assert panel.rating_excitement_spin.maximum() == 9.99
    assert panel.rating_intensity_spin.maximum() == 9.99
    assert panel.rating_nausea_spin.maximum() == 9.99


def test_rating_spins_support_two_decimal_places(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)

    panel.rating_excitement_spin.setValue(6.55)
    panel.rating_intensity_spin.setValue(4.25)
    panel.rating_nausea_spin.setValue(2.10)

    assert project.rating_excitement == 6.55
    assert project.rating_intensity == 4.25
    assert project.rating_nausea == 2.10


def test_authors_field_parses_comma_separated_list(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)

    panel.authors_edit.setText("Alice,  Bob ,Carol")

    assert project.authors == ["Alice", "Bob", "Carol"]


def test_editing_a_field_emits_project_changed(qtbot, tmp_path):
    panel, _project = _panel_with_project(qtbot, tmp_path)

    calls = []
    panel.projectChanged.connect(lambda: calls.append(True))
    panel.car_num_seats_spin.setValue(24)

    assert len(calls) == 1


def test_panel_disabled_until_project_set(qtbot):
    panel = RideObjectPanel()
    qtbot.addWidget(panel)

    assert not panel.isEnabled()
