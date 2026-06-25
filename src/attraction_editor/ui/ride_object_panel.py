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
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QLineEdit, QSpinBox, QVBoxLayout, QWidget

from attraction_editor.model.project import RideProject


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
        form.addRow("Excitement rating", self.rating_excitement_spin)
        form.addRow("Intensity rating", self.rating_intensity_spin)
        form.addRow("Nausea rating", self.rating_nausea_spin)

        layout = QVBoxLayout()
        layout.addLayout(form)
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
        self.rating_excitement_spin.valueChanged.connect(self._on_field_changed)
        self.rating_intensity_spin.valueChanged.connect(self._on_field_changed)
        self.rating_nausea_spin.valueChanged.connect(self._on_field_changed)

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
            self.rating_excitement_spin.setValue(project.rating_excitement)
            self.rating_intensity_spin.setValue(project.rating_intensity)
            self.rating_nausea_spin.setValue(project.rating_nausea)
        finally:
            self._loading = False
        self.setEnabled(True)

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
        self.project.rating_excitement = self.rating_excitement_spin.value()
        self.project.rating_intensity = self.rating_intensity_spin.value()
        self.project.rating_nausea = self.rating_nausea_spin.value()
        self.projectChanged.emit()
