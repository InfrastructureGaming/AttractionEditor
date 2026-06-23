"""Data model for a rotation-family ride project (.ridepkg.json)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DIRECTIONS = 4

LAYER_KINDS = {"static", "animated"}
DITHER_ALGORITHMS = {"floyd_steinberg", "bayer", "atkinson", "none"}


@dataclass
class DirectionAnchor:
    x: int
    y: int


@dataclass
class CarConfig:
    name: str
    sprite_dir: str  # path relative to project_dir, e.g. "Frames/Riders/Car0"


@dataclass
class Layer:
    """One visual plane of the ride's structure, composited with the others
    in list order (RideProject.layers[0] = furthest back, [-1] = furthest
    front) to form the final per-direction, per-frame sprite.

    kind == "static": sprite_dir holds exactly 4 files, dir{0-3}_f0000.png
    (see scanner.static_frame_path - frame 0 of the same naming convention
    as an animated layer) - there's nothing to animate, so there's only ever
    one frame per direction, dithered once and reused for every output frame.
    kind == "animated": sprite_dir holds dir{0-3}_f{0000..N-1}.png (see
    scanner.frame_path), one of which is dithered per output frame.

    dither_algorithm/dither_strength select this layer's dithering
    independently of its kind - e.g. an animated layer dithered with
    Floyd-Steinberg or Atkinson (both error-diffusion) will jitter in
    playback the same way a flattened single-layer image would; Bayer is the
    only one of the three with a frame-content-independent threshold pattern,
    so it's the only choice immune to that. Left as the author's call rather
    than a hardcoded rule. "none" skips dithering for that layer entirely.
    """

    name: str
    sprite_dir: str  # path relative to project_dir
    kind: str  # "static" | "animated"
    dither_algorithm: str = "floyd_steinberg"  # "floyd_steinberg" | "bayer" | "atkinson" | "none"
    dither_strength: int = 32  # meaning is algorithm-specific; ignored when dither_algorithm == "none"


@dataclass
class AnimationPhase:
    """One phase of an animation program: a time-indexed run through
    [frame_start, frame_start + frame_count) of the ride's combined sprite
    sheet, each frame held for ticks_per_frame ticks.

    Mirrors FlatRideAnimationPhase (RideData.h): next_phase is the phase
    index (within the same program) to advance to when this phase ends.
    repeat_until_rotations_complete replays this phase (NumRotations++) until
    NumRotations >= ride.rotations, then advances to next_phase.
    is_final_phase (when not repeating) ends the program -> Status::arriving.
    reset_rotations_on_entry zeroes NumRotations when this phase is entered,
    giving it its own independent ride.rotations budget. Needed when a
    program has more than one repeat_until_rotations_complete phase.
    """

    name: str
    frame_start: int
    frame_count: int
    ticks_per_frame: int = 1
    next_phase: int = 0
    repeat_until_rotations_complete: bool = False
    is_final_phase: bool = False
    reset_rotations_on_entry: bool = False


@dataclass
class AnimationProgram:
    """A selectable animation program: an ordered/looping graph of phases.

    Mirrors FlatRideAnimationProgram (RideData.h). An empty
    RideProject.programs list means legacy single-program, 3-phase
    Start/Loop/End behaviour (FlatRideRotationDescriptor.Programs == nullptr)."""

    name: str
    phases: list[AnimationPhase] = field(default_factory=list)


@dataclass
class ColourScheme:
    """One default colour preset, written into object.json's
    properties.carColours (RideObject::ReadJsonCarColours, RideObject.cpp).
    The engine picks one preset at random when the ride is placed, and the
    ride stays fully recolourable by the player afterward - this is NOT a
    colour baked into the sprites, just a starting point.

    Field names match the engine's actual VehicleColour terminology, verified
    against VehiclePaint.cpp/ImageId.hpp/PaletteIndex.h: trim_colour drives
    the secondary remap zone (palette indices 202-213, reference shade
    "bright_pink" in Blender), tertiary_colour drives the tertiary remap zone
    (indices 46-57, reference shade "yellow"). There is deliberately no
    body_colour/primary field: the engine's primary remap zone (243-254) is
    excluded from openrct2-cli's `-m closest` nearest-match targets
    (ImageImporter::IsChangablePixel, drawing/ImageImporter.cpp), so a
    PNG-authored custom ride has no way to put a pixel there at all - Body
    colour recolouring isn't achievable through this import pipeline.
    """

    trim_colour: str
    tertiary_colour: str


@dataclass
class RideProject:
    """A rotation-family ride: structure layers (see Layer) plus N rider-overlay
    cars, each rendered as 4 directions x frames_per_dir frames. The structure
    layers are composited together (see build.compositing) into the same shape
    before sprite-building; cars remain separate, un-dithered sprite entries."""

    id: str
    name: str
    description: str
    category: str
    frames_per_dir: int
    sprite_width: int
    sprite_height: int
    anchors: list[DirectionAnchor]
    layers: list[Layer]
    cars: list[CarConfig] = field(default_factory=list)
    # Multi-phase/multi-program animation (see AnimationProgram). Empty = legacy
    # single-program, 3-phase Start/Loop/End behaviour; frames_per_dir is then the
    # per-phase frame count as before. Non-empty = frames_per_dir is the TOTAL
    # combined frame count across every phase of every program.
    programs: list[AnimationProgram] = field(default_factory=list)
    # At least one preset (see ColourScheme); the first is what preview panels
    # show by default. Written into object.json's properties.carColours on
    # build - never baked into the shipped sprite pixels.
    colour_schemes: list[ColourScheme] = field(default_factory=lambda: [ColourScheme("white", "white")])
    # Widen (positive) or narrow (negative) which pixels count as inside the
    # secondary/tertiary remap zones during dithering (see build/dither.py's
    # _apply_catch_tolerance_bias) - plain RGB-distance units, 0 = exact
    # nearest-match only (no change from the original fixed behaviour).
    # Lets the artist catch borderline EEVEE-lit pixels that fall just
    # outside a zone without endlessly re-tuning scene lighting/materials,
    # at the cost of some quantisation accuracy for the pixels it touches.
    trim_catch_tolerance: int = 0
    tertiary_catch_tolerance: int = 0
    # Engine ride-object metadata authored into object.json on build (see
    # build/object_json.py's write_object_json) - this tool owns the whole
    # file, not just the build-computed fields, so anything the engine's
    # RideObject reads has to live somewhere here. Scoped to what actually
    # matters for a single-flat-ride-car configuration of "flat_ride_generic"
    # (this project's own modular, self-contained flat-ride object type,
    # always used here - see write_object_json's hardcoded properties.type)
    # - not the full engine schema, most of which (go-kart/chairlift/minigolf
    # physics, etc.) doesn't apply to a flat ride at all. ride_type/
    # rotationMode/car spacing/mass were considered and deliberately dropped:
    # rotationMode only affects rides without a flatRideAnimation block
    # (UpdateFlatRideGeneric() bypasses it entirely once one exists, which it
    # always does here), and spacing/mass are skipped by the engine entirely
    # for any ride with carsPerFlatRide set (Ride.cpp's train-validation
    # logic only runs for tracked rides).
    authors: list[str] = field(default_factory=lambda: ["OpenRCT2 Dev Fork"])
    version: str = "1.0"
    car_tab_offset: int = 0
    car_tab_scale: float = 0.0
    car_num_seats: int = 0
    car_visual: int = 1
    car_draw_order: int = 6
    capacity_text: str = ""  # strings.capacity, e.g. "24 passengers" - free text, not derived from car_num_seats
    # manifest.json (see build/object_json.py's custom_ride_manifest) -
    # CustomRideLoader.cpp's own ride-registration overrides, separate from
    # anything in object.json/the .parkobj. build_cost is whole pounds, 0 =
    # no override (engine keeps FlatRideGenericRTD's own default cost).
    # rating_* are whole numbers 0-9 (per CustomRideLoader.cpp's own
    # documented range) - default 3/2/1 matches the engine's own fallback
    # when "ratings" is absent entirely, so leaving these untouched is
    # equivalent to omitting the override, not an arbitrary placeholder.
    build_cost: int = 0
    rating_excitement: int = 3
    rating_intensity: int = 2
    rating_nausea: int = 1
    output_name: str = ""
    deploy_dir: str | None = None
    openrct2_cli_path: str | None = None

    project_dir: Path | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if len(self.anchors) != DIRECTIONS:
            raise ValueError(f"RideProject requires exactly {DIRECTIONS} anchors, got {len(self.anchors)}")
        if not self.layers:
            raise ValueError("RideProject requires at least one layer")
        if not self.colour_schemes:
            raise ValueError("RideProject requires at least one colour scheme")
        for layer in self.layers:
            if layer.kind not in LAYER_KINDS:
                raise ValueError(f"Layer {layer.name!r} has invalid kind {layer.kind!r}, expected one of {LAYER_KINDS}")
            if layer.dither_algorithm not in DITHER_ALGORITHMS:
                raise ValueError(
                    f"Layer {layer.name!r} has invalid dither_algorithm {layer.dither_algorithm!r}, "
                    f"expected one of {DITHER_ALGORITHMS}"
                )
        if not self.output_name:
            self.output_name = self.id

    @property
    def rotation_frame_mask(self) -> int:
        return self.frames_per_dir - 1

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("project_dir")
        return data

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=4), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> RideProject:
        data = json.loads(path.read_text(encoding="utf-8"))
        anchors = [DirectionAnchor(**a) for a in data.pop("anchors")]
        cars = [CarConfig(**c) for c in data.pop("cars", [])]
        programs = [
            AnimationProgram(name=p["name"], phases=[AnimationPhase(**ph) for ph in p["phases"]])
            for p in data.pop("programs", [])
        ]

        if "layers" in data:
            layers = [Layer(**lyr) for lyr in data.pop("layers")]
        else:
            # Back-compat: pre-layers projects had a single animated core_sprite_dir.
            core_sprite_dir = data.pop("core_sprite_dir")
            layers = [Layer(name="Core", sprite_dir=core_sprite_dir, kind="animated")]

        if "colour_schemes" in data:
            colour_schemes = [ColourScheme(**cs) for cs in data.pop("colour_schemes")]
        else:
            # Back-compat: pre-ColourScheme projects had a single body_colour/
            # trim_colour pair - and those names were themselves one slot off
            # from the engine's actual terminology (see ColourScheme docstring):
            # old body_colour fed the Trim zone, old trim_colour fed Tertiary.
            old_body = data.pop("body_colour", "white")
            old_trim = data.pop("trim_colour", "white")
            colour_schemes = [ColourScheme(trim_colour=old_body, tertiary_colour=old_trim)]

        if "sprite_height" not in data and "sprite_height_negative" in data:
            # Back-compat: pre-single-height projects split the sprite's
            # vertical extent into negative/positive halves relative to the
            # origin point - the same thing the anchor's y now expresses on
            # its own (see build/object_json.py's invalidation_bounds), so
            # total height is just their sum.
            data["sprite_height"] = data.pop("sprite_height_negative") + data.pop("sprite_height_positive")

        return cls(
            anchors=anchors,
            cars=cars,
            programs=programs,
            layers=layers,
            colour_schemes=colour_schemes,
            project_dir=path.parent,
            **data,
        )
