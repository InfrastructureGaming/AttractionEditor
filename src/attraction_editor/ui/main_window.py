"""Top-level window: tabbed panels over a single bound RideProject, plus
File menu actions for creating/opening/saving `.ridepkg.json` project files."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QTabWidget

from attraction_editor.model.project import DIRECTIONS, DirectionAnchor, RideProject
from attraction_editor.ui.anchor_editor_panel import AnchorEditorPanel
from attraction_editor.ui.animation_player_panel import AnimationPlayerPanel
from attraction_editor.ui.build_panel import BuildPanel
from attraction_editor.ui.colour_preview_panel import ColourPreviewPanel
from attraction_editor.ui.program_editor_panel import ProgramEditorPanel
from attraction_editor.ui.project_panel import ProjectPanel
from attraction_editor.ui.sprite_browser_panel import SpriteBrowserPanel

PROJECT_FILE_FILTER = "Ride project (*.ridepkg.json);;All files (*)"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Attraction Editor")

        self.project: RideProject | None = None
        self.project_path: Path | None = None

        self.project_panel = ProjectPanel()
        self.sprite_browser_panel = SpriteBrowserPanel()
        self.anchor_editor_panel = AnchorEditorPanel()
        self.colour_preview_panel = ColourPreviewPanel()
        self.animation_player_panel = AnimationPlayerPanel()
        self.program_editor_panel = ProgramEditorPanel()
        self.build_panel = BuildPanel()

        tabs = QTabWidget()
        tabs.addTab(self.project_panel, "Project")
        tabs.addTab(self.sprite_browser_panel, "Sprites")
        tabs.addTab(self.anchor_editor_panel, "Anchors")
        tabs.addTab(self.colour_preview_panel, "Colours")
        tabs.addTab(self.animation_player_panel, "Animation")
        tabs.addTab(self.program_editor_panel, "Programs & Phases")
        tabs.addTab(self.build_panel, "Build")
        self.setCentralWidget(tabs)

        self._build_menu()

        self.project_panel.projectChanged.connect(self._on_project_panel_changed)
        self.colour_preview_panel.projectChanged.connect(self.project_panel.refresh_colours_from_project)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("&New Project...", self._on_new)
        file_menu.addAction("&Open Project...", self._on_open)
        file_menu.addAction("&Save Project", self._on_save)
        file_menu.addAction("Save Project &As...", self._on_save_as)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close)

    def _on_project_panel_changed(self) -> None:
        self.colour_preview_panel.refresh_from_project()
        self.sprite_browser_panel._reload_frame_set_list()
        self.anchor_editor_panel.reload()
        self.animation_player_panel._reload_car_checks()
        self.animation_player_panel._update_frame()

    def _set_project(self, project: RideProject, path: Path | None) -> None:
        self.project = project
        self.project_path = path

        self.project_panel.set_project(project)
        self.sprite_browser_panel.set_project(project)
        self.anchor_editor_panel.set_project(project)
        self.colour_preview_panel.set_project(project)
        self.animation_player_panel.set_project(project)
        self.program_editor_panel.set_project(project)
        self.build_panel.set_project(project)

        self.setWindowTitle(f"Attraction Editor - {project.name}")

    def _on_new(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select project folder")
        if not directory:
            return

        project = RideProject(
            id="openrct2dev.ride.new_ride",
            name="New Ride",
            description="",
            category="thrill",
            frames_per_dir=128,
            sprite_width=122,
            sprite_height_negative=85,
            sprite_height_positive=85,
            anchors=[DirectionAnchor(x=0, y=0) for _ in range(DIRECTIONS)],
            core_sprite_dir="Frames/Core",
            project_dir=Path(directory),
        )
        self._set_project(project, None)

    def _on_open(self) -> None:
        path_str, _filter = QFileDialog.getOpenFileName(self, "Open project", "", PROJECT_FILE_FILTER)
        if not path_str:
            return

        path = Path(path_str)
        try:
            project = RideProject.load(path)
        except Exception as exc:  # noqa: BLE001 - surface load failures to the user
            QMessageBox.critical(self, "Open Project", f"Could not load project:\n{exc}")
            return

        self._set_project(project, path)

    def _on_save(self) -> None:
        if self.project is None:
            return
        if self.project_path is None:
            self._on_save_as()
            return

        self.project.save(self.project_path)
        self.statusBar().showMessage(f"Saved {self.project_path}", 3000)

    def _on_save_as(self) -> None:
        if self.project is None:
            return

        start_dir = self.project.project_dir or Path.cwd()
        default_path = self.project_path or (Path(start_dir) / f"{self.project.id}.ridepkg.json")

        path_str, _filter = QFileDialog.getSaveFileName(self, "Save project", str(default_path), PROJECT_FILE_FILTER)
        if not path_str:
            return

        path = Path(path_str)
        self.project.project_dir = path.parent
        self.project.save(path)
        self.project_path = path
        self.statusBar().showMessage(f"Saved {path}", 3000)
