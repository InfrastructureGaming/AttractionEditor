"""Build & Package pipeline (Phase 4) driven from a single button, with a
streamed log and the RTD handoff report."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget

from attraction_editor.build.handoff import generate_handoff_report
from attraction_editor.build.object_json import update_object_json
from attraction_editor.build.package import deploy_parkobj, package_parkobj
from attraction_editor.build.sprite_builder import build_images_dat
from attraction_editor.model.project import RideProject
from attraction_editor.sprites.validate import validate_project


class _BuildWorker(QObject):
    log = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, project: RideProject) -> None:
        super().__init__()
        self.project = project

    def run(self) -> None:
        try:
            self.log.emit("Validating sprite frames...")
            reports = validate_project(self.project)
            for name, report in reports.items():
                for issue in report.issues:
                    self.log.emit(f"  [{issue.severity.upper()}] {name}: {issue.message}")
            if any(not report.ok for report in reports.values()):
                self.finished.emit(False, "Validation found errors - see log above")
                return

            self.log.emit("Building images.dat via openrct2-cli (this may take a while)...")
            result = build_images_dat(self.project)
            self.log.emit(f"  {result.image_count} images, {result.total_data_size} bytes total")

            self.log.emit("Updating object.json...")
            update_object_json(self.project)

            self.log.emit("Packaging .parkobj...")
            parkobj_path = package_parkobj(self.project)
            self.log.emit(f"  Created {parkobj_path}")

            if self.project.deploy_dir:
                self.log.emit("Deploying...")
                dest = deploy_parkobj(self.project, parkobj_path)
                self.log.emit(f"  Deployed to {dest}")

            self.finished.emit(True, "")
        except Exception as exc:  # noqa: BLE001 - surface any failure to the log
            self.finished.emit(False, str(exc))


class BuildPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self._thread: QThread | None = None
        self._worker: _BuildWorker | None = None

        self.build_button = QPushButton("Build and Package")
        self.handoff_button = QPushButton("Generate handoff report")

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        self.handoff_text = QTextEdit()
        self.handoff_text.setReadOnly(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.build_button)
        buttons.addWidget(self.handoff_button)

        layout = QVBoxLayout()
        layout.addLayout(buttons)
        layout.addWidget(self.log_text)
        layout.addWidget(self.handoff_text)
        self.setLayout(layout)

        self.build_button.clicked.connect(self._on_build)
        self.handoff_button.clicked.connect(self._on_handoff)

        self.setEnabled(False)

    def set_project(self, project: RideProject) -> None:
        self.project = project
        self.log_text.clear()
        self.handoff_text.clear()
        self.setEnabled(True)

    def _append_log(self, message: str) -> None:
        self.log_text.append(message)

    def _on_build(self) -> None:
        if self.project is None or self._thread is not None:
            return

        self.build_button.setEnabled(False)
        self.log_text.clear()

        self._thread = QThread(self)
        self._worker = _BuildWorker(self.project)
        self._worker.moveToThread(self._thread)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_finished(self, success: bool, error: str) -> None:
        if success:
            self._append_log("Build completed successfully.")
        else:
            self._append_log(f"Build failed: {error}")

        self.build_button.setEnabled(True)
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None

    def _on_handoff(self) -> None:
        if self.project is None:
            return
        self.handoff_text.setPlainText(generate_handoff_report(self.project))
