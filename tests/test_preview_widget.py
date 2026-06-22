"""Tests for ui/preview_widget.py: the shared preview surface used by
Layers/Colours/Anchors/Animation instead of each owning its own."""

from __future__ import annotations

from PIL import Image
from PySide6.QtWidgets import QGraphicsEllipseItem

from attraction_editor.ui.preview_widget import PreviewWidget


def test_set_image_adds_pixmap_to_scene(qtbot):
    widget = PreviewWidget()
    qtbot.addWidget(widget)

    widget.set_image(Image.new("RGBA", (10, 8), (255, 0, 0, 255)))

    assert len(widget.scene.items()) == 1
    assert widget.scene.sceneRect().width() == 10
    assert widget.scene.sceneRect().height() == 8


def test_set_image_replaces_previous_pixmap_and_overlays(qtbot):
    widget = PreviewWidget()
    qtbot.addWidget(widget)

    widget.set_image(Image.new("RGBA", (10, 8), (255, 0, 0, 255)))
    overlay = QGraphicsEllipseItem(-2, -2, 4, 4)
    widget.add_overlay_item(overlay)
    assert len(widget.scene.items()) == 2

    widget.set_image(Image.new("RGBA", (5, 5), (0, 255, 0, 255)))

    # Old pixmap and overlay are gone - only the new pixmap remains.
    assert len(widget.scene.items()) == 1
    assert widget.scene.sceneRect().width() == 5


def test_add_overlay_item_layers_on_top_of_current_image(qtbot):
    widget = PreviewWidget()
    qtbot.addWidget(widget)

    widget.set_image(Image.new("RGBA", (10, 8), (255, 0, 0, 255)))
    overlay = QGraphicsEllipseItem(-2, -2, 4, 4)
    widget.add_overlay_item(overlay)

    assert overlay in widget.scene.items()


def test_clear_overlays_removes_only_overlay_items(qtbot):
    widget = PreviewWidget()
    qtbot.addWidget(widget)

    widget.set_image(Image.new("RGBA", (10, 8), (255, 0, 0, 255)))
    overlay = QGraphicsEllipseItem(-2, -2, 4, 4)
    widget.add_overlay_item(overlay)

    widget.clear_overlays()

    assert len(widget.scene.items()) == 1  # pixmap survives
    assert overlay not in widget.scene.items()


def test_clear_removes_everything(qtbot):
    widget = PreviewWidget()
    qtbot.addWidget(widget)

    widget.set_image(Image.new("RGBA", (10, 8), (255, 0, 0, 255)))
    widget.add_overlay_item(QGraphicsEllipseItem(-2, -2, 4, 4))

    widget.clear()

    assert len(widget.scene.items()) == 0
