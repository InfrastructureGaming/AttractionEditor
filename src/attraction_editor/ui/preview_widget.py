"""Shared live-preview surface used by every section that renders a single
composited frame (Layers, Colours, Anchors, Animation) - replaces what used
to be a separate QGraphicsView/QLabel per panel. "Last writer wins": whichever
section last called set_image() is what's currently displayed; there's no
explicit mode switch in this first pass.

Built on AnchorEditorPanel's pre-existing QGraphicsView/QGraphicsScene
pattern, generalized so other sections (plain images, no overlay) can use it
too via add_overlay_item() being optional.

No zoom/pan yet - every set_image() call re-fits the view. That's a known,
deliberately deferred follow-up."""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView, QVBoxLayout, QWidget

from attraction_editor.ui.pil_qt import pil_to_pixmap


class PreviewWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.setLayout(layout)

        self._pixmap_item = None
        self._overlay_items: list[QGraphicsItem] = []

    def set_image(self, image: Image.Image) -> None:
        """Replace whatever the scene currently shows (pixmap and any
        overlay items) with `image`, fitted to the view."""
        self.scene.clear()
        self._overlay_items.clear()

        pixmap = pil_to_pixmap(image)
        self._pixmap_item = self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def clear(self) -> None:
        """Clear the scene entirely (no pixmap, no overlays)."""
        self.scene.clear()
        self._pixmap_item = None
        self._overlay_items.clear()

    def add_overlay_item(self, item: QGraphicsItem) -> None:
        """Layer an interactive item (e.g. AnchorEditorPanel's draggable
        crosshair) on top of whatever set_image() last drew."""
        self.scene.addItem(item)
        self._overlay_items.append(item)

    def clear_overlays(self) -> None:
        for item in self._overlay_items:
            self.scene.removeItem(item)
        self._overlay_items.clear()
