"""Build & Package pipeline driven from a single button, with a streamed log
and a build summary (flatRideAnimation values, image count, anchor positions).

Deploying also writes manifest.json alongside the .parkobj - a separate file
this fork's CustomRideLoader.cpp needs to discover the ride at all (see
build/object_json.py's custom_ride_manifest)."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget

from attraction_editor.build.handoff import generate_handoff_report
from attraction_editor.build.object_json import write_object_json
from attraction_editor.build.package import deploy_parkobj, package_parkobj, write_custom_ride_manifest
from attraction_editor.build.sprite_builder import BuildAborted, build_images_dat
from attraction_editor.model.project import RideProject
from attraction_editor.sprites.scanner import FrameSetError, scan_project
from attraction_editor.sprites.validate import validate_project


class _BuildWorker(QObject):
    log = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, project: RideProject) -> None:
        super().__init__()
        self.project = project
        # Set from the GUI thread by cancel(), read here in the worker thread.
        # A plain bool is fine: under the GIL the write and read are atomic, and
        # a one-checkpoint-late observation is harmless (the build just stops at
        # the next checkpoint instead of this one).
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise BuildAborted()

    def run(self) -> None:
        try:
            self._raise_if_cancelled()
            self.log.emit("Validating sprite frames...")
            reports = validate_project(self.project)
            for name, report in reports.items():
                for issue in report.issues:
                    self.log.emit(f"  [{issue.severity.upper()}] {name}: {issue.message}")
            if any(not report.ok for report in reports.values()):
                self.finished.emit(False, "Validation found errors - see log above")
                return

            self._raise_if_cancelled()
            self.log.emit("Scanning frame sets for completeness...")
            try:
                scan_project(self.project)
            except FrameSetError as exc:
                self.log.emit(f"  [ERROR] {exc}")
                self.finished.emit(False, "Frame set scan found errors - see log above")
                return

            self._raise_if_cancelled()
            self.log.emit("Compositing layers (remap + per-layer dithering)...")
            last_pct = [-1]

            def on_dither_progress(done: int, total: int) -> None:
                # The compositing loop's natural cancellation hook: raising here
                # bails out of build_composite_frames mid-frame (its tempdir is
                # cleaned up on the way out).
                self._raise_if_cancelled()
                pct = (done * 100) // total
                if pct != last_pct[0] and pct % 5 == 0:
                    self.log.emit(f"  Compositing: {done}/{total} frames ({pct}%)")
                    last_pct[0] = pct

            self.log.emit("Building images.dat via openrct2-cli (this may take a while)...")
            result = build_images_dat(
                self.project,
                dither=True,
                on_progress=on_dither_progress,
                should_cancel=lambda: self._cancelled,
            )
            self.log.emit(f"  {result.image_count} images, {result.total_data_size} bytes total")

            self._raise_if_cancelled()
            self.log.emit("Writing object.json...")
            write_object_json(self.project)

            self.log.emit("Packaging .parkobj...")
            parkobj_path = package_parkobj(self.project)
            self.log.emit(f"  Created {parkobj_path}")

            if self.project.deploy_dir:
                self.log.emit("Deploying...")
                dest = deploy_parkobj(self.project, parkobj_path)
                self.log.emit(f"  Deployed to {dest}")
                manifest_dest = write_custom_ride_manifest(self.project)
                self.log.emit(f"  Wrote {manifest_dest}")

            self.finished.emit(True, "")
        except BuildAborted:
            self.finished.emit(False, "Build aborted by user.")
        except Exception as exc:  # noqa: BLE001 - surface any failure to the log
            self.finished.emit(False, str(exc))


class BuildPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: RideProject | None = None
        self._thread: QThread | None = None
        self._worker: _BuildWorker | None = None
        self._aborting = False

        self.build_button = QPushButton("Build and Package")
        self.abort_button = QPushButton("Abort")
        self.abort_button.setEnabled(False)  # only live while a build is running
        self.handoff_button = QPushButton("View build summary")

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        self.handoff_text = QTextEdit()
        self.handoff_text.setReadOnly(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.build_button)
        buttons.addWidget(self.abort_button)
        buttons.addWidget(self.handoff_button)

        layout = QVBoxLayout()
        layout.addLayout(buttons)
        layout.addWidget(self.log_text)
        layout.addWidget(self.handoff_text)
        self.setLayout(layout)

        self.build_button.clicked.connect(self._on_build)
        self.abort_button.clicked.connect(self._on_abort)
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

        self._aborting = False
        self.build_button.setEnabled(False)
        self.abort_button.setEnabled(True)
        self.log_text.clear()

        self._thread = QThread(self)
        self._worker = _BuildWorker(self.project)
        self._worker.moveToThread(self._thread)
        self._worker.log.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._thread.started.connect(self._worker.run)
        # Non-blocking teardown (the Qt-recommended pattern): the worker asks
        # the thread's event loop to quit when it finishes, and worker+thread
        # are deleted once the thread has actually stopped. The GUI thread must
        # NEVER wait() on the worker here - an aborted build winds down slowly
        # (terminating the CLI, deleting a large temp dir), and blocking on that
        # froze the whole UI, which is exactly what made an abort look hung.
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    def _on_abort(self) -> None:
        if self._worker is None:
            return
        # Cooperative cancel: the worker stops at its next checkpoint (between
        # steps, mid-composite, or by terminating the CLI) - it can't be killed
        # instantly, so disable the button and report that we're stopping. The
        # UI stays responsive throughout (no wait() on the GUI thread).
        self._aborting = True
        self._worker.cancel()
        self.abort_button.setEnabled(False)
        self._append_log("Aborting build...")

    def _on_finished(self, success: bool, error: str) -> None:
        if success:
            self._append_log("Build completed successfully.")
        elif self._aborting:
            self._append_log("Build aborted.")
        else:
            self._append_log(f"Build failed: {error}")

        self._aborting = False
        self.build_button.setEnabled(True)
        self.abort_button.setEnabled(False)

    def _on_thread_finished(self) -> None:
        # Thread has fully stopped; drop our references (the QObjects delete
        # themselves via deleteLater). Done here, not in _on_finished, so the
        # GUI never blocks waiting for the worker thread to wind down.
        self._thread = None
        self._worker = None

    def _on_handoff(self) -> None:
        if self.project is None:
            return
        self.handoff_text.setPlainText(generate_handoff_report(self.project))
