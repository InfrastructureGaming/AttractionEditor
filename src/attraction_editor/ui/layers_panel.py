"""Structure layers editor: authors RideProject.layers (see model.project.Layer)
- an ordered list of visual planes composited together (back to front) into
the final sprite before building. List order is z-order: move-up/move-down
swap adjacent entries, which is the only thing that needs to change to
reorder compositing.

Also hosts the rider-cars list (RideProject.cars) - a sprite-layer concern
(rider-overlay frame sets composited on top at render time, see
build/layers.py's docstring) rather than project metadata, so it lives here
rather than on the Project section.

Modeled on ProgramEditorPanel's list + form + _loading-guard pattern.

Renders into the shared PreviewWidget (see ui/preview_widget.py) after any
compositing-relevant edit - set_preview_widget()/set_direction_combo() must
be called before set_project()."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.build.layers import composite_preview_frame
from attraction_editor.model.project import CarConfig, ColourScheme, DITHER_ALGORITHMS, LAYER_KINDS, Layer, RideProject
from attraction_editor.sprites.scanner import frame_path
from attraction_editor.ui.preview_widget import PreviewWidget

# Display order for the kind/algorithm combos - sets are unordered, so pin
# a stable, sensible order here rather than iterating the set directly.
_KIND_ORDER = ["animated", "static"]
_ALGORITHM_ORDER = ["floyd_steinberg", "bayer", "atkinson", "none"]

assert set(_KIND_ORDER) == LAYER_KINDS
assert set(_ALGORITHM_ORDER) == DITHER_ALGORITHMS


class LayersPanel(QWidget):
    """Layers list (back-to-front order) -> form for the selected layer's
    name/sprite_dir/kind/dither algorithm+strength. Edits are written
    directly to the bound RideProject; `projectChanged` fires after any
    edit (including reordering, which changes compositing z-order)."""

    projectChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self.preview_widget: PreviewWidget | None = None
        self.direction_combo: QComboBox | None = None
        self.dither_check: QCheckBox | None = None
        self._active_scheme_getter: Callable[[], ColourScheme | None] | None = None
        self._loading = False

        self.layer_list = QListWidget()
        add_btn = QPushButton("Add layer")
        remove_btn = QPushButton("Remove layer")
        up_btn = QPushButton("Move up (back)")
        down_btn = QPushButton("Move down (front)")

        list_buttons = QHBoxLayout()
        list_buttons.addWidget(add_btn)
        list_buttons.addWidget(remove_btn)

        reorder_buttons = QHBoxLayout()
        reorder_buttons.addWidget(up_btn)
        reorder_buttons.addWidget(down_btn)

        self.name_edit = QLineEdit()
        self.sprite_dir_edit, sprite_dir_row = _path_field(self._project_dir)
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(_KIND_ORDER)
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.addItems(_ALGORITHM_ORDER)
        self.strength_spin = QSpinBox()
        self.strength_spin.setRange(0, 255)
        self.strength_spin.setToolTip(
            "0 = no dithering (plain nearest-match), 32 = full classic dithering for the\n"
            "chosen algorithm (the default). Values above 32 have no further effect."
        )
        # Strength is the one field gated behind an explicit Apply: unlike the
        # discrete dropdowns, it's typed digit-by-digit, and a re-dither runs
        # on every committed value - so a live valueChanged binding would
        # re-render the (expensive) dithered preview on each intermediate keystroke
        # before the user has finished entering the number they actually want.
        self.apply_strength_btn = QPushButton("Apply")
        self.apply_strength_btn.setToolTip(
            "Apply the entered dither strength and re-render the preview.\n"
            "Strength changes aren't previewed until applied."
        )
        # Cap the spin and left-pack with a trailing stretch so the button sits
        # right beside it. Without this the QFormLayout's field column (~210px
        # wide, sized by the long-named algorithm combo) splits between the two,
        # parking the button at the far-right edge - the first thing scrolled
        # out of view in the narrow controls column (see ui/main_window.py).
        self.strength_spin.setMaximumWidth(72)
        strength_row = QHBoxLayout()
        strength_row.addWidget(self.strength_spin)
        strength_row.addWidget(self.apply_strength_btn)
        strength_row.addStretch(1)

        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("Sprite folder", sprite_dir_row)
        form.addRow("Kind", self.kind_combo)
        form.addRow("Dither algorithm", self.algorithm_combo)
        form.addRow("Dither strength", strength_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        self.car_list = QListWidget()
        self.car_name_edit = QLineEdit()
        self.car_sprite_dir_edit, car_dir_row = _path_field(self._project_dir)
        add_car_btn = QPushButton("Add car")
        remove_car_btn = QPushButton("Remove car")

        car_buttons = QHBoxLayout()
        car_buttons.addWidget(add_car_btn)
        car_buttons.addWidget(remove_car_btn)

        car_form = QFormLayout()
        car_form.addRow("Name", self.car_name_edit)
        car_form.addRow("Sprite folder", car_dir_row)

        car_box = QGroupBox("Rider cars")
        car_layout = QVBoxLayout()
        car_layout.addWidget(self.car_list)
        car_layout.addLayout(car_buttons)
        car_layout.addLayout(car_form)
        car_box.setLayout(car_layout)

        layout = QVBoxLayout()
        layout.addWidget(self.layer_list)
        layout.addLayout(list_buttons)
        layout.addLayout(reorder_buttons)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addWidget(car_box)
        self.setLayout(layout)

        self.layer_list.currentRowChanged.connect(self._on_layer_selected)
        add_btn.clicked.connect(self._on_add_layer)
        remove_btn.clicked.connect(self._on_remove_layer)
        up_btn.clicked.connect(self._on_move_up)
        down_btn.clicked.connect(self._on_move_down)

        self.name_edit.editingFinished.connect(self._on_field_changed)
        self.sprite_dir_edit.editingFinished.connect(self._on_field_changed)
        self.kind_combo.currentTextChanged.connect(self._on_field_changed)
        self.algorithm_combo.currentTextChanged.connect(self._on_field_changed)
        self.apply_strength_btn.clicked.connect(self._on_apply_strength)

        self.car_list.currentRowChanged.connect(self._on_car_selected)
        self.car_name_edit.editingFinished.connect(self._on_car_field_changed)
        self.car_sprite_dir_edit.editingFinished.connect(self._on_car_field_changed)
        add_car_btn.clicked.connect(self._on_add_car)
        remove_car_btn.clicked.connect(self._on_remove_car)

        self.setEnabled(False)

    def _project_dir(self) -> Path | None:
        return self.project.project_dir if self.project is not None else None

    def set_preview_widget(self, preview_widget: PreviewWidget) -> None:
        self.preview_widget = preview_widget

    def set_direction_combo(self, direction_combo: QComboBox) -> None:
        self.direction_combo = direction_combo

    def set_active_scheme_getter(self, getter: Callable[[], ColourScheme | None]) -> None:
        """`getter` returns the session's currently-applied colour scheme
        (see ColourPreviewPanel.get_active_scheme), or None for raw sprites."""
        self._active_scheme_getter = getter

    def set_dither_checkbox(self, dither_check: QCheckBox) -> None:
        """The "Preview dithering" checkbox lives on the Colours section
        (ColourPreviewPanel) - this panel just reads the same shared widget."""
        self.dither_check = dither_check

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self._reload_layer_list()
        self._reload_car_list()
        self._reload_preview()
        self.setEnabled(True)

    def _reload_preview(self, *_args) -> None:
        if (
            self.project is None
            or self.project.project_dir is None
            or self.preview_widget is None
            or self.direction_combo is None
        ):
            return
        direction = self.direction_combo.currentIndex()
        scheme = self._active_scheme_getter() if self._active_scheme_getter else None
        dither = self.dither_check.isChecked() if self.dither_check is not None else False
        try:
            preview = composite_preview_frame(self.project, direction, dither=dither, scheme=scheme)
        except FileNotFoundError as exc:
            self.status_label.setText(f"Preview unavailable - {exc}")
            return

        # Overlay the rider cars on top of the structure, exactly as the
        # Animation section does (see AnimationPlayerPanel._update_frame): every
        # car frame shares the structure's own per-direction anchor (see
        # sprites/manifest.py), so it composites pixel-for-pixel with no offset.
        # Riders are never dithered or colour-remapped (they use peep colours,
        # not the ride's trim/tertiary scheme), so they go on raw - frame 0,
        # since this static preview isn't animating. Missing car frames are
        # skipped rather than failing the whole preview.
        project_dir = self.project.project_dir
        for car in self.project.cars:
            car_path = frame_path(project_dir / car.sprite_dir, direction, 0)
            if not car_path.exists():
                continue
            with Image.open(car_path) as car_img:
                preview = Image.alpha_composite(preview.convert("RGBA"), car_img.convert("RGBA"))

        self.status_label.setText("")
        self.preview_widget.set_image(preview)

    def _reload_layer_list(self) -> None:
        current = self.layer_list.currentRow()
        self.layer_list.clear()
        for layer in self.project.layers:
            self.layer_list.addItem(self._label_for(layer))
        if 0 <= current < self.layer_list.count():
            self.layer_list.setCurrentRow(current)
        elif self.project.layers:
            self.layer_list.setCurrentRow(0)
        else:
            self._on_layer_selected(-1)

    @staticmethod
    def _label_for(layer: Layer) -> str:
        return f"{layer.name} ({layer.kind}, {layer.dither_algorithm})"

    def _current_layer(self) -> Layer | None:
        if self.project is None:
            return None
        row = self.layer_list.currentRow()
        if row < 0 or row >= len(self.project.layers):
            return None
        return self.project.layers[row]

    def _on_layer_selected(self, row: int) -> None:
        layer = self._current_layer()
        self._loading = True
        try:
            if layer is None:
                self.name_edit.setText("")
                self.sprite_dir_edit.setText("")
                self.kind_combo.setCurrentText("animated")
                self.algorithm_combo.setCurrentText("floyd_steinberg")
                self.strength_spin.setValue(32)
            else:
                self.name_edit.setText(layer.name)
                self.sprite_dir_edit.setText(layer.sprite_dir)
                self.kind_combo.setCurrentText(layer.kind)
                self.algorithm_combo.setCurrentText(layer.dither_algorithm)
                self.strength_spin.setValue(layer.dither_strength)
        finally:
            self._loading = False

    def _on_field_changed(self, *_args) -> None:
        if self._loading:
            return
        layer = self._current_layer()
        if layer is None:
            return

        layer.name = self.name_edit.text()
        layer.sprite_dir = self.sprite_dir_edit.text()
        layer.kind = self.kind_combo.currentText()
        layer.dither_algorithm = self.algorithm_combo.currentText()
        # Strength is intentionally NOT committed here - it's applied only via
        # _on_apply_strength so an unapplied, mid-entry value never leaks into
        # the layer when another field changes (see the strength_spin comment).

        self.layer_list.item(self.layer_list.currentRow()).setText(self._label_for(layer))
        self._reload_preview()
        self.projectChanged.emit()

    def _on_apply_strength(self) -> None:
        """Commit the entered dither strength to the current layer and re-render.
        The only path that writes layer.dither_strength, so the preview re-dithers
        once, on the value the user actually chose - not on each keystroke."""
        if self._loading:
            return
        layer = self._current_layer()
        if layer is None:
            return
        layer.dither_strength = self.strength_spin.value()
        self._reload_preview()
        self.projectChanged.emit()

    def _on_add_layer(self) -> None:
        if self.project is None:
            return
        index = len(self.project.layers)
        layer = Layer(name=f"Layer{index}", sprite_dir=f"Frames/Layer{index}", kind="animated")
        self.project.layers.append(layer)
        self._reload_layer_list()
        self.layer_list.setCurrentRow(index)
        self._reload_preview()
        self.projectChanged.emit()

    def _on_remove_layer(self) -> None:
        if self.project is None or len(self.project.layers) <= 1:
            return
        row = self.layer_list.currentRow()
        if row < 0 or row >= len(self.project.layers):
            return
        del self.project.layers[row]
        self._reload_layer_list()
        self._reload_preview()
        self.projectChanged.emit()

    def _on_move_up(self) -> None:
        self._swap(-1)

    def _on_move_down(self) -> None:
        self._swap(1)

    def _swap(self, delta: int) -> None:
        if self.project is None:
            return
        row = self.layer_list.currentRow()
        other = row + delta
        if row < 0 or other < 0 or other >= len(self.project.layers):
            return
        layers = self.project.layers
        layers[row], layers[other] = layers[other], layers[row]
        self._reload_layer_list()
        self.layer_list.setCurrentRow(other)
        self._reload_preview()
        self.projectChanged.emit()

    def _reload_car_list(self) -> None:
        self.car_list.clear()
        for car in self.project.cars:
            self.car_list.addItem(QListWidgetItem(f"{car.name}: {car.sprite_dir}"))

    def _on_car_selected(self, row: int) -> None:
        if self.project is None or row < 0 or row >= len(self.project.cars):
            self.car_name_edit.clear()
            self.car_sprite_dir_edit.clear()
            return
        car = self.project.cars[row]
        self._loading = True
        try:
            self.car_name_edit.setText(car.name)
            self.car_sprite_dir_edit.setText(car.sprite_dir)
        finally:
            self._loading = False
        # Selecting a car shows the structure with the rider cars overlaid (see
        # _reload_preview). No projectChanged.emit() here - selection doesn't
        # mutate the project - so the Layers panel stays the last writer to the
        # shared preview and the riders aren't wiped by another panel's render.
        self._reload_preview()

    def _on_car_field_changed(self) -> None:
        if self._loading or self.project is None:
            return
        row = self.car_list.currentRow()
        if row < 0 or row >= len(self.project.cars):
            return
        car = self.project.cars[row]
        car.name = self.car_name_edit.text()
        car.sprite_dir = self.car_sprite_dir_edit.text()
        self.car_list.item(row).setText(f"{car.name}: {car.sprite_dir}")
        # Emit first (cascades to the other preview panels via main_window),
        # then refresh this panel's preview last so the rider overlay survives
        # as the final write to the shared preview.
        self.projectChanged.emit()
        self._reload_preview()

    def _on_add_car(self) -> None:
        if self.project is None:
            return
        index = len(self.project.cars)
        car = CarConfig(name=f"Car{index}", sprite_dir=f"Frames/Riders/Car{index}")
        self.project.cars.append(car)
        self._reload_car_list()
        self.car_list.setCurrentRow(index)
        self.projectChanged.emit()
        self._reload_preview()

    def _on_remove_car(self) -> None:
        if self.project is None:
            return
        row = self.car_list.currentRow()
        if row < 0 or row >= len(self.project.cars):
            return
        del self.project.cars[row]
        self._reload_car_list()
        self.projectChanged.emit()
        self._reload_preview()


def _path_field(project_dir_getter: Callable[[], Path | None] | None = None) -> tuple[QLineEdit, QWidget]:
    """A QLineEdit + "Browse..." button packed into a single row widget.

    `project_dir_getter`, if given, is consulted on every Browse click so the
    dialog starts from (and the result is stored relative to) the current
    project's directory - Layer.sprite_dir/CarConfig.sprite_dir are always
    project_dir-relative (see model.project.Layer/CarConfig), so storing the
    dialog's raw absolute pick verbatim corrupts every downstream path build
    (sprite_builder.py's "../" car-path prefixing assumes a relative path and
    silently produces a nonsense doubled path otherwise - this was a real,
    confirmed bug, not a hypothetical). Picking a folder outside project_dir
    falls back to storing the absolute path, since there's no relative path
    that would make sense."""
    edit = QLineEdit()
    browse = QPushButton("Browse...")

    def on_browse() -> None:
        project_dir = project_dir_getter() if project_dir_getter else None
        current_text = edit.text()
        if current_text:
            start = str(Path(project_dir) / current_text) if project_dir is not None and not Path(current_text).is_absolute() else current_text
        else:
            start = str(project_dir) if project_dir is not None else str(Path.cwd())

        chosen = QFileDialog.getExistingDirectory(edit, "Select folder", start)
        if chosen:
            text = chosen
            if project_dir is not None:
                try:
                    text = str(Path(chosen).resolve().relative_to(Path(project_dir).resolve())).replace("\\", "/")
                except ValueError:
                    pass  # chosen folder is outside project_dir - keep the absolute path
            edit.setText(text)
            # setText() alone doesn't fire editingFinished (only Enter/focus-
            # loss does) - emit it explicitly so Browse-picked paths commit
            # to the model the same way typing-and-pressing-Enter does.
            edit.editingFinished.emit()

    browse.clicked.connect(on_browse)

    row = QWidget()
    row_layout = QHBoxLayout()
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.addWidget(edit)
    row_layout.addWidget(browse)
    row.setLayout(row_layout)
    return edit, row
