"""Tests for ui/collapsible_section.py: a foldable header that shows/hides
its content without touching enabled state (which each panel manages
independently via set_project()).

Uses QWidget.isHidden() rather than isVisible() - isVisible() requires the
whole ancestor chain (including the top-level window) to actually be shown
on screen, which qtbot.addWidget() alone doesn't do. isHidden() reflects
just this widget's own explicit hide()/setVisible(False) state, which is
what these tests actually want to verify."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from attraction_editor.ui.collapsible_section import CollapsibleSection


def test_starts_expanded_by_default(qtbot):
    content = QLabel("hello")
    section = CollapsibleSection("Title", content)
    qtbot.addWidget(section)

    assert section.toggle_button.isChecked()
    assert not section.body.isHidden()


def test_can_start_collapsed(qtbot):
    content = QLabel("hello")
    section = CollapsibleSection("Title", content, expanded=False)
    qtbot.addWidget(section)

    assert not section.toggle_button.isChecked()
    assert section.body.isHidden()


def test_toggling_button_shows_and_hides_body(qtbot):
    content = QLabel("hello")
    section = CollapsibleSection("Title", content)
    qtbot.addWidget(section)

    section.toggle_button.setChecked(False)
    assert section.body.isHidden()

    section.toggle_button.setChecked(True)
    assert not section.body.isHidden()


def test_collapsing_does_not_disable_content(qtbot):
    """Collapsing is purely visual - it must never touch enabled state,
    which panels manage independently via their own set_project()."""
    content = QLabel("hello")
    content.setEnabled(True)
    section = CollapsibleSection("Title", content)
    qtbot.addWidget(section)

    section.toggle_button.setChecked(False)
    assert content.isEnabled()

    content.setEnabled(False)
    section.toggle_button.setChecked(True)
    assert not content.isEnabled()  # collapse/expand never overrides this
