"""Parametric motion editor: authors RideProject.motion - an ordered list of
swing/loop segment dicts that the build compiles into an explicit time-to-sprite
map over the angle atlas (see build/motion.py + build/object_json's
flat_ride_animation_block). When any segments are present they DRIVE the
animation instead of the range-based Programs & Phases.

No live preview here (the motion is validated in-game against the rendered angle
atlas); this panel just authors the spec. Edits write straight to the bound
RideProject and fire `projectChanged`."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.model.project import RideProject

_EASINGS = ["sine", "linear"]

# Defaults for a freshly-added segment - a modest swing and a single loop.
_DEFAULT_SWING = {"kind": "swing", "amplitude": 30, "cycles": 1, "ticks": 90, "easing": "sine"}
_DEFAULT_LOOP = {"kind": "loop", "turns": 1, "ticks": 360, "direction": 1, "easing": "linear"}


class MotionEditorPanel(QWidget):
    """Segment list (top) + per-segment parameter fields (bottom). Segments are
    stored as plain dicts on RideProject.motion (see build/motion.py)."""

    projectChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self._loading = False

        self.segment_list = QListWidget()
        add_swing_btn = QPushButton("Add swing")
        add_loop_btn = QPushButton("Add loop")
        remove_btn = QPushButton("Remove")
        up_btn = QPushButton("Move up")
        down_btn = QPushButton("Move down")

        add_row = QHBoxLayout()
        add_row.addWidget(add_swing_btn)
        add_row.addWidget(add_loop_btn)
        order_row = QHBoxLayout()
        order_row.addWidget(remove_btn)
        order_row.addWidget(up_btn)
        order_row.addWidget(down_btn)

        # Shared fields.
        self.ticks_spin = QSpinBox()
        self.ticks_spin.setRange(1, 100000)
        self.ticks_spin.setToolTip("Total game ticks this segment lasts - one atlas frame is chosen per tick.")
        self.easing_combo = QComboBox()
        self.easing_combo.addItems(_EASINGS)

        # Swing-only fields (in their own widget so the whole row hides cleanly).
        self.amplitude_spin = QSpinBox()
        self.amplitude_spin.setRange(0, 360)
        self.amplitude_spin.setToolTip("Peak swing angle from rest, in degrees.")
        self.cycles_spin = QSpinBox()
        self.cycles_spin.setRange(1, 1000)
        self.cycles_spin.setToolTip("Complete back-and-forth swings within this segment.")
        self.swing_fields = QWidget()
        swing_form = QFormLayout(self.swing_fields)
        swing_form.setContentsMargins(0, 0, 0, 0)
        swing_form.addRow("Amplitude (deg)", self.amplitude_spin)
        swing_form.addRow("Cycles", self.cycles_spin)

        # Loop-only fields.
        self.turns_spin = QSpinBox()
        self.turns_spin.setRange(1, 1000)
        self.turns_spin.setToolTip("Complete 360-degree revolutions in this segment.")
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Forward (+)", "Reverse (-)"])
        self.loop_fields = QWidget()
        loop_form = QFormLayout(self.loop_fields)
        loop_form.setContentsMargins(0, 0, 0, 0)
        loop_form.addRow("Turns", self.turns_spin)
        loop_form.addRow("Direction", self.direction_combo)

        shared_form = QFormLayout()
        shared_form.addRow("Ticks", self.ticks_spin)
        shared_form.addRow("Easing", self.easing_combo)

        layout = QVBoxLayout()
        layout.addWidget(self.segment_list)
        layout.addLayout(add_row)
        layout.addLayout(order_row)
        layout.addWidget(self.swing_fields)
        layout.addWidget(self.loop_fields)
        layout.addLayout(shared_form)
        self.setLayout(layout)

        self.segment_list.currentRowChanged.connect(self._on_segment_selected)
        add_swing_btn.clicked.connect(lambda: self._add_segment(dict(_DEFAULT_SWING)))
        add_loop_btn.clicked.connect(lambda: self._add_segment(dict(_DEFAULT_LOOP)))
        remove_btn.clicked.connect(self._on_remove)
        up_btn.clicked.connect(lambda: self._move(-1))
        down_btn.clicked.connect(lambda: self._move(1))
        for spin in (self.ticks_spin, self.amplitude_spin, self.cycles_spin, self.turns_spin):
            spin.valueChanged.connect(self._on_field_changed)
        self.easing_combo.currentIndexChanged.connect(self._on_field_changed)
        self.direction_combo.currentIndexChanged.connect(self._on_field_changed)

        self.setEnabled(False)

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self.setEnabled(True)
        self._reload_list()

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _label_for(seg: dict) -> str:
        if seg.get("kind") == "swing":
            return f"Swing  {seg.get('amplitude', 0)} deg x{seg.get('cycles', 1)}  ({seg.get('ticks', 0)}t, {seg.get('easing', 'sine')})"
        if seg.get("kind") == "loop":
            arrow = "+" if seg.get("direction", 1) >= 0 else "-"
            return f"Loop  x{seg.get('turns', 1)} {arrow}  ({seg.get('ticks', 0)}t, {seg.get('easing', 'linear')})"
        return str(seg)

    def _current_segment(self) -> dict | None:
        if self.project is None:
            return None
        row = self.segment_list.currentRow()
        if 0 <= row < len(self.project.motion):
            return self.project.motion[row]
        return None

    def _reload_list(self) -> None:
        current = self.segment_list.currentRow()
        self._loading = True
        try:
            self.segment_list.clear()
            if self.project is not None:
                for seg in self.project.motion:
                    self.segment_list.addItem(self._label_for(seg))
        finally:
            self._loading = False
        count = self.segment_list.count()
        if count:
            self.segment_list.setCurrentRow(min(max(current, 0), count - 1))
        else:
            self._on_segment_selected(-1)

    def _on_segment_selected(self, _row: int) -> None:
        seg = self._current_segment()
        is_swing = seg is not None and seg.get("kind") == "swing"
        is_loop = seg is not None and seg.get("kind") == "loop"
        self.swing_fields.setVisible(is_swing)
        self.loop_fields.setVisible(is_loop)
        if seg is None:
            return
        self._loading = True
        try:
            self.ticks_spin.setValue(int(seg.get("ticks", 0)))
            self.easing_combo.setCurrentText(str(seg.get("easing", "sine")))
            if is_swing:
                self.amplitude_spin.setValue(int(seg.get("amplitude", 0)))
                self.cycles_spin.setValue(int(seg.get("cycles", 1)))
            elif is_loop:
                self.turns_spin.setValue(int(seg.get("turns", 1)))
                self.direction_combo.setCurrentIndex(0 if seg.get("direction", 1) >= 0 else 1)
        finally:
            self._loading = False

    def _add_segment(self, seg: dict) -> None:
        if self.project is None:
            return
        self.project.motion.append(seg)
        self._reload_list()
        self.segment_list.setCurrentRow(len(self.project.motion) - 1)
        self.projectChanged.emit()

    def _on_remove(self) -> None:
        if self.project is None:
            return
        row = self.segment_list.currentRow()
        if 0 <= row < len(self.project.motion):
            del self.project.motion[row]
            self._reload_list()
            self.projectChanged.emit()

    def _move(self, delta: int) -> None:
        if self.project is None:
            return
        row = self.segment_list.currentRow()
        other = row + delta
        if 0 <= row < len(self.project.motion) and 0 <= other < len(self.project.motion):
            motion = self.project.motion
            motion[row], motion[other] = motion[other], motion[row]
            self._reload_list()
            self.segment_list.setCurrentRow(other)
            self.projectChanged.emit()

    def _on_field_changed(self, *_args) -> None:
        if self._loading:
            return
        seg = self._current_segment()
        if seg is None:
            return
        seg["ticks"] = self.ticks_spin.value()
        seg["easing"] = self.easing_combo.currentText()
        if seg.get("kind") == "swing":
            seg["amplitude"] = self.amplitude_spin.value()
            seg["cycles"] = self.cycles_spin.value()
        elif seg.get("kind") == "loop":
            seg["turns"] = self.turns_spin.value()
            seg["direction"] = 1 if self.direction_combo.currentIndex() == 0 else -1
        self.segment_list.item(self.segment_list.currentRow()).setText(self._label_for(seg))
        self.projectChanged.emit()
