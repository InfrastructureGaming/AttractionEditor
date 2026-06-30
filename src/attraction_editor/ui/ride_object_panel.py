"""Engine ride-object metadata, bound to a RideProject. Authored here and
written into object.json on build (see build/object_json.py's
write_object_json) - this is the data the tool can't derive from sprites,
anchors, or animation programs: how the engine physically configures this
ride's single flat-ride car.

Scoped to what actually matters for "flat_ride_generic" (this project's own
modular, self-contained flat-ride object type - see write_object_json's
hardcoded properties.type), not the full RideObject.cpp schema, most of
which (go-kart/chairlift/minigolf physics, etc.) doesn't apply to a flat
ride. carsPerFlatRide, frames.flat, recalculateSpriteBounds, and both
hasAdditionalColour flags are hardcoded in write_object_json rather than
exposed here - they're always the same for this tool's rides. Ride type and
rotation mode aren't exposed at all: type is always "flat_ride_generic",
and rotation mode only matters for rides without a flatRideAnimation block
(which every ride built here has, driven by Programs & Phases instead).
Car spacing/mass aren't exposed either - confirmed against Ride.cpp that
the engine only reads them for tracked-ride train validation, which never
runs once carsPerFlatRide is set."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.model.project import BREAKDOWN_TYPES, RideProject

# Display labels for every breakdown checkbox. The authorable ones come from
# BREAKDOWN_TYPES; the rest are shown disabled as a "coming later" affordance.
_BREAKDOWN_LABELS = {
    "safetyCutOut": "Safety cut-out",
    "controlFailure": "Control failure",
    "vehicleMalfunction": "Vehicle malfunction",
    "restraintsStuckClosed": "Restraints stuck closed",
    "restraintsStuckOpen": "Restraints stuck open",
    "doorsStuckClosed": "Doors stuck closed",
    "doorsStuckOpen": "Doors stuck open",
}

# Shown but not yet selectable: these drive a vehicle's restraint/door sprite
# state, which our phase-animated flat rides don't have, so they need the
# animation-bridge subsystem (freeze the declared restraint/door phase on
# breakdown) before they can be authored. Listed here purely so artists can see
# they're planned. Kept out of BREAKDOWN_TYPES so they can never be emitted.
_GATED_BREAKDOWNS = [
    "restraintsStuckClosed",
    "restraintsStuckOpen",
    "doorsStuckClosed",
    "doorsStuckOpen",
]
_GATED_BREAKDOWN_TOOLTIP = (
    "Not yet available: needs a declared restraints/doors animation phase for the\n"
    "breakdown to freeze. Coming in a later update."
)


class RideObjectPanel(QWidget):
    """Ride-object metadata form. Edits are written directly to the bound
    RideProject; `projectChanged` fires after any edit."""

    projectChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self._loading = False

        self.car_tab_offset_spin = QSpinBox()
        self.car_tab_offset_spin.setRange(-128, 127)
        self.car_tab_scale_spin = QDoubleSpinBox()
        self.car_tab_scale_spin.setRange(0.0, 0.5)
        self.car_tab_scale_spin.setSingleStep(0.1)
        self.car_num_seats_spin = QSpinBox()
        self.car_num_seats_spin.setRange(0, 255)
        self.car_visual_spin = QSpinBox()
        self.car_visual_spin.setRange(0, 255)
        self.car_draw_order_spin = QSpinBox()
        # 0-15 only - VehiclePaint.cpp indexes a fixed 16-entry bounding-box
        # table by this value and silently skips drawing the vehicle
        # entirely (no error) for anything >= 16, so the car would just
        # vanish in-game with no warning if this were left unclamped.
        self.car_draw_order_spin.setRange(0, 15)
        self.car_draw_order_spin.setToolTip(
            "Indexes a fixed 16-entry table the engine uses to draw this car - values\n"
            "above 15 aren't an error, they just make the car invisible in-game."
        )

        self.capacity_text_edit = QLineEdit()
        self.capacity_text_edit.setToolTip("Free text shown to the player, e.g. \"24 passengers\" - not derived from Num seats.")

        self.authors_edit = QLineEdit()
        self.authors_edit.setToolTip("Comma-separated list of author names.")
        self.version_edit = QLineEdit()

        self.build_cost_spin = QSpinBox()
        self.build_cost_spin.setRange(0, 1_000_000)
        self.build_cost_spin.setPrefix("£")
        self.build_cost_spin.setToolTip(
            "Whole pounds. 0 = no override - the engine keeps the generic flat-ride\n"
            "type's own default build cost instead."
        )

        self.bonus_value_spin = QSpinBox()
        self.bonus_value_spin.setRange(0, RideProject.BONUS_VALUE_MAX)
        self.bonus_value_spin.setToolTip(
            "How much an open, working copy of this ride raises the park's soft guest\n"
            "cap - the engine sums this over all open rides (Park.cpp). For reference:\n"
            "vanilla stalls ~5-15, flat rides ~35-50, coasters up to ~105. Default 35."
        )

        # 0-9 each with up to 2 decimal places, matching RideRating_t's own
        # fixed16_2dp precision (CustomRideLoader.cpp's toRideRating).
        # Defaults (3/2/1) match the engine's own fallback when "ratings" is
        # absent entirely, for reference: the vanilla "Twist" ride (a similar
        # gentle spinning ride) actually rates around excitement 1.1/
        # intensity 1.0/nausea 1.9 on the engine's own finer-grained scale.
        self.rating_excitement_spin = QDoubleSpinBox()
        self.rating_excitement_spin.setRange(0.0, 9.99)
        self.rating_excitement_spin.setDecimals(2)
        self.rating_excitement_spin.setSingleStep(0.01)
        self.rating_intensity_spin = QDoubleSpinBox()
        self.rating_intensity_spin.setRange(0.0, 9.99)
        self.rating_intensity_spin.setDecimals(2)
        self.rating_intensity_spin.setSingleStep(0.01)
        self.rating_nausea_spin = QDoubleSpinBox()
        self.rating_nausea_spin.setRange(0.0, 9.99)
        self.rating_nausea_spin.setDecimals(2)
        self.rating_nausea_spin.setSingleStep(0.01)

        # Breakdowns this ride can suffer. The master "Disable" checkbox is pure
        # UX sugar over an empty selection (a clearer affordance for arcades/
        # static rides): checking it clears + greys every breakdown, exactly the
        # same result as leaving them all unchecked.
        self.disable_breakdowns_check = QCheckBox("Disable breakdowns (this ride never breaks down)")
        self.breakdown_checks: dict[str, QCheckBox] = {}
        breakdown_layout = QVBoxLayout()
        breakdown_layout.addWidget(self.disable_breakdowns_check)
        for key in [*BREAKDOWN_TYPES, *_GATED_BREAKDOWNS]:
            check = QCheckBox(_BREAKDOWN_LABELS[key])
            if key not in BREAKDOWN_TYPES:
                check.setToolTip(_GATED_BREAKDOWN_TOOLTIP)
            self.breakdown_checks[key] = check
            breakdown_layout.addWidget(check)
        self.breakdown_box = QGroupBox("Breakdowns")
        self.breakdown_box.setLayout(breakdown_layout)

        form = QFormLayout()
        form.addRow("Car tab offset", self.car_tab_offset_spin)
        form.addRow("Car tab scale", self.car_tab_scale_spin)
        form.addRow("Num seats", self.car_num_seats_spin)
        form.addRow("Car visual", self.car_visual_spin)
        form.addRow("Draw order", self.car_draw_order_spin)
        form.addRow("Capacity text", self.capacity_text_edit)
        form.addRow("Authors", self.authors_edit)
        form.addRow("Version", self.version_edit)
        form.addRow("Build cost", self.build_cost_spin)
        form.addRow("Guest-cap weight", self.bonus_value_spin)
        form.addRow("Excitement rating", self.rating_excitement_spin)
        form.addRow("Intensity rating", self.rating_intensity_spin)
        form.addRow("Nausea rating", self.rating_nausea_spin)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.breakdown_box)
        self.setLayout(layout)

        self.car_tab_offset_spin.valueChanged.connect(self._on_field_changed)
        self.car_tab_scale_spin.valueChanged.connect(self._on_field_changed)
        self.car_num_seats_spin.valueChanged.connect(self._on_field_changed)
        self.car_visual_spin.valueChanged.connect(self._on_field_changed)
        self.car_draw_order_spin.valueChanged.connect(self._on_field_changed)
        self.capacity_text_edit.textChanged.connect(self._on_field_changed)
        self.authors_edit.textChanged.connect(self._on_field_changed)
        self.version_edit.textChanged.connect(self._on_field_changed)
        self.build_cost_spin.valueChanged.connect(self._on_field_changed)
        self.bonus_value_spin.valueChanged.connect(self._on_field_changed)
        self.rating_excitement_spin.valueChanged.connect(self._on_field_changed)
        self.rating_intensity_spin.valueChanged.connect(self._on_field_changed)
        self.rating_nausea_spin.valueChanged.connect(self._on_field_changed)

        self.disable_breakdowns_check.toggled.connect(self._on_disable_breakdowns_toggled)
        for check in self.breakdown_checks.values():
            check.toggled.connect(self._on_field_changed)

        self.setEnabled(False)

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self._loading = True
        try:
            self.car_tab_offset_spin.setValue(project.car_tab_offset)
            self.car_tab_scale_spin.setValue(project.car_tab_scale)
            self.car_num_seats_spin.setValue(project.car_num_seats)
            self.car_visual_spin.setValue(project.car_visual)
            self.car_draw_order_spin.setValue(project.car_draw_order)
            self.capacity_text_edit.setText(project.capacity_text)
            self.authors_edit.setText(", ".join(project.authors))
            self.version_edit.setText(project.version)
            self.build_cost_spin.setValue(project.build_cost)
            self.bonus_value_spin.setValue(project.bonus_value)
            self.rating_excitement_spin.setValue(project.rating_excitement)
            self.rating_intensity_spin.setValue(project.rating_intensity)
            self.rating_nausea_spin.setValue(project.rating_nausea)

            # Empty breakdown set => the master "Disable" affordance is on.
            self.disable_breakdowns_check.setChecked(not project.breakdowns)
            for key, check in self.breakdown_checks.items():
                check.setChecked(key in project.breakdowns)
        finally:
            self._loading = False
        self._apply_breakdown_enabled_state()
        self.setEnabled(True)

    def _apply_breakdown_enabled_state(self) -> None:
        """A breakdown checkbox is interactive only when it's an authorable type
        AND the master 'Disable' isn't overriding everything. Gated (future)
        types stay disabled regardless."""
        disabled_all = self.disable_breakdowns_check.isChecked()
        for key, check in self.breakdown_checks.items():
            check.setEnabled(not disabled_all and key in BREAKDOWN_TYPES)

    def _on_disable_breakdowns_toggled(self, checked: bool) -> None:
        if self._loading:
            return
        if checked:
            # Clear every selection (guarded so the per-box signals don't each
            # write the model), then grey them out.
            self._loading = True
            try:
                for check in self.breakdown_checks.values():
                    check.setChecked(False)
            finally:
                self._loading = False
        self._apply_breakdown_enabled_state()
        self._on_field_changed()

    def _on_field_changed(self, *_args) -> None:
        if self._loading or self.project is None:
            return
        self.project.car_tab_offset = self.car_tab_offset_spin.value()
        self.project.car_tab_scale = self.car_tab_scale_spin.value()
        self.project.car_num_seats = self.car_num_seats_spin.value()
        self.project.car_visual = self.car_visual_spin.value()
        self.project.car_draw_order = self.car_draw_order_spin.value()
        self.project.capacity_text = self.capacity_text_edit.text()
        self.project.authors = [name.strip() for name in self.authors_edit.text().split(",") if name.strip()]
        self.project.version = self.version_edit.text()
        self.project.build_cost = self.build_cost_spin.value()
        self.project.bonus_value = self.bonus_value_spin.value()
        self.project.rating_excitement = self.rating_excitement_spin.value()
        self.project.rating_intensity = self.rating_intensity_spin.value()
        self.project.rating_nausea = self.rating_nausea_spin.value()
        # Master disable => empty set. Otherwise the checked authorable types, in
        # BREAKDOWN_TYPES order so the emitted list is deterministic.
        if self.disable_breakdowns_check.isChecked():
            self.project.breakdowns = []
        else:
            self.project.breakdowns = [key for key in BREAKDOWN_TYPES if self.breakdown_checks[key].isChecked()]
        self.projectChanged.emit()
