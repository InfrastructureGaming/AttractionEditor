"""A foldable section: a clickable header (title + arrow indicator) that
shows/hides its content, used to let the user collapse sections they aren't
using to make better use of the window (see ui/main_window.py's controls
column).

Deliberately NOT built on QGroupBox.setCheckable() - that ties the checked
state to automatically enabling/disabling every child widget, which would
fight with each panel's own independent enabled-state lifecycle (set_project()
enables a panel once a project is loaded, regardless of collapse state).
Collapsing here is purely visual (show/hide); it never touches enabled state."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QToolButton, QVBoxLayout, QWidget


class CollapsibleSection(QWidget):
    def __init__(self, title: str, content: QWidget, parent: QWidget | None = None, *, expanded: bool = True) -> None:
        super().__init__(parent)

        self.toggle_button = QToolButton()
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(expanded)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.toggle_button.setAutoRaise(True)

        self.body = QFrame()
        self.body.setFrameShape(QFrame.Shape.StyledPanel)
        body_layout = QVBoxLayout()
        body_layout.addWidget(content)
        self.body.setLayout(body_layout)
        self.body.setVisible(expanded)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.body)
        self.setLayout(layout)

        self.toggle_button.toggled.connect(self._on_toggled)

    def _on_toggled(self, expanded: bool) -> None:
        self.body.setVisible(expanded)
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
