# AttractionEditorTool

Authoring and packaging tool for custom OpenRCT2 flat-ride objects.

Replaces the manual sprite-packaging pipeline (manifest generation, `images.dat`
build, `object.json` editing, `.parkobj` packaging, and deploy) with a single
project file and GUI, scoped for v1 to the "rotation family" sprite layout
(animated rotating flat rides with per-direction rider-overlay cars, as used by
the Tilt-A-Whirl).

## Status

v1 in development. See `tools/` for the offline palette-ramp extractor and
`src/attraction_editor/` for the application source.

## Requirements

- Python 3.11+
- PySide6, Pillow (see `pyproject.toml`)

## Development

```
pip install -e .[dev]
pytest
```
