"""Application entry point for the PySide6 UI."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from attraction_editor.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1200, 800)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
