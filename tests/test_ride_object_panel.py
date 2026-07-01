"""Tests for ui/ride_object_panel.py: engine ride-object metadata authored
into object.json on build (see build/object_json.py's write_object_json),
not derivable from sprites/anchors/animation programs."""

from __future__ import annotations

from attraction_editor.model.project import BREAKDOWN_TYPES
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


def test_bonus_value_spin_loads_and_commits(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)
    assert panel.bonus_value_spin.value() == 35  # default

    panel.bonus_value_spin.setValue(60)
    assert project.bonus_value == 60


def test_bonus_value_spin_clamped_to_max(qtbot, tmp_path):
    panel, _project = _panel_with_project(qtbot, tmp_path)
    assert panel.bonus_value_spin.maximum() == 100


def test_upkeep_cost_spin_loads_and_commits(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)
    assert panel.upkeep_cost_spin.value() == 50  # default

    panel.upkeep_cost_spin.setValue(200)
    assert project.upkeep_cost == 200


def test_upkeep_cost_spin_clamped_to_max(qtbot, tmp_path):
    panel, _project = _panel_with_project(qtbot, tmp_path)
    assert panel.upkeep_cost_spin.maximum() == 500


def test_shuffle_load_check_loads_and_commits(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)
    assert panel.shuffle_load_check.isChecked() is False  # default

    panel.shuffle_load_check.setChecked(True)
    assert project.shuffle_load_order is True


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


def test_breakdown_checks_load_from_project(qtbot, tmp_path):
    panel = RideObjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    project.breakdowns = ["safetyCutOut", "vehicleMalfunction"]

    panel.set_project(project)

    assert panel.breakdown_checks["safetyCutOut"].isChecked()
    assert panel.breakdown_checks["vehicleMalfunction"].isChecked()
    assert not panel.breakdown_checks["controlFailure"].isChecked()
    assert not panel.disable_breakdowns_check.isChecked()


def test_checking_a_breakdown_writes_to_project(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)

    panel.breakdown_checks["controlFailure"].setChecked(True)

    assert "controlFailure" in project.breakdowns


def test_emitted_breakdowns_follow_canonical_order(qtbot, tmp_path):
    """Regardless of the order boxes are toggled, the stored list is in
    BREAKDOWN_TYPES order so the built object.json is deterministic."""
    panel, project = _panel_with_project(qtbot, tmp_path)  # default: safetyCutOut

    panel.breakdown_checks["vehicleMalfunction"].setChecked(True)
    panel.breakdown_checks["controlFailure"].setChecked(True)

    assert project.breakdowns == BREAKDOWN_TYPES


def test_master_disable_clears_and_greys_all_breakdowns(qtbot, tmp_path):
    panel, project = _panel_with_project(qtbot, tmp_path)
    panel.breakdown_checks["controlFailure"].setChecked(True)

    panel.disable_breakdowns_check.setChecked(True)

    assert project.breakdowns == []
    for key in BREAKDOWN_TYPES:
        assert not panel.breakdown_checks[key].isChecked()
        assert not panel.breakdown_checks[key].isEnabled()


def test_unchecking_master_disable_re_enables_authorable_breakdowns(qtbot, tmp_path):
    panel, _project = _panel_with_project(qtbot, tmp_path)
    panel.disable_breakdowns_check.setChecked(True)

    panel.disable_breakdowns_check.setChecked(False)

    for key in BREAKDOWN_TYPES:
        assert panel.breakdown_checks[key].isEnabled()


def test_empty_breakdowns_loads_as_master_disabled(qtbot, tmp_path):
    panel = RideObjectPanel()
    qtbot.addWidget(panel)
    project = make_synthetic_project(tmp_path)
    project.breakdowns = []

    panel.set_project(project)

    assert panel.disable_breakdowns_check.isChecked()
    for key in BREAKDOWN_TYPES:
        assert not panel.breakdown_checks[key].isEnabled()


def test_gated_breakdowns_are_shown_but_never_authorable(qtbot, tmp_path):
    """restraints/doors are visible as a 'coming later' affordance but disabled
    and absent from BREAKDOWN_TYPES, so they can never be emitted."""
    panel, _project = _panel_with_project(qtbot, tmp_path)

    for key in ("restraintsStuckClosed", "restraintsStuckOpen", "doorsStuckClosed", "doorsStuckOpen"):
        assert key in panel.breakdown_checks
        assert not panel.breakdown_checks[key].isEnabled()
        assert key not in BREAKDOWN_TYPES
