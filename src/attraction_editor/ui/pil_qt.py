"""Helpers for converting Pillow images to Qt pixmaps."""

from __future__ import annotations

from PIL import Image, ImageQt
from PySide6.QtGui import QPixmap


def pil_to_pixmap(image: Image.Image) -> QPixmap:
    """Convert a Pillow image to a QPixmap, independent of its mode."""
    return QPixmap.fromImage(ImageQt.ImageQt(image.convert("RGBA")))
