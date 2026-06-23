"""A tiny synthetic rotation-family project (2 frames/dir, optional cars) used
to exercise the build/package pipeline against the real openrct2-cli without
the cost of TiltAWhirl's full 128-frame sheets."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from attraction_editor.model.project import CarConfig, ColourScheme, DirectionAnchor, Layer, RideProject
from attraction_editor.sprites.scanner import frame_path, static_frame_path

OPENRCT2_CLI_PATH = Path("G:/GAME DESIGN/OPENRCT2/OpenRCT2/bin/openrct2-cli.exe")

FRAMES_PER_DIR = 2
FRAME_SIZE = (80, 60)


def _make_frame(seed: int = 0) -> Image.Image:
    img = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    for x in range(FRAME_SIZE[0]):
        for y in range(FRAME_SIZE[1]):
            img.putpixel((x, y), (255, (x * 3 + seed) % 256, (y * 5 + seed) % 256, 255))
    return img


def write_animated_layer_frames(sprite_dir: Path, frames_per_dir: int = FRAMES_PER_DIR, seed: int = 0) -> None:
    """Write a dir{0-3}_f{nnnn}.png frame sequence (see scanner.frame_path)."""
    sprite_dir.mkdir(parents=True, exist_ok=True)
    for direction in range(4):
        for frame in range(frames_per_dir):
            _make_frame(seed).save(frame_path(sprite_dir, direction, frame))


def write_static_layer_frames(sprite_dir: Path, seed: int = 0) -> None:
    """Write a dir{0-3}.png single-frame-per-direction set (see
    scanner.static_frame_path)."""
    sprite_dir.mkdir(parents=True, exist_ok=True)
    for direction in range(4):
        _make_frame(seed).save(static_frame_path(sprite_dir, direction))


def make_synthetic_project(project_dir: Path, num_cars: int = 0) -> RideProject:
    """Create a small project on disk under `project_dir` with real PNG
    frames for a single animated "Core" layer (and `num_cars` rider cars),
    and return its RideProject."""
    core_dir = project_dir / "Frames" / "Core"
    write_animated_layer_frames(core_dir)

    cars = []
    for i in range(num_cars):
        car_dir = project_dir / "Frames" / "Riders" / f"Car{i}"
        write_animated_layer_frames(car_dir)
        cars.append(CarConfig(name=f"Car{i}", sprite_dir=f"Frames/Riders/Car{i}"))

    return RideProject(
        id="openrct2dev.ride.synthetic",
        name="Synthetic",
        description="A synthetic test ride.",
        category="thrill",
        frames_per_dir=FRAMES_PER_DIR,
        sprite_width=FRAME_SIZE[0] // 2,
        sprite_height=FRAME_SIZE[1],
        anchors=[DirectionAnchor(-FRAME_SIZE[0] // 2, -FRAME_SIZE[1] // 2) for _ in range(4)],
        layers=[Layer(name="Core", sprite_dir="Frames/Core", kind="animated")],
        cars=cars,
        colour_schemes=[ColourScheme(trim_colour="bright_red", tertiary_colour="white")],
        openrct2_cli_path=str(OPENRCT2_CLI_PATH),
        project_dir=project_dir,
    )


def make_multilayer_synthetic_project(project_dir: Path) -> RideProject:
    """Background static + animated + foreground static, mixing dithering
    algorithms - exercises the full layer/compositing pipeline end to end."""
    write_static_layer_frames(project_dir / "Frames" / "Background", seed=10)
    write_animated_layer_frames(project_dir / "Frames" / "Core", seed=20)
    write_static_layer_frames(project_dir / "Frames" / "Foreground", seed=30)

    return RideProject(
        id="openrct2dev.ride.synthetic_multilayer",
        name="Synthetic Multilayer",
        description="A synthetic multi-layer test ride.",
        category="thrill",
        frames_per_dir=FRAMES_PER_DIR,
        sprite_width=FRAME_SIZE[0] // 2,
        sprite_height=FRAME_SIZE[1],
        anchors=[DirectionAnchor(-FRAME_SIZE[0] // 2, -FRAME_SIZE[1] // 2) for _ in range(4)],
        layers=[
            Layer(name="Background", sprite_dir="Frames/Background", kind="static", dither_algorithm="floyd_steinberg"),
            Layer(name="Core", sprite_dir="Frames/Core", kind="animated", dither_algorithm="bayer"),
            Layer(name="Foreground", sprite_dir="Frames/Foreground", kind="static", dither_algorithm="atkinson"),
        ],
        colour_schemes=[ColourScheme(trim_colour="bright_red", tertiary_colour="white")],
        openrct2_cli_path=str(OPENRCT2_CLI_PATH),
        project_dir=project_dir,
    )
