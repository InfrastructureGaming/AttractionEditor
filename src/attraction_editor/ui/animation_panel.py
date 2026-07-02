"""Animation authoring container: a method dropdown that selects HOW the ride's
motion is authored - and therefore which data the build emits - swapping the
relevant editor beneath it.

- Frame Sequence   -> the range-based Programs & Phases editor (ProgramEditorPanel)
- Swing (Parametric) -> the Motion editor (MotionEditorPanel)
- Rotation (Parametric) -> listed but DISABLED until the Ferris Wheel gives us its
  tailored palette (the dropdown is the extension point: new methods drop straight in).

The chosen method is stored on RideProject.animation_method and decides which
dataset object_json emits (see build/object_json.flat_ride_animation_block). Both
the `programs` and `motion` datasets are kept regardless, so switching methods
never discards work - only the active method's data ships."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QStackedWidget, QVBoxLayout, QWidget

from attraction_editor.model.project import RideProject
from attraction_editor.ui.motion_editor_panel import MotionEditorPanel
from attraction_editor.ui.program_editor_panel import ProgramEditorPanel

# (label, animation_method key). Order defines dropdown order.
_METHODS = [
    ("Frame Sequence", "frame_sequence"),
    ("Swing (Parametric)", "swing"),
    ("Rotation (Parametric)", "rotation"),
]
# Methods present in the dropdown as a roadmap signpost but not yet selectable.
_DISABLED_METHODS = {"rotation"}


class AnimationPanel(QWidget):
    """Method dropdown (top) + a QStackedWidget swapping between the Programs &
    Phases editor and the Motion editor based on the selected method."""

    projectChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self._loading = False

        self.method_combo = QComboBox()
        for label, key in _METHODS:
            self.method_combo.addItem(label, key)
        # Gray out the not-yet-implemented methods (default QComboBox model is a
        # QStandardItemModel, so its items expose setEnabled/setToolTip).
        model = self.method_combo.model()
        for i, (_label, key) in enumerate(_METHODS):
            if key in _DISABLED_METHODS:
                item = model.item(i)
                item.setEnabled(False)
                item.setToolTip("Coming with the Ferris Wheel")

        self.program_editor_panel = ProgramEditorPanel()
        self.motion_editor_panel = MotionEditorPanel()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.program_editor_panel)  # frame_sequence
        self.stack.addWidget(self.motion_editor_panel)  # swing / rotation

        layout = QVBoxLayout()
        layout.addWidget(self.method_combo)
        layout.addWidget(self.stack)
        self.setLayout(layout)

        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        self.program_editor_panel.projectChanged.connect(self.projectChanged)
        self.motion_editor_panel.projectChanged.connect(self.projectChanged)

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self._loading = True
        try:
            self.program_editor_panel.set_project(project)
            self.motion_editor_panel.set_project(project)
            index = self.method_combo.findData(project.animation_method)
            self.method_combo.setCurrentIndex(index if index >= 0 else 0)
            self._show_editor_for(project.animation_method)
        finally:
            self._loading = False

    def _show_editor_for(self, method: str) -> None:
        # Frame Sequence -> programs editor; every parametric method -> motion editor.
        self.stack.setCurrentWidget(
            self.program_editor_panel if method == "frame_sequence" else self.motion_editor_panel
        )

    def _on_method_changed(self, _index: int) -> None:
        if self._loading or self.project is None:
            return
        method = self.method_combo.currentData()
        self.project.animation_method = method
        self._show_editor_for(method)
        self.projectChanged.emit()
