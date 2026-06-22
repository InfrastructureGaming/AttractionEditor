"""Default colour schemes editor: authors RideProject.colour_schemes (see
model.project.ColourScheme), the list of presets written into object.json's
properties.carColours on build. The engine picks one preset at random when
the ride is placed and the ride stays fully recolourable by the player
afterward - this panel is for choosing those starting presets and previewing
what each one looks like, NOT for setting a colour that gets baked into the
shipped sprites (see build/layers.py's render_layer_frame_preview - the
preview here calls that, never the production render path).

Selecting a scheme in the list only loads it into the Trim/Tertiary combos
for editing - it does NOT change what's shown anywhere. "Apply Scheme" makes
the selected scheme the session's active preview scheme, used by every
preview-rendering section (Layers/Anchors/Animation/this panel itself) until
a different scheme is applied or "Disable Colours" clears it back to raw.
This is purely a UI-session concept (see get_active_scheme()) - it's never
written to the project file, and never affects what actually ships.

The Trim/Tertiary catch tolerance spinboxes (RideProject.trim_catch_tolerance/
tertiary_catch_tolerance) widen or narrow which pixels actually land in each
remap zone during dithering - this DOES affect the shipped sprite (see
build/dither.py's module docstring), unlike everything else on this panel.

Modeled on LayersPanel/ProgramEditorPanel's list + form + _loading-guard
pattern. Renders into the shared PreviewWidget (see ui/preview_widget.py)
rather than its own QLabel - set_preview_widget()/set_direction_combo() must
be called before set_project()."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.build.layers import composite_preview_frame
from attraction_editor.model.project import ColourScheme, RideProject
from attraction_editor.palette.remap import load_colour_ramps
from attraction_editor.ui.preview_widget import PreviewWidget


class ColourPreviewPanel(QWidget):
    """Scheme list (left) -> Trim/Tertiary combos for the selected scheme +
    Apply/Disable buttons + live preview (right). Edits are written directly
    to the bound RideProject; `projectChanged` fires after any edit
    (add/remove/recolour). `activeSchemeChanged` fires when Apply/Disable
    changes the session's active preview scheme - other panels need to
    re-render when that happens, not just this one."""

    projectChanged = Signal()
    activeSchemeChanged = Signal()
    catchToleranceChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self.preview_widget: PreviewWidget | None = None
        self.direction_combo: QComboBox | None = None
        self._loading = False
        self._active_scheme: ColourScheme | None = None

        colours = sorted(load_colour_ramps().keys())

        self.scheme_list = QListWidget()
        add_btn = QPushButton("Add scheme")
        remove_btn = QPushButton("Remove scheme")

        list_buttons = QHBoxLayout()
        list_buttons.addWidget(add_btn)
        list_buttons.addWidget(remove_btn)

        self.trim_combo = QComboBox()
        self.trim_combo.addItems(colours)
        self.tertiary_combo = QComboBox()
        self.tertiary_combo.addItems(colours)

        # Widen (positive) or narrow (negative) which pixels actually land
        # in each remap zone during dithering for the *real* build - see
        # RideProject.trim_catch_tolerance/tertiary_catch_tolerance and
        # build/dither.py's _apply_catch_tolerance_bias. 0 = today's
        # original fixed nearest-match-only behaviour.
        self.trim_tolerance_spin = QSpinBox()
        self.trim_tolerance_spin.setRange(-150, 150)
        self.trim_tolerance_spin.setToolTip(
            "Widen (+) or narrow (-) which pixels count as Trim-remappable.\n"
            "0 = exact nearest-match only."
        )
        self.tertiary_tolerance_spin = QSpinBox()
        self.tertiary_tolerance_spin.setRange(-150, 150)
        self.tertiary_tolerance_spin.setToolTip(
            "Widen (+) or narrow (-) which pixels count as Tertiary-remappable.\n"
            "0 = exact nearest-match only."
        )

        form = QFormLayout()
        form.addRow("Trim colour", self.trim_combo)
        form.addRow("Trim catch tolerance", self.trim_tolerance_spin)
        form.addRow("Tertiary colour", self.tertiary_combo)
        form.addRow("Tertiary catch tolerance", self.tertiary_tolerance_spin)

        apply_btn = QPushButton("Apply Scheme")
        disable_btn = QPushButton("Disable Colours")
        apply_buttons = QHBoxLayout()
        apply_buttons.addWidget(apply_btn)
        apply_buttons.addWidget(disable_btn)

        # Moved here from Animation - dithering and colour remapping are
        # both palette-level concerns best judged together, and this is
        # where the recolour preview itself lives. AnimationPlayerPanel
        # still reads this same checkbox (see set_dither_checkbox()) so
        # playback respects it too.
        self.dither_check = QCheckBox("Preview dithering")

        self.active_label = QLabel("Colours disabled (raw sprites shown)")
        self.active_label.setWordWrap(True)
        self.status_label = QLabel("No preview available")
        self.status_label.setWordWrap(True)

        left = QVBoxLayout()
        left.addWidget(self.scheme_list)
        left.addLayout(list_buttons)
        left_widget = QWidget()
        left_widget.setLayout(left)

        right = QVBoxLayout()
        right.addLayout(form)
        right.addLayout(apply_buttons)
        right.addWidget(self.dither_check)
        right.addWidget(self.active_label)
        right.addWidget(self.status_label)
        right_widget = QWidget()
        right_widget.setLayout(right)

        # Stacked rather than side-by-side: this panel now lives in a narrow
        # column next to the shared preview (see ui/main_window.py), not a
        # full-width tab - a QHBoxLayout here would sum both halves' minimum
        # widths and force horizontal scrolling as the column narrows.
        layout = QVBoxLayout()
        layout.addWidget(left_widget)
        layout.addWidget(right_widget)
        self.setLayout(layout)

        self.scheme_list.currentRowChanged.connect(self._on_scheme_selected)
        add_btn.clicked.connect(self._on_add_scheme)
        remove_btn.clicked.connect(self._on_remove_scheme)

        self.trim_combo.currentTextChanged.connect(self._on_field_changed)
        self.tertiary_combo.currentTextChanged.connect(self._on_field_changed)

        self.trim_tolerance_spin.valueChanged.connect(self._on_catch_tolerance_changed)
        self.tertiary_tolerance_spin.valueChanged.connect(self._on_catch_tolerance_changed)

        apply_btn.clicked.connect(self._on_apply_scheme)
        disable_btn.clicked.connect(self._on_disable_colours)

        self.dither_check.stateChanged.connect(self._reload_preview)

        self.setEnabled(False)

    def set_preview_widget(self, preview_widget: PreviewWidget) -> None:
        self.preview_widget = preview_widget

    def set_direction_combo(self, direction_combo: QComboBox) -> None:
        self.direction_combo = direction_combo

    def get_active_scheme(self) -> ColourScheme | None:
        """The session's currently-applied preview scheme, or None if
        colours are disabled (raw sprites). Read by every other
        preview-rendering panel via set_active_scheme_getter()."""
        return self._active_scheme

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self._active_scheme = None  # a new project's schemes are different objects
        self._update_active_label()
        self._loading = True
        try:
            self.trim_tolerance_spin.setValue(project.trim_catch_tolerance)
            self.tertiary_tolerance_spin.setValue(project.tertiary_catch_tolerance)
        finally:
            self._loading = False
        self._reload_scheme_list()
        self.setEnabled(True)

    def refresh_from_project(self) -> None:
        """Re-sync from `self.project` without emitting projectChanged (for
        use when another panel's edit affects this preview, e.g. layers or
        sprite dimensions changing)."""
        if self.project is None:
            return
        self._reload_scheme_list()

    def _reload_scheme_list(self) -> None:
        current = self.scheme_list.currentRow()
        self.scheme_list.clear()
        for scheme in self.project.colour_schemes:
            self.scheme_list.addItem(self._label_for(scheme))
        if 0 <= current < self.scheme_list.count():
            self.scheme_list.setCurrentRow(current)
        elif self.project.colour_schemes:
            self.scheme_list.setCurrentRow(0)
        else:
            self._on_scheme_selected(-1)

    @staticmethod
    def _label_for(scheme: ColourScheme) -> str:
        return f"Trim={scheme.trim_colour}, Tertiary={scheme.tertiary_colour}"

    def _current_scheme(self) -> ColourScheme | None:
        if self.project is None:
            return None
        row = self.scheme_list.currentRow()
        if row < 0 or row >= len(self.project.colour_schemes):
            return None
        return self.project.colour_schemes[row]

    def _on_scheme_selected(self, row: int) -> None:
        # Selecting only loads the scheme into the form for editing - it
        # does not change the active preview scheme. Use "Apply Scheme" for that.
        scheme = self._current_scheme()
        self._loading = True
        try:
            if scheme is None:
                self.trim_combo.setCurrentText("white")
                self.tertiary_combo.setCurrentText("white")
            else:
                self.trim_combo.setCurrentText(scheme.trim_colour)
                self.tertiary_combo.setCurrentText(scheme.tertiary_colour)
        finally:
            self._loading = False

    def _on_field_changed(self, *_args) -> None:
        if self._loading:
            return
        scheme = self._current_scheme()
        if scheme is None:
            return
        scheme.trim_colour = self.trim_combo.currentText()
        scheme.tertiary_colour = self.tertiary_combo.currentText()
        self.scheme_list.item(self.scheme_list.currentRow()).setText(self._label_for(scheme))
        # If this scheme happens to be the active one (same object), the
        # preview needs to reflect the edit immediately; harmless no-op
        # otherwise since the rendered image wouldn't change.
        if scheme is self._active_scheme:
            self._update_active_label()
            self._reload_preview()
        self.projectChanged.emit()

    def _on_catch_tolerance_changed(self, *_args) -> None:
        if self._loading or self.project is None:
            return
        self.project.trim_catch_tolerance = self.trim_tolerance_spin.value()
        self.project.tertiary_catch_tolerance = self.tertiary_tolerance_spin.value()
        self._reload_preview()
        self.catchToleranceChanged.emit()
        self.projectChanged.emit()

    def _on_add_scheme(self) -> None:
        if self.project is None:
            return
        index = len(self.project.colour_schemes)
        self.project.colour_schemes.append(ColourScheme(trim_colour="white", tertiary_colour="white"))
        self._reload_scheme_list()
        self.scheme_list.setCurrentRow(index)
        self.projectChanged.emit()

    def _on_remove_scheme(self) -> None:
        if self.project is None or len(self.project.colour_schemes) <= 1:
            return
        row = self.scheme_list.currentRow()
        if row < 0 or row >= len(self.project.colour_schemes):
            return
        removed = self.project.colour_schemes[row]
        del self.project.colour_schemes[row]
        self._reload_scheme_list()
        if removed is self._active_scheme:
            # The applied scheme no longer exists - fall back to raw rather
            # than holding a reference to a deleted preset.
            self._active_scheme = None
            self._update_active_label()
            self._reload_preview()
            self.activeSchemeChanged.emit()
        self.projectChanged.emit()

    def _on_apply_scheme(self) -> None:
        scheme = self._current_scheme()
        if scheme is None:
            return
        self._active_scheme = scheme
        self._update_active_label()
        self._reload_preview()
        self.activeSchemeChanged.emit()

    def _on_disable_colours(self) -> None:
        self._active_scheme = None
        self._update_active_label()
        self._reload_preview()
        self.activeSchemeChanged.emit()

    def _update_active_label(self) -> None:
        if self._active_scheme is None:
            self.active_label.setText("Colours disabled (raw sprites shown)")
        else:
            self.active_label.setText(f"Active: {self._label_for(self._active_scheme)}")

    def _reload_preview(self, *_args) -> None:
        if (
            self.project is None
            or self.project.project_dir is None
            or self.preview_widget is None
            or self.direction_combo is None
        ):
            self.status_label.setText("No preview available")
            return

        direction = self.direction_combo.currentIndex()
        try:
            preview = composite_preview_frame(
                self.project, direction, dither=self.dither_check.isChecked(), scheme=self._active_scheme
            )
        except FileNotFoundError as exc:
            self.status_label.setText(f"Frame not found: {exc}")
            return

        self.status_label.setText("")
        self.preview_widget.set_image(preview)
