"""Data model for a rotation-family ride project (.ridepkg.json)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DIRECTIONS = 4

LAYER_KINDS = {"static", "animated"}
DITHER_ALGORITHMS = {"floyd_steinberg", "bayer", "atkinson", "none"}

# Breakdowns the tool will author into object.json's "breakdowns" array (parsed
# by RideObject.cpp), spelled exactly as the engine's Breakdown enum. Present
# (even empty) => it replaces the ride type's default breakdown set for this
# ride; empty => the ride never breaks down. Order is display order.
#
# Only the breakdowns fully wired for flat rides today are listed - they halt or
# cut out the ride and need no part-specific animation. restraintsStuck*/
# doorsStuck* are deliberately NOT here: the engine drives those through a
# vehicle's restraint/door sprite state, which our phase-animated flat rides
# don't have, so emitting one would soft-lock the ride. They'll be added once the
# animation-bridge subsystem (freeze the declared restraint/door phase on
# breakdown) lands. brakesFailure is excluded outright - it's tracked-ride-only.
BREAKDOWN_TYPES = [
    "safetyCutOut",
    "controlFailure",
    "vehicleMalfunction",
]


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
    # Optional dir (relative to project_dir) of Blender "zone pass" EXRs that
    # parallel this layer's frames (AOVdir{d}_f{####}.exr, see
    # sprites/scanner.zone_mask_path + build/zone_mask.py). When set, the build
    # reads authored COLOR_TRIM/TERTIARY/PRIMARY masks from them and uses those
    # to classify remap zones instead of the distance/catch-tolerance guess -
    # and it's the only way to author the primary (main/body) zone. None = the
    # legacy distance-based classification for this layer.
    zone_pass_dir: str | None = None


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
    play_reverse walks the same [frame_start, frame_start + frame_count) range
    backwards (last frame first), so a single authored sprite range can drive
    a motion and its inverse without doubling the image count - e.g. animate
    restraints closing once, then a second phase plays that range reversed to
    open them. The engine expands this into a descending TimeToSpriteMap at
    object load (RideObject.cpp); the runtime playback is unchanged, it just
    walks whatever order the map holds. Emitted as "playReverse" only when
    True (see build/object_json.py); harmless on engines that predate reverse
    support, which simply ignore the unknown key and play the range forward.
    """

    name: str
    frame_start: int
    frame_count: int
    ticks_per_frame: int = 1
    next_phase: int = 0
    repeat_until_rotations_complete: bool = False
    is_final_phase: bool = False
    reset_rotations_on_entry: bool = False
    play_reverse: bool = False


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

    Field names match the engine's VehicleColour terminology: body_colour drives
    the primary remap zone (indices 243-254, the player's "Main Color"),
    trim_colour the secondary zone (202-213, "Additional Color 1"),
    tertiary_colour the tertiary zone (46-57, "Additional Color 2") - the
    [Body, Trim, Tertiary] order the engine paints with (GenericFlatRide.cpp).

    body_colour was once impossible: the primary range (243-254) is excluded
    from openrct2-cli's `-m closest` targets (ImageImporter::IsChangablePixel),
    so a Blender render couldn't put a pixel there. The zone-pass authoring path
    (an authored COLOR_PRIMARY mask + snap_to_palette preserving exact 243-254
    pixels) now reaches it, so the Main colour is genuinely recolourable. It's
    optional for back-compat: None falls back to trim_colour when emitted (see
    build/object_json.colour_schemes_block), matching the old two-colour default.
    """

    trim_colour: str
    tertiary_colour: str
    body_colour: str | None = None


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
    # rating_* are 0-9 with up to 2 decimal places (RideRating_t is a
    # fixed16_2dp - see CustomRideLoader.cpp's toRideRating) - default
    # 3.0/2.0/1.0 matches the engine's own fallback when "ratings" is absent
    # entirely, so leaving these untouched is equivalent to omitting the
    # override, not an arbitrary placeholder.
    build_cost: int = 0
    rating_excitement: float = 3.0
    rating_intensity: float = 2.0
    rating_nausea: float = 1.0
    # How much an open, working copy of this ride raises the park's soft guest
    # cap (engine sums BonusValue over all open rides - see Park.cpp's
    # calculateSuggestedMaxGuests). Written into object.json as "bonusValue" and
    # applied per-object via RideObjectEntry::bonusValueOverride. Default 35
    # matches the flat_ride_generic RTD exactly (so it's inert until changed);
    # clamped 0-100 (vanilla rides span ~5 for stalls to ~105 for big coasters).
    bonus_value: int = 35
    BONUS_VALUE_MAX = 100
    # The breakdowns this ride may suffer, written into object.json's
    # "breakdowns" array (see build/object_json.py + BREAKDOWN_TYPES). The tool
    # always emits this, so it always replaces the ride type's default set: an
    # empty list means the ride never breaks down. Defaults to ["safetyCutOut"],
    # which matches what FlatRideGenericRTD gave every custom ride before this
    # field existed - so loading/rebuilding an older project is a no-op.
    breakdowns: list[str] = field(default_factory=lambda: ["safetyCutOut"])
    # Optional path (relative to project_dir, or absolute) to a source image
    # used as the ride's preview thumbnail in the New Ride / construction
    # window. Fitted to 112x112 and built as a flat ("raw" format) sprite at
    # build time (see build/thumbnail.py + sprites/manifest.py) so it takes the
    # engine's masked preview-draw path - feathered border, correctly clipped -
    # instead of being a full-size animation frame cropped to its top-left
    # corner (the long-standing reason custom-ride thumbnails rendered wrong).
    # None = auto-generate the thumbnail from composited structure frame 0
    # (direction 0) at build time, which still fixes the rendering, just
    # without a hand-authored image.
    thumbnail_path: str | None = None
    output_name: str = ""
    deploy_dir: str | None = None
    openrct2_cli_path: str | None = None
    # The ride's reserved land footprint in game tiles - written into
    # manifest.json (see build/object_json.py's custom_ride_manifest) so
    # CustomRideLoader.cpp can select the matching TrackElemType at ride
    # registration. Defaults to 6x6, matching every custom ride's behaviour
    # before this field existed (FlatRideGenericRTD was hardcoded to
    # TrackElemType::flatTrack6x6). Bounded by kMaxSequencesPerPiece - the
    # engine's own hard cap on tiles per track piece (TrackElementDescriptor.h)
    # - not an arbitrary tool-side limit.
    base_footprint_width: int = 6
    base_footprint_length: int = 6

    project_dir: Path | None = field(default=None, compare=False)

    MAX_FOOTPRINT_TILES = 64

    def __post_init__(self) -> None:
        if len(self.anchors) != DIRECTIONS:
            raise ValueError(f"RideProject requires exactly {DIRECTIONS} anchors, got {len(self.anchors)}")
        if not self.layers:
            raise ValueError("RideProject requires at least one layer")
        if not self.colour_schemes:
            raise ValueError("RideProject requires at least one colour scheme")
        if self.base_footprint_width < 1 or self.base_footprint_length < 1:
            raise ValueError(
                f"base_footprint_width/length must each be >= 1, got "
                f"{self.base_footprint_width}x{self.base_footprint_length}"
            )
        if self.base_footprint_width * self.base_footprint_length > self.MAX_FOOTPRINT_TILES:
            raise ValueError(
                f"base footprint {self.base_footprint_width}x{self.base_footprint_length} "
                f"({self.base_footprint_width * self.base_footprint_length} tiles) exceeds the "
                f"engine's {self.MAX_FOOTPRINT_TILES}-tile cap per track piece"
            )
        for breakdown in self.breakdowns:
            if breakdown not in BREAKDOWN_TYPES:
                raise ValueError(
                    f"Unknown breakdown {breakdown!r}, expected one of {BREAKDOWN_TYPES}"
                )
        self.bonus_value = max(0, min(self.BONUS_VALUE_MAX, self.bonus_value))
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
