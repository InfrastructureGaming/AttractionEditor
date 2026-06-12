"""A tiny synthetic rotation-family project (2 frames/dir, optional cars) used
to exercise the build/package pipeline against the real openrct2-cli without
the cost of TiltAWhirl's full 128-frame sheets."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from attraction_editor.model.project import CarConfig, DirectionAnchor, RideProject
from attraction_editor.sprites.scanner import frame_path

OPENRCT2_CLI_PATH = Path("G:/GAME DESIGN/OPENRCT2/OpenRCT2/bin/openrct2-cli.exe")

FRAMES_PER_DIR = 2
FRAME_SIZE = (80, 60)


def _write_frames(sprite_dir: Path) -> None:
    sprite_dir.mkdir(parents=True, exist_ok=True)
    for direction in range(4):
        for frame in range(FRAMES_PER_DIR):
            img = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
            for x in range(FRAME_SIZE[0]):
                for y in range(FRAME_SIZE[1]):
                    img.putpixel((x, y), (255, (x * 3) % 256, (y * 5) % 256, 255))
            img.save(frame_path(sprite_dir, direction, frame))


def make_synthetic_project(project_dir: Path, num_cars: int = 0) -> RideProject:
    """Create a small project on disk under `project_dir` with real PNG
    frames for Core (and `num_cars` rider cars), and return its RideProject."""
    core_dir = project_dir / "Frames" / "Core"
    _write_frames(core_dir)

    cars = []
    for i in range(num_cars):
        car_dir = project_dir / "Frames" / "Riders" / f"Car{i}"
        _write_frames(car_dir)
        cars.append(CarConfig(name=f"Car{i}", sprite_dir=f"Frames/Riders/Car{i}"))

    return RideProject(
        id="openrct2dev.ride.synthetic",
        name="Synthetic",
        description="A synthetic test ride.",
        category="thrill",
        frames_per_dir=FRAMES_PER_DIR,
        sprite_width=FRAME_SIZE[0] // 2,
        sprite_height_negative=FRAME_SIZE[1] // 2,
        sprite_height_positive=FRAME_SIZE[1] // 2,
        anchors=[DirectionAnchor(-FRAME_SIZE[0] // 2, -FRAME_SIZE[1] // 2) for _ in range(4)],
        core_sprite_dir="Frames/Core",
        cars=cars,
        body_colour="bright_red",
        trim_colour="white",
        openrct2_cli_path=str(OPENRCT2_CLI_PATH),
        project_dir=project_dir,
    )
