"""Ride metadata form, bound to a RideProject.

Rider cars live on the Layers section (layers_panel.py) - they're a sprite
layer concern (rider-overlay frame sets), not project metadata. Default
colour schemes live on the Colours section (colour_preview_panel.py) -
they're a list of presets, not a single project-wide pair."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.build.thumbnail import THUMBNAIL_SIZE, fit_to_thumbnail
from attraction_editor.model.project import RideProject
from attraction_editor.ui.pil_qt import pil_to_pixmap

RIDE_CATEGORIES = ["transport", "gentle", "rollercoaster", "thrill", "water", "shop"]


class ProjectPanel(QWidget):
    """Ride metadata. Edits are written directly to the bound RideProject;
    `projectChanged` fires after any edit."""

    projectChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None

        self.id_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.description_edit = QLineEdit()
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(RIDE_CATEGORIES)

        self.frames_per_dir_spin = QSpinBox()
        self.frames_per_dir_spin.setRange(1, 65535)

        self.sprite_width_spin = QSpinBox()
        self.sprite_width_spin.setRange(0, 1024)
        self.sprite_height_spin = QSpinBox()
        self.sprite_height_spin.setRange(0, 1024)
        self.sprite_height_spin.setToolTip(
            "The rendered frame's total pixel height (e.g. 265 for a 384x265 sheet).\n"
            "Where the origin point sits within that height is the Anchors section's job -\n"
            "no need to split this into above/below halves yourself."
        )

        # Reserved land footprint in game tiles - written into manifest.json
        # (see build/object_json.py's custom_ride_manifest) so
        # CustomRideLoader.cpp can select the matching TrackElemType.
        # Validated here against the engine's own kMaxSequencesPerPiece cap
        # (64 tiles per track piece) rather than RideProject's constructor-
        # time check, since an invalid combination must never reach the
        # model at all - the user is mid-edit, one spinbox at a time, and
        # RideProject only validates at construction, not on attribute
        # assignment.
        self.footprint_width_spin = QSpinBox()
        self.footprint_width_spin.setRange(1, RideProject.MAX_FOOTPRINT_TILES)
        self.footprint_length_spin = QSpinBox()
        self.footprint_length_spin.setRange(1, RideProject.MAX_FOOTPRINT_TILES)
        self.footprint_error_label = QLabel("")
        self.footprint_error_label.setStyleSheet("color: red;")
        self.footprint_error_label.setWordWrap(True)

        # Preview thumbnail: the New Ride / construction-window icon. Optional -
        # left blank, the build auto-generates one from structure frame 0 (see
        # build/sprite_builder.py). The live preview shows exactly what the
        # build will produce: the source fitted to 112x112 on transparent
        # padding (see build/thumbnail.py).
        self.thumbnail_edit, thumbnail_row = _path_field(directory=False)
        self.thumbnail_preview = QLabel()
        self.thumbnail_preview.setFixedSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
        self.thumbnail_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_preview.setStyleSheet("border: 1px solid palette(mid);")

        self.output_name_edit = QLineEdit()
        self.deploy_dir_edit, deploy_row = _path_field(directory=True)
        self.openrct2_cli_edit, cli_row = _path_field(directory=False)

        form = QFormLayout()
        form.addRow("ID", self.id_edit)
        form.addRow("Name", self.name_edit)
        form.addRow("Description", self.description_edit)
        form.addRow("Category", self.category_combo)
        form.addRow("Sequence length (frames)", self.frames_per_dir_spin)
        form.addRow("Sprite width", self.sprite_width_spin)
        form.addRow("Sprite height", self.sprite_height_spin)
        form.addRow("Footprint width (tiles)", self.footprint_width_spin)
        form.addRow("Footprint length (tiles)", self.footprint_length_spin)
        form.addRow("", self.footprint_error_label)
        form.addRow("Preview thumbnail", thumbnail_row)
        form.addRow("", self.thumbnail_preview)
        form.addRow("Output name", self.output_name_edit)
        form.addRow("Deploy folder", deploy_row)
        form.addRow("openrct2-cli path", cli_row)

        layout = QVBoxLayout()
        layout.addLayout(form)
        self.setLayout(layout)

        # Wiring
        self.id_edit.textChanged.connect(self._on_simple_field_changed)
        self.name_edit.textChanged.connect(self._on_simple_field_changed)
        self.description_edit.textChanged.connect(self._on_simple_field_changed)
        self.category_combo.currentTextChanged.connect(self._on_simple_field_changed)
        self.frames_per_dir_spin.valueChanged.connect(self._on_simple_field_changed)
        self.sprite_width_spin.valueChanged.connect(self._on_simple_field_changed)
        self.sprite_height_spin.valueChanged.connect(self._on_simple_field_changed)
        self.footprint_width_spin.valueChanged.connect(self._on_simple_field_changed)
        self.footprint_length_spin.valueChanged.connect(self._on_simple_field_changed)
        self.thumbnail_edit.textChanged.connect(self._on_simple_field_changed)
        self.output_name_edit.textChanged.connect(self._on_simple_field_changed)
        self.deploy_dir_edit.textChanged.connect(self._on_simple_field_changed)
        self.openrct2_cli_edit.textChanged.connect(self._on_simple_field_changed)

        self._loading = False
        self.setEnabled(False)

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self._loading = True
        try:
            self.id_edit.setText(project.id)
            self.name_edit.setText(project.name)
            self.description_edit.setText(project.description)
            self.category_combo.setCurrentText(project.category)
            self.frames_per_dir_spin.setValue(project.frames_per_dir)
            self.sprite_width_spin.setValue(project.sprite_width)
            self.sprite_height_spin.setValue(project.sprite_height)
            self.footprint_width_spin.setValue(project.base_footprint_width)
            self.footprint_length_spin.setValue(project.base_footprint_length)
            self.footprint_error_label.setText("")
            self.thumbnail_edit.setText(project.thumbnail_path or "")
            self.output_name_edit.setText(project.output_name)
            self.deploy_dir_edit.setText(project.deploy_dir or "")
            self.openrct2_cli_edit.setText(project.openrct2_cli_path or "")
        finally:
            self._loading = False
        self._update_thumbnail_preview()
        self.setEnabled(True)

    def _on_simple_field_changed(self, *_args) -> None:
        if self._loading or self.project is None:
            return
        self.project.id = self.id_edit.text()
        self.project.name = self.name_edit.text()
        self.project.description = self.description_edit.text()
        self.project.category = self.category_combo.currentText()
        self.project.frames_per_dir = self.frames_per_dir_spin.value()
        self.project.sprite_width = self.sprite_width_spin.value()
        self.project.sprite_height = self.sprite_height_spin.value()

        width = self.footprint_width_spin.value()
        length = self.footprint_length_spin.value()
        tiles = width * length
        if tiles > RideProject.MAX_FOOTPRINT_TILES:
            self.footprint_error_label.setText(
                f"{width}x{length} = {tiles} tiles exceeds the engine's "
                f"{RideProject.MAX_FOOTPRINT_TILES}-tile limit per track piece - not saved."
            )
        else:
            self.footprint_error_label.setText("")
            self.project.base_footprint_width = width
            self.project.base_footprint_length = length

        # Stored as typed (relative to project_dir, or absolute): the build
        # resolves both via project_dir / thumbnail_path, same as the car
        # sprite-dir convention.
        self.project.thumbnail_path = self.thumbnail_edit.text() or None
        self.project.output_name = self.output_name_edit.text()
        self.project.deploy_dir = self.deploy_dir_edit.text() or None
        self.project.openrct2_cli_path = self.openrct2_cli_edit.text() or None
        self._update_thumbnail_preview()
        self.projectChanged.emit()

    def _update_thumbnail_preview(self) -> None:
        """Show the build's actual thumbnail output (source fitted to 112x112),
        or a placeholder: (auto) when none is set - the build will derive one
        from structure frame 0 - (missing)/(invalid) when the configured file
        can't be loaded."""
        self.thumbnail_preview.setToolTip("")
        if self.project is None or not self.project.thumbnail_path:
            self.thumbnail_preview.clear()
            self.thumbnail_preview.setText("(auto)")
            return

        base = self.project.project_dir or Path.cwd()
        source = base / self.project.thumbnail_path  # absolute thumbnail_path overrides base
        if not source.exists():
            self.thumbnail_preview.clear()
            self.thumbnail_preview.setText("(missing)")
            self.thumbnail_preview.setToolTip(f"Not found: {source}")
            return
        try:
            with Image.open(source) as im:
                fitted = fit_to_thumbnail(im)
        except (OSError, ValueError) as exc:
            self.thumbnail_preview.clear()
            self.thumbnail_preview.setText("(invalid)")
            self.thumbnail_preview.setToolTip(str(exc))
            return
        self.thumbnail_preview.setPixmap(pil_to_pixmap(fitted))


def _path_field(directory: bool = False) -> tuple[QLineEdit, QWidget]:
    """A QLineEdit + "Browse..." button packed into a single row widget."""
    edit = QLineEdit()
    browse = QPushButton("Browse...")

    def on_browse() -> None:
        start = edit.text() or str(Path.cwd())
        if directory:
            chosen = QFileDialog.getExistingDirectory(edit, "Select folder", start)
        else:
            chosen, _filter = QFileDialog.getOpenFileName(edit, "Select file", start)
        if chosen:
            edit.setText(chosen)
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
