"""Run Qt headless (no display required) for pytest-qt tests."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
