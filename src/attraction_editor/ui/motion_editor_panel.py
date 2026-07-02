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
    QCheckBox,
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

# Defaults for a freshly-added segment. Frames defaults to the Loop-O-Plane's
# door-close (391 -> 361); flip start/end for door-open.
_DEFAULT_SWING = {"kind": "swing", "amplitude": 30, "cycles": 1, "ticks": 90, "easing": "sine"}
_DEFAULT_LOOP = {"kind": "loop", "turns": 1, "ticks": 360, "direction": 1, "easing": "linear", "repeatable": False}
_DEFAULT_FRAMES = {"kind": "frames", "start": 391, "end": 361, "ticks_per_frame": 1}


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
        add_frames_btn = QPushButton("Add frames")
        remove_btn = QPushButton("Remove")
        up_btn = QPushButton("Move up")
        down_btn = QPushButton("Move down")

        add_row = QHBoxLayout()
        add_row.addWidget(add_swing_btn)
        add_row.addWidget(add_loop_btn)
        add_row.addWidget(add_frames_btn)
        order_row = QHBoxLayout()
        order_row.addWidget(remove_btn)
        order_row.addWidget(up_btn)
        order_row.addWidget(down_btn)

        # Shared ticks/easing (swing + loop; NOT frames, which times per-frame),
        # wrapped so the whole block hides for a frames segment.
        self.ticks_spin = QSpinBox()
        self.ticks_spin.setRange(1, 100000)
        self.ticks_spin.setToolTip("Total game ticks this segment lasts - one atlas frame is chosen per tick.")
        self.easing_combo = QComboBox()
        self.easing_combo.addItems(_EASINGS)
        self.shared_fields = QWidget()
        shared_form = QFormLayout(self.shared_fields)
        shared_form.setContentsMargins(0, 0, 0, 0)
        shared_form.addRow("Ticks", self.ticks_spin)
        shared_form.addRow("Easing", self.easing_combo)

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
        self.repeatable_check = QCheckBox("Operator-controlled (repeat)")
        self.repeatable_check.setToolTip(
            "Repeat this loop until the ride's 'number of rotations' operating\n"
            "setting is met (the operator's spinner drives the count). Splits the\n"
            "motion into its own program phase."
        )
        self.loop_fields = QWidget()
        loop_form = QFormLayout(self.loop_fields)
        loop_form.setContentsMargins(0, 0, 0, 0)
        loop_form.addRow("Turns", self.turns_spin)
        loop_form.addRow("Direction", self.direction_combo)
        loop_form.addRow("", self.repeatable_check)

        # Frames-only fields (raw frame-range playback: doors etc.).
        self.frames_start_spin = QSpinBox()
        self.frames_start_spin.setRange(0, 100000)
        self.frames_start_spin.setToolTip("First atlas frame to play (start > end plays in reverse).")
        self.frames_end_spin = QSpinBox()
        self.frames_end_spin.setRange(0, 100000)
        self.frames_end_spin.setToolTip("Last atlas frame to play (inclusive).")
        self.frame_ticks_spin = QSpinBox()
        self.frame_ticks_spin.setRange(1, 1000)
        self.frame_ticks_spin.setToolTip("Game ticks to hold each frame (higher = slower playback).")
        self.frames_fields = QWidget()
        frames_form = QFormLayout(self.frames_fields)
        frames_form.setContentsMargins(0, 0, 0, 0)
        frames_form.addRow("From frame", self.frames_start_spin)
        frames_form.addRow("To frame", self.frames_end_spin)
        frames_form.addRow("Ticks / frame", self.frame_ticks_spin)

        layout = QVBoxLayout()
        layout.addWidget(self.segment_list)
        layout.addLayout(add_row)
        layout.addLayout(order_row)
        layout.addWidget(self.swing_fields)
        layout.addWidget(self.loop_fields)
        layout.addWidget(self.frames_fields)
        layout.addWidget(self.shared_fields)
        self.setLayout(layout)

        self.segment_list.currentRowChanged.connect(self._on_segment_selected)
        add_swing_btn.clicked.connect(lambda: self._add_segment(dict(_DEFAULT_SWING)))
        add_loop_btn.clicked.connect(lambda: self._add_segment(dict(_DEFAULT_LOOP)))
        add_frames_btn.clicked.connect(lambda: self._add_segment(dict(_DEFAULT_FRAMES)))
        remove_btn.clicked.connect(self._on_remove)
        up_btn.clicked.connect(lambda: self._move(-1))
        down_btn.clicked.connect(lambda: self._move(1))
        for spin in (
            self.ticks_spin,
            self.amplitude_spin,
            self.cycles_spin,
            self.turns_spin,
            self.frames_start_spin,
            self.frames_end_spin,
            self.frame_ticks_spin,
        ):
            spin.valueChanged.connect(self._on_field_changed)
        self.easing_combo.currentIndexChanged.connect(self._on_field_changed)
        self.direction_combo.currentIndexChanged.connect(self._on_field_changed)
        self.repeatable_check.toggled.connect(self._on_field_changed)

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
            rep = ", operator" if seg.get("repeatable") else ""
            return f"Loop  x{seg.get('turns', 1)} {arrow}  ({seg.get('ticks', 0)}t, {seg.get('easing', 'linear')}{rep})"
        if seg.get("kind") == "frames":
            return f"Frames  {seg.get('start', 0)} -> {seg.get('end', 0)}  ({seg.get('ticks_per_frame', 1)}t/frame)"
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
        kind = seg.get("kind") if seg is not None else None
        is_swing, is_loop, is_frames = kind == "swing", kind == "loop", kind == "frames"
        self.swing_fields.setVisible(is_swing)
        self.loop_fields.setVisible(is_loop)
        self.frames_fields.setVisible(is_frames)
        # Frames time per-frame, so the shared ticks/easing block doesn't apply.
        self.shared_fields.setVisible(is_swing or is_loop)
        if seg is None:
            return
        self._loading = True
        try:
            if is_frames:
                self.frames_start_spin.setValue(int(seg.get("start", 0)))
                self.frames_end_spin.setValue(int(seg.get("end", 0)))
                self.frame_ticks_spin.setValue(int(seg.get("ticks_per_frame", 1)))
            else:
                self.ticks_spin.setValue(int(seg.get("ticks", 0)))
                self.easing_combo.setCurrentText(str(seg.get("easing", "sine")))
            if is_swing:
                self.amplitude_spin.setValue(int(seg.get("amplitude", 0)))
                self.cycles_spin.setValue(int(seg.get("cycles", 1)))
            elif is_loop:
                self.turns_spin.setValue(int(seg.get("turns", 1)))
                self.direction_combo.setCurrentIndex(0 if seg.get("direction", 1) >= 0 else 1)
                self.repeatable_check.setChecked(bool(seg.get("repeatable", False)))
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
        kind = seg.get("kind")
        if kind == "frames":
            seg["start"] = self.frames_start_spin.value()
            seg["end"] = self.frames_end_spin.value()
            seg["ticks_per_frame"] = self.frame_ticks_spin.value()
        else:
            seg["ticks"] = self.ticks_spin.value()
            seg["easing"] = self.easing_combo.currentText()
        if kind == "swing":
            seg["amplitude"] = self.amplitude_spin.value()
            seg["cycles"] = self.cycles_spin.value()
        elif kind == "loop":
            seg["turns"] = self.turns_spin.value()
            seg["direction"] = 1 if self.direction_combo.currentIndex() == 0 else -1
            seg["repeatable"] = self.repeatable_check.isChecked()
        self.segment_list.item(self.segment_list.currentRow()).setText(self._label_for(seg))
        self.projectChanged.emit()
