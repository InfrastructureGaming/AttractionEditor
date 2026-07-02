"""Top-level window: every section stacked in one scrollable column next to
a shared live preview, plus File menu actions for creating/opening/saving
`.ridepkg.json` project files.

No tabs - tab-switching to check the effect of an edit became disruptive as
the feature set grew (layers, dithering, colour schemes all want to be seen
immediately). AnchorEditorPanel/ColourPreviewPanel/AnimationPlayerPanel/
LayersPanel all render into one shared PreviewWidget (see ui/preview_widget.py)
and share one "Direction" combo owned by this window, instead of each having
their own. ProgramEditorPanel's transition-comparison thumbnails and
SpriteBrowserPanel's sample-frame grid stay as their own small embedded
displays - they show multiple images at once, which doesn't fit the single
shared preview surface.

The Colours section also owns a session-only "active preview scheme" (Apply
Scheme / Disable Colours buttons) - the other three preview-rendering panels
read it via set_active_scheme_getter(), so applying a scheme is reflected
everywhere, not just on the Colours section's own preview. This is purely
a UI convenience for *looking at* the ride in colour while editing other
sections; it's never written to the project and never affects what the real
build produces (build/layers.py's production render path is unaffected)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from attraction_editor.model.project import DIRECTIONS, DirectionAnchor, Layer, RideProject
from attraction_editor.ui.anchor_editor_panel import AnchorEditorPanel
from attraction_editor.ui.animation_player_panel import AnimationPlayerPanel
from attraction_editor.ui.build_panel import BuildPanel
from attraction_editor.ui.collapsible_section import CollapsibleSection
from attraction_editor.ui.colour_preview_panel import ColourPreviewPanel
from attraction_editor.ui.layers_panel import LayersPanel
from attraction_editor.ui.preview_widget import PreviewWidget
from attraction_editor.ui.animation_panel import AnimationPanel
from attraction_editor.ui.project_panel import ProjectPanel
from attraction_editor.ui.ride_object_panel import RideObjectPanel
from attraction_editor.ui.sprite_browser_panel import SpriteBrowserPanel

PROJECT_FILE_FILTER = "Ride project (*.ridepkg.json);;All files (*)"


def _wrap_in_group(title: str, widget: QWidget, *, expanded: bool = False) -> CollapsibleSection:
    return CollapsibleSection(title, widget, expanded=expanded)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Attraction Editor")

        self.project: RideProject | None = None
        self.project_path: Path | None = None

        self.project_panel = ProjectPanel()
        self.ride_object_panel = RideObjectPanel()
        self.layers_panel = LayersPanel()
        self.sprite_browser_panel = SpriteBrowserPanel()
        self.anchor_editor_panel = AnchorEditorPanel()
        self.colour_preview_panel = ColourPreviewPanel()
        self.animation_player_panel = AnimationPlayerPanel()
        self.animation_panel = AnimationPanel()
        self.build_panel = BuildPanel()

        # Shared preview surface + the one "Direction" selector every
        # preview-rendering section reads from, instead of each owning its own.
        self.preview_widget = PreviewWidget()
        # Kept as the hidden source of truth for the current direction (every
        # panel reads direction_combo.currentIndex() / its currentIndexChanged);
        # the visible control is now a pair of rotate arrows + a label that drive
        # it, for a more fluid "turn the ride" feel than a dropdown.
        self.direction_combo = QComboBox()
        self.direction_combo.addItems([f"Direction {d}" for d in range(DIRECTIONS)])
        self.direction_combo.hide()

        self.direction_prev_btn = QToolButton()
        self.direction_prev_btn.setArrowType(Qt.ArrowType.LeftArrow)
        self.direction_prev_btn.setToolTip("Rotate view left")
        self.direction_next_btn = QToolButton()
        self.direction_next_btn.setArrowType(Qt.ArrowType.RightArrow)
        self.direction_next_btn.setToolTip("Rotate view right")
        self.direction_label = QLabel()
        self.direction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.direction_label.setMinimumWidth(96)  # steady width so arrows don't shuffle as the text changes

        self.direction_prev_btn.clicked.connect(lambda: self._step_direction(-1))
        self.direction_next_btn.clicked.connect(lambda: self._step_direction(1))
        self.direction_combo.currentIndexChanged.connect(self._update_direction_label)
        self._update_direction_label()

        for panel in (self.anchor_editor_panel, self.colour_preview_panel, self.animation_player_panel, self.layers_panel):
            panel.set_preview_widget(self.preview_widget)
            panel.set_direction_combo(self.direction_combo)

        # The Colours section owns the session's "active preview scheme"
        # state (Apply Scheme / Disable Colours) - the other three panels
        # just read it via this getter when they render.
        for panel in (self.anchor_editor_panel, self.animation_player_panel, self.layers_panel):
            panel.set_active_scheme_getter(self.colour_preview_panel.get_active_scheme)

        # "Preview dithering" also moved onto the Colours section - every
        # panel just reads/disables the same shared checkbox now, the same
        # way they all read direction_combo.
        for panel in (self.anchor_editor_panel, self.animation_player_panel, self.layers_panel):
            panel.set_dither_checkbox(self.colour_preview_panel.dither_check)
        self.colour_preview_panel.dither_check.stateChanged.connect(self._on_dither_check_changed)

        self.direction_combo.currentIndexChanged.connect(self._on_direction_changed)
        self.colour_preview_panel.activeSchemeChanged.connect(self._on_active_scheme_changed)
        self.colour_preview_panel.catchToleranceChanged.connect(self._on_catch_tolerance_changed)

        preview_side = QWidget()
        preview_layout = QVBoxLayout()
        # Navigation bar atop the preview: view-rotation (left) groups with the
        # playback controls (right) - both are "how I'm looking at it", freeing the
        # Animation section below to be purely "how it moves".
        nav_bar = QHBoxLayout()
        nav_bar.addWidget(self.direction_prev_btn)
        nav_bar.addWidget(self.direction_label)
        nav_bar.addWidget(self.direction_next_btn)
        nav_bar.addStretch()
        nav_bar.addWidget(self.animation_player_panel)
        preview_layout.addLayout(nav_bar)
        preview_layout.addWidget(self.preview_widget)
        preview_side.setLayout(preview_layout)

        controls_column = QVBoxLayout()
        controls_column.addWidget(_wrap_in_group("Project", self.project_panel, expanded=True))
        controls_column.addWidget(_wrap_in_group("Ride Object", self.ride_object_panel))
        controls_column.addWidget(_wrap_in_group("Layers", self.layers_panel))
        controls_column.addWidget(_wrap_in_group("Sprites", self.sprite_browser_panel))
        anchors_section = _wrap_in_group("Anchors", self.anchor_editor_panel)
        # The anchor crosshair/grid overlays only belong on the shared preview
        # while the Anchors section is open (it starts collapsed).
        anchors_section.toggled.connect(self.anchor_editor_panel.set_section_expanded)
        controls_column.addWidget(anchors_section)
        controls_column.addWidget(_wrap_in_group("Colours", self.colour_preview_panel))
        # Animation authoring lives here (method dropdown -> Programs & Phases OR
        # Motion editor); playback controls moved up to the preview's nav bar.
        controls_column.addWidget(_wrap_in_group("Animation", self.animation_panel))
        controls_column.addWidget(_wrap_in_group("Build", self.build_panel))
        # Without this, QVBoxLayout distributes leftover vertical space among
        # the sections themselves once they're collapsed (each stretches to
        # fill the gap) instead of staying packed at the top - the stretch
        # absorbs that space instead.
        controls_column.addStretch()

        controls_content = QWidget()
        controls_content.setLayout(controls_column)

        controls_scroll = QScrollArea()
        controls_scroll.setWidget(controls_content)
        controls_scroll.setWidgetResizable(True)

        # QScrollArea.minimumSizeHint() deliberately ignores its content's
        # size (it's designed to handle overflow via scrollbars), so a
        # QSplitter will happily shrink it well past the point where its
        # content needs to scroll horizontally - dragging the divider would
        # otherwise force exactly the horizontal scrolling we don't want.
        # Pin an explicit floor instead, computed from the content's actual
        # minimum width, so the divider simply can't be dragged that far.
        scrollbar_allowance = controls_scroll.verticalScrollBar().sizeHint().width() + 4
        controls_scroll.setMinimumWidth(controls_content.minimumSizeHint().width() + scrollbar_allowance)

        self.splitter = QSplitter()
        self.splitter.addWidget(preview_side)
        self.splitter.addWidget(controls_scroll)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.setCentralWidget(self.splitter)
        self._splitter_initialized = False

        self._build_menu()

        self.project_panel.projectChanged.connect(self._on_project_panel_changed)
        self.layers_panel.projectChanged.connect(self._on_layers_panel_changed)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        if not self._splitter_initialized:
            self._splitter_initialized = True
            # Calling setSizes() in __init__ doesn't work - the window has no
            # real width yet then. Even here, in showEvent, Qt's own internal
            # layout pass for the freshly-shown splitter runs *after* this
            # handler and overwrites it - deferring to the next event loop
            # iteration (0ms timer) lets that settle first.
            #
            # Equal *small* values (e.g. [1, 1]) don't reliably scale into a
            # 50/50 proportional split here - empirically, Qt instead falls
            # back to each pane's own size hint and distributes only the
            # leftover by stretch factor, which is not 50/50 when the two
            # panes' natural size hints differ (they do: the preview side is
            # much narrower than the controls column). Computing the actual
            # half-width explicitly is what reliably works.
            #
            # Guarded by the flag above so later minimize/restore cycles
            # don't reset a user's own drag.
            QTimer.singleShot(0, self._apply_default_splitter_split)

    def _apply_default_splitter_split(self) -> None:
        half = self.splitter.width() // 2
        self.splitter.setSizes([half, half])

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction("&New Project...", self._on_new)
        file_menu.addAction("&Open Project...", self._on_open)
        file_menu.addAction("&Save Project", self._on_save)
        file_menu.addAction("Save Project &As...", self._on_save_as)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close)

    def _step_direction(self, delta: int) -> None:
        """Rotate the view one step, wrapping around - the arrow buttons drive
        the hidden direction_combo, whose currentIndexChanged fans out to every
        preview section exactly as the dropdown used to."""
        self.direction_combo.setCurrentIndex((self.direction_combo.currentIndex() + delta) % DIRECTIONS)

    def _update_direction_label(self, *_args) -> None:
        self.direction_label.setText(f"Direction {self.direction_combo.currentIndex()}")

    def _on_direction_changed(self, *_args) -> None:
        # "Last writer wins" on the shared preview - re-trigger every section
        # that renders into it. AnchorEditorPanel's crosshair is the only
        # *stateful* overlay item among them (set_image() wipes the whole
        # scene, deleting any previously-added overlay), so it must always
        # refresh last or its crosshair gets deleted by a later call here.
        self.colour_preview_panel._reload_preview()
        self.animation_player_panel._update_frame()
        self.layers_panel._reload_preview()
        self.anchor_editor_panel.reload()

    def _on_active_scheme_changed(self) -> None:
        # Apply Scheme / Disable Colours changed the session's active
        # preview scheme - every section reading it via
        # set_active_scheme_getter() needs to re-render. Anchor last, same
        # reason as _on_direction_changed above.
        self.animation_player_panel._update_frame()
        self.layers_panel._reload_preview()
        self.anchor_editor_panel.reload()

    def _on_dither_check_changed(self, *_args) -> None:
        # ColourPreviewPanel refreshes its own preview internally (connected
        # in its own __init__) - this handles every *other* panel reading
        # the same shared checkbox via set_dither_checkbox(). Anchor last,
        # same reason as _on_direction_changed above.
        self.animation_player_panel._update_frame()
        self.layers_panel._reload_preview()
        self.anchor_editor_panel.reload()

    def _on_catch_tolerance_changed(self) -> None:
        # Trim/Tertiary catch tolerance changed RideProject.trim_catch_
        # tolerance/tertiary_catch_tolerance, which affects every layer's
        # dithering (see build/dither.py) - ColourPreviewPanel already
        # refreshed its own preview before emitting; this handles the rest.
        # Anchor last, same reason as _on_direction_changed above.
        self.animation_player_panel._update_frame()
        self.layers_panel._reload_preview()
        self.anchor_editor_panel.reload()

    def _on_project_panel_changed(self) -> None:
        # Sprite dimensions etc. aren't part of AnimationPlayerPanel's frame
        # cache key (see that module's docstring) - invalidate explicitly.
        self.colour_preview_panel.refresh_from_project()
        self.sprite_browser_panel._reload_frame_set_list()
        self.animation_player_panel._invalidate_frame_cache()
        self.animation_player_panel._update_frame()
        self.anchor_editor_panel.reload()

    def _on_layers_panel_changed(self) -> None:
        # Layer order/content/dithering choice (and rider-car list changes,
        # which also live on this panel) all feed the composite, which every
        # other preview panel renders from - refresh them all. Anchor last -
        # see _on_direction_changed's comment on why. Layer edits aren't part
        # of AnimationPlayerPanel's frame cache key either - invalidate explicitly.
        self.sprite_browser_panel._reload_frame_set_list()
        self.colour_preview_panel._reload_preview()
        self.animation_player_panel._invalidate_frame_cache()
        self.animation_player_panel._reload_car_checks()
        self.animation_player_panel._update_frame()
        self.anchor_editor_panel.reload()

    def _set_project(self, project: RideProject, path: Path | None) -> None:
        self.project = project
        self.project_path = path

        # AnchorEditorPanel last - its crosshair is the only stateful overlay
        # item among the shared-preview panels, and set_image() wipes the
        # whole scene, so anything set up before it would otherwise be wiped.
        self.project_panel.set_project(project)
        self.ride_object_panel.set_project(project)
        self.layers_panel.set_project(project)
        self.sprite_browser_panel.set_project(project)
        self.colour_preview_panel.set_project(project)
        self.animation_player_panel.set_project(project)
        self.animation_panel.set_project(project)
        self.build_panel.set_project(project)
        self.anchor_editor_panel.set_project(project)

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
            sprite_height=170,
            anchors=[DirectionAnchor(x=0, y=0) for _ in range(DIRECTIONS)],
            layers=[Layer(name="Core", sprite_dir="Frames/Core", kind="animated")],
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
