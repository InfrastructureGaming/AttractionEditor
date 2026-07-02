"""Plays a direction's frame sequence at an adjustable FPS: the live
structure composite (every Layer dithered/flattened in z-order, see
build.layers.composite_preview_frame) with rider cars (toggleable per car)
layered on top. This is the place to actually see whether a layer's chosen
dithering algorithm jitters in motion - the "Preview dithering" checkbox
that controls this now lives on the Colours section (dithering and colour
remapping are both palette-level concerns best judged together there); this
panel just reads that same shared checkbox, see set_dither_checkbox().

Shows the session's active colour scheme if one has been applied via the
Colours section's "Apply Scheme" button (see ColourPreviewPanel); otherwise
shows the raw, as-shipped structure, since the real build never recolours
either.

Caches each (direction, frame_index) structure composite (everything
composite_preview_frame produces, before rider-car overlays are added) so
looping playback re-renders each frame only once per pass through the
configuration that produced it. This matters once a colour scheme or catch
tolerance is in use: classifying every pixel against the full StandardPalette
(see palette/remap.py's classify_remap_zone) costs tens of milliseconds per
frame even with that module's own optimisations, which a 20-60Hz playback
timer calling composite_preview_frame fresh on every tick would otherwise pay
on every single loop instead of just the first. The cache key includes the
active scheme's identity, the dither checkbox, and both catch tolerances, so
it can never serve a stale frame for the wrong settings - changing any of
those simply misses the cache and renders fresh, no separate invalidation
plumbing required. Edits that change the underlying layer images themselves
(layer/project edits) aren't reflected in the key, so set_project() and
_invalidate_frame_cache() explicitly clear it.

Renders into the shared PreviewWidget (see ui/preview_widget.py) rather than
its own QLabel - set_preview_widget()/set_direction_combo()/
set_active_scheme_getter()/set_dither_checkbox() must be called before
set_project()."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

from attraction_editor.build.layers import composite_preview_frame
from attraction_editor.model.project import ColourScheme, RideProject
from attraction_editor.sprites.scanner import frame_path
from attraction_editor.ui.preview_widget import PreviewWidget

DEFAULT_FPS = 20

# Cap on cached structure composites - bounds memory for projects with very
# large frame counts (frames_per_dir can go up to 65535) while still fully
# covering the common case (looping a few hundred frames at most).
_FRAME_CACHE_LIMIT = 256


class AnimationPlayerPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self.preview_widget: PreviewWidget | None = None
        self.direction_combo: QComboBox | None = None
        self.dither_check: QCheckBox | None = None
        self._active_scheme_getter: Callable[[], ColourScheme | None] | None = None
        self.frame_index = 0
        self.car_checks: dict[str, QCheckBox] = {}
        self._frame_cache: dict[tuple, Image.Image] = {}

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)

        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setValue(DEFAULT_FPS)

        self.play_button = QPushButton("Play")
        self.play_button.setCheckable(True)

        self.frame_counter_label = QLabel("Frame 0")

        self.car_checks_layout = QHBoxLayout()

        # Compact horizontal strip: this panel lives in the Preview's navigation
        # bar (see main_window), not a controls-column section, so its playback
        # controls + per-car visibility toggles lay out inline.
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.play_button)
        layout.addWidget(QLabel("FPS"))
        layout.addWidget(self.fps_spin)
        layout.addWidget(self.frame_counter_label)
        layout.addLayout(self.car_checks_layout)
        self.setLayout(layout)

        self.play_button.toggled.connect(self._on_play_toggled)
        self.fps_spin.valueChanged.connect(self._on_fps_changed)

        self.setEnabled(False)

    def set_preview_widget(self, preview_widget: PreviewWidget) -> None:
        self.preview_widget = preview_widget

    def set_direction_combo(self, direction_combo: QComboBox) -> None:
        self.direction_combo = direction_combo

    def set_dither_checkbox(self, dither_check: QCheckBox) -> None:
        """The "Preview dithering" checkbox now lives on the Colours
        section (ColourPreviewPanel) - this panel just reads/disables the
        same shared widget rather than owning its own."""
        self.dither_check = dither_check

    def set_active_scheme_getter(self, getter: Callable[[], ColourScheme | None]) -> None:
        """`getter` returns the session's currently-applied colour scheme
        (see ColourPreviewPanel.get_active_scheme), or None for raw sprites."""
        self._active_scheme_getter = getter

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self.frame_index = 0
        self.timer.stop()
        self.play_button.setChecked(False)
        self.play_button.setText("Play")
        self._invalidate_frame_cache()
        self._reload_car_checks()
        self._update_frame()
        self.setEnabled(True)

    def _invalidate_frame_cache(self) -> None:
        """Call after any edit that changes the underlying layer images
        themselves (layer reordering/sprite-dir/dither-algorithm changes,
        sprite dimensions, a new project) - those aren't reflected in the
        cache key (see this module's docstring), unlike scheme/dither/
        tolerance changes, which invalidate automatically."""
        self._frame_cache.clear()

    def _reload_car_checks(self) -> None:
        while self.car_checks_layout.count():
            item = self.car_checks_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.car_checks.clear()

        for car in self.project.cars:
            checkbox = QCheckBox(car.name)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._update_frame)
            self.car_checks_layout.addWidget(checkbox)
            self.car_checks[car.name] = checkbox

    def _on_play_toggled(self, checked: bool) -> None:
        if checked:
            self.timer.start(1000 // self.fps_spin.value())
            self.play_button.setText("Pause")
            if self.dither_check is not None:
                self.dither_check.setEnabled(False)
        else:
            self.timer.stop()
            self.play_button.setText("Play")
            if self.dither_check is not None:
                self.dither_check.setEnabled(True)
            self._update_frame()

    def _on_fps_changed(self, value: int) -> None:
        if self.timer.isActive():
            self.timer.start(1000 // value)

    def _advance(self) -> None:
        if self.project is None:
            return
        self.frame_index = (self.frame_index + 1) % self.project.frames_per_dir
        self._update_frame()

    def _update_frame(self, *_args) -> None:
        self.frame_counter_label.setText(f"Frame {self.frame_index}")
        if self.project is None or self.project.project_dir is None or self.direction_combo is None:
            return
        if self.preview_widget is None:
            return

        direction = self.direction_combo.currentIndex()
        project_dir = Path(self.project.project_dir)
        scheme = self._active_scheme_getter() if self._active_scheme_getter else None
        dither = self.dither_check.isChecked() if self.dither_check is not None else False

        cache_key = (
            direction,
            self.frame_index,
            id(scheme) if scheme is not None else None,
            dither,
            self.project.trim_catch_tolerance,
            self.project.tertiary_catch_tolerance,
        )
        composite = self._frame_cache.get(cache_key)
        if composite is None:
            try:
                composite = composite_preview_frame(self.project, direction, self.frame_index, dither=dither, scheme=scheme)
            except FileNotFoundError as exc:
                self.frame_counter_label.setText(f"Frame {self.frame_index} - preview unavailable ({exc})")
                return
            if len(self._frame_cache) >= _FRAME_CACHE_LIMIT:
                self._frame_cache.pop(next(iter(self._frame_cache)))
            self._frame_cache[cache_key] = composite

        for car in self.project.cars:
            checkbox = self.car_checks.get(car.name)
            if checkbox is None or not checkbox.isChecked():
                continue
            car_path = frame_path(project_dir / car.sprite_dir, direction, self.frame_index)
            if not car_path.exists():
                continue
            with Image.open(car_path) as car_img:
                composite = Image.alpha_composite(composite, car_img.convert("RGBA"))

        self.preview_widget.set_image(composite)
