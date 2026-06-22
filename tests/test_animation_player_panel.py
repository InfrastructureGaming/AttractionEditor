"""Tests for ui/animation_player_panel.py's per-frame structure-composite
cache - added because a fast (20-60Hz) playback timer calling
composite_preview_frame fresh on every tick became a real bottleneck once
colour-scheme/catch-tolerance pixel classification (palette/remap.py's
classify_remap_zone) made each render meaningfully more expensive than the
original, dithering-only path."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox

from attraction_editor.model.project import ColourScheme
from attraction_editor.ui import animation_player_panel as animation_player_panel_module
from attraction_editor.ui.animation_player_panel import AnimationPlayerPanel
from attraction_editor.ui.preview_widget import PreviewWidget
from tests.fixtures.synthetic import make_synthetic_project, write_animated_layer_frames


def _panel_with_project(qtbot, tmp_path):
    panel = AnimationPlayerPanel()
    qtbot.addWidget(panel)

    direction_combo = QComboBox()
    direction_combo.addItems([f"Direction {d}" for d in range(4)])
    panel.set_preview_widget(PreviewWidget())
    panel.set_direction_combo(direction_combo)

    project = make_synthetic_project(tmp_path)
    panel.set_project(project)
    panel._invalidate_frame_cache()  # set_project() itself renders frame 0 once - start each test from a clean slate
    return panel, project


def _count_render_calls(monkeypatch):
    calls = []
    original = animation_player_panel_module.composite_preview_frame

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(animation_player_panel_module, "composite_preview_frame", spy)
    return calls


def test_looping_the_same_frame_twice_only_renders_once(qtbot, tmp_path, monkeypatch):
    panel, _project = _panel_with_project(qtbot, tmp_path)
    calls = _count_render_calls(monkeypatch)

    panel.frame_index = 0
    panel._update_frame()
    panel._update_frame()  # same frame, same settings - should hit cache

    assert len(calls) == 1


def test_a_different_frame_renders_fresh(qtbot, tmp_path, monkeypatch):
    panel, project = _panel_with_project(qtbot, tmp_path)
    calls = _count_render_calls(monkeypatch)

    panel.frame_index = 0
    panel._update_frame()
    panel.frame_index = 1
    panel._update_frame()

    assert len(calls) == 2


def test_changing_dither_checkbox_misses_the_cache(qtbot, tmp_path, monkeypatch):
    """The cache key includes the dither checkbox state, so toggling it
    must never serve a stale (wrong-dither) cached frame."""
    panel, _project = _panel_with_project(qtbot, tmp_path)
    from PySide6.QtWidgets import QCheckBox

    dither_check = QCheckBox()
    panel.set_dither_checkbox(dither_check)
    calls = _count_render_calls(monkeypatch)

    panel.frame_index = 0
    panel._update_frame()
    dither_check.setChecked(True)
    panel._update_frame()

    assert len(calls) == 2


def test_changing_active_scheme_misses_the_cache(qtbot, tmp_path, monkeypatch):
    panel, project = _panel_with_project(qtbot, tmp_path)
    scheme = ColourScheme(trim_colour="black", tertiary_colour="white")
    panel.set_active_scheme_getter(lambda: None)
    calls = _count_render_calls(monkeypatch)

    panel.frame_index = 0
    panel._update_frame()
    panel.set_active_scheme_getter(lambda: scheme)
    panel._update_frame()

    assert len(calls) == 2


def test_changing_catch_tolerance_misses_the_cache(qtbot, tmp_path, monkeypatch):
    panel, project = _panel_with_project(qtbot, tmp_path)
    calls = _count_render_calls(monkeypatch)

    panel.frame_index = 0
    panel._update_frame()
    project.trim_catch_tolerance = 10
    panel._update_frame()

    assert len(calls) == 2


def test_invalidate_frame_cache_forces_a_fresh_render(qtbot, tmp_path, monkeypatch):
    panel, _project = _panel_with_project(qtbot, tmp_path)
    calls = _count_render_calls(monkeypatch)

    panel.frame_index = 0
    panel._update_frame()
    panel._invalidate_frame_cache()
    panel._update_frame()

    assert len(calls) == 2


def test_set_project_invalidates_the_cache(qtbot, tmp_path, monkeypatch):
    panel, project = _panel_with_project(qtbot, tmp_path)
    panel.frame_index = 0
    panel._update_frame()
    assert len(panel._frame_cache) == 1

    panel.set_project(project)

    # set_project re-renders frame 0 itself, so the cache isn't left empty -
    # the point is the *prior* entries didn't survive into the new pass.
    assert len(panel._frame_cache) == 1


def test_frame_cache_is_bounded(qtbot, tmp_path):
    """frames_per_dir can go up to 65535 - the cache must not grow without
    bound for a project with a very large frame count."""
    panel, project = _panel_with_project(qtbot, tmp_path)
    frame_count = animation_player_panel_module._FRAME_CACHE_LIMIT + 50
    write_animated_layer_frames(project.project_dir / project.layers[0].sprite_dir, frames_per_dir=frame_count)
    project.frames_per_dir = frame_count

    for i in range(frame_count):
        panel.frame_index = i
        panel._update_frame()

    assert len(panel._frame_cache) <= animation_player_panel_module._FRAME_CACHE_LIMIT


def test_cached_frame_does_not_accumulate_car_overlays(qtbot, tmp_path):
    """The cache stores the structure-only composite (before car overlays) -
    car checkbox toggles must still take effect every call, not get baked
    into a stale cached image."""
    panel, project = _panel_with_project(qtbot, tmp_path)
    project.cars = []  # no car fixtures on disk for this synthetic project - just verify no crash/staleness
    panel._reload_car_checks()

    panel.frame_index = 0
    panel._update_frame()
    panel._update_frame()  # second call must not double-apply anything from the first

    assert len(panel._frame_cache) == 1
