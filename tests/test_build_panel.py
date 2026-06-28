"""Regression test for the Build pipeline's preflight checks.

validate_project only samples a handful of frames per direction (see
sprites/validate.py's SAMPLE_FRAMES) for cheap blank-frame diagnostics - it
was never meant to guarantee every frame file exists. Before this fix,
_BuildWorker only ran that sampled check, so an animated layer missing a
frame outside the sample set passed "Validation found no errors" and then
blew up deep inside compositing with a raw FileNotFoundError. scan_project
(sprites/scanner.py) is the strict, every-frame check; the worker must run
it before compositing starts."""

from __future__ import annotations

from attraction_editor.sprites.scanner import frame_path
from attraction_editor.ui.build_panel import BuildPanel, _BuildWorker
from tests.fixtures.synthetic import make_synthetic_project


def test_build_worker_reports_missing_frame_outside_validation_sample(tmp_path):
    project = make_synthetic_project(tmp_path)
    core_dir = project.project_dir / project.layers[0].sprite_dir
    # frames_per_dir=2 -> validate_project's SAMPLE_FRAMES only checks frame 0
    # for this project, so deleting frame 1 must slip past validation but
    # still be caught before any compositing work happens.
    frame_path(core_dir, 0, 1).unlink()

    logs: list[str] = []
    results: list[tuple[bool, str]] = []
    worker = _BuildWorker(project)
    worker.log.connect(logs.append)
    worker.finished.connect(lambda ok, msg: results.append((ok, msg)))

    worker.run()

    assert results == [(False, "Frame set scan found errors - see log above")]
    assert any("Missing frame" in line for line in logs)
    # Confirms the premise: this gap really does pass the sampled check.
    assert not any("Validation found errors" in msg for _ok, msg in results)


def test_build_worker_aborts_at_a_step_boundary(tmp_path):
    """A cancel request stops the build at its next checkpoint and reports it
    as a deliberate abort, not a failure."""
    project = make_synthetic_project(tmp_path)
    results: list[tuple[bool, str]] = []
    worker = _BuildWorker(project)
    worker.finished.connect(lambda ok, msg: results.append((ok, msg)))

    worker.cancel()  # requested before run() even reaches the first step
    worker.run()

    assert results == [(False, "Build aborted by user.")]


def test_abort_button_starts_disabled(qtbot, tmp_path):
    panel = BuildPanel()
    qtbot.addWidget(panel)
    panel.set_project(make_synthetic_project(tmp_path))

    assert not panel.abort_button.isEnabled()


def test_on_abort_cancels_worker_and_updates_ui(qtbot, tmp_path):
    panel = BuildPanel()
    qtbot.addWidget(panel)
    panel.set_project(make_synthetic_project(tmp_path))

    class _StubWorker:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    panel._worker = _StubWorker()
    panel.abort_button.setEnabled(True)

    panel._on_abort()

    assert panel._worker.cancelled is True
    assert panel._aborting is True
    assert not panel.abort_button.isEnabled()
    assert "Aborting build..." in panel.log_text.toPlainText()


def test_finished_while_aborting_reports_aborted_not_failed(qtbot, tmp_path):
    panel = BuildPanel()
    qtbot.addWidget(panel)
    panel.set_project(make_synthetic_project(tmp_path))
    panel._aborting = True

    panel._on_finished(False, "Build aborted by user.")

    log = panel.log_text.toPlainText()
    assert "Build aborted." in log
    assert "Build failed" not in log
    # Buttons reset for the next build.
    assert panel.build_button.isEnabled()
    assert not panel.abort_button.isEnabled()
    assert panel._aborting is False
