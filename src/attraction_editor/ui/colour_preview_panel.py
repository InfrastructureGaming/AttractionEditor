"""Default colour schemes editor: authors RideProject.colour_schemes (see
model.project.ColourScheme), the list of presets written into object.json's
properties.carColours on build. The engine picks one preset at random when
the ride is placed and the ride stays fully recolourable by the player
afterward - this panel is for choosing those starting presets and previewing
what each one looks like, NOT for setting a colour that gets baked into the
shipped sprites (see build/layers.py's render_layer_frame_preview - the
preview here calls that, never the production render path).

Modeled on LayersPanel/ProgramEditorPanel's list + form + _loading-guard
pattern. Renders into the shared PreviewWidget (see ui/preview_widget.py)
rather than its own QLabel - set_preview_widget()/set_direction_combo() must
be called before set_project()."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.build.layers import composite_preview_frame
from attraction_editor.model.project import ColourScheme, RideProject
from attraction_editor.palette.remap import load_colour_ramps
from attraction_editor.ui.preview_widget import PreviewWidget


class ColourPreviewPanel(QWidget):
    """Scheme list (left) -> Trim/Tertiary combos for the selected scheme +
    live preview (right). Edits are written directly to the bound
    RideProject; `projectChanged` fires after any edit (add/remove/recolour)."""

    projectChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self.preview_widget: PreviewWidget | None = None
        self.direction_combo: QComboBox | None = None
        self._loading = False

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

        form = QFormLayout()
        form.addRow("Trim colour", self.trim_combo)
        form.addRow("Tertiary colour", self.tertiary_combo)

        self.status_label = QLabel("No preview available")

        left = QVBoxLayout()
        left.addWidget(self.scheme_list)
        left.addLayout(list_buttons)
        left_widget = QWidget()
        left_widget.setLayout(left)

        right = QVBoxLayout()
        right.addLayout(form)
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

        self.setEnabled(False)

    def set_preview_widget(self, preview_widget: PreviewWidget) -> None:
        self.preview_widget = preview_widget

    def set_direction_combo(self, direction_combo: QComboBox) -> None:
        self.direction_combo = direction_combo

    def set_project(self, project: RideProject) -> None:
        self.project = project
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
        self._reload_preview()

    def _on_field_changed(self, *_args) -> None:
        if self._loading:
            return
        scheme = self._current_scheme()
        if scheme is None:
            return
        scheme.trim_colour = self.trim_combo.currentText()
        scheme.tertiary_colour = self.tertiary_combo.currentText()
        self.scheme_list.item(self.scheme_list.currentRow()).setText(self._label_for(scheme))
        self._reload_preview()
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
        del self.project.colour_schemes[row]
        self._reload_scheme_list()
        self.projectChanged.emit()

    def _reload_preview(self, *_args) -> None:
        if (
            self.project is None
            or self.project.project_dir is None
            or self.preview_widget is None
            or self.direction_combo is None
        ):
            self.status_label.setText("No preview available")
            return
        scheme = self._current_scheme()
        if scheme is None:
            self.status_label.setText("No scheme selected")
            return

        direction = self.direction_combo.currentIndex()
        try:
            preview = composite_preview_frame(self.project, direction, scheme=scheme)
        except FileNotFoundError as exc:
            self.status_label.setText(f"Frame not found: {exc}")
            return

        self.status_label.setText(self._label_for(scheme))
        self.preview_widget.set_image(preview)
