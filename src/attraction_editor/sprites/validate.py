"""Blank-frame and duplicate-trajectory diagnostics for rotation-family frame
sets, porting the PowerShell Get-AlphaBBoxFast / Has-AnyAlpha checks to Pillow.

A frame's "bbox" is the bounding box of its non-transparent pixels, or None if
the frame is fully transparent. Sampling a handful of frames per direction and
comparing bbox sequences across cars catches the two failure modes seen during
the TiltAWhirl rider rollout: a fully-blank render pass, and a render pass that
copy-pasted one car's output into another car's folder.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from attraction_editor.model.project import DIRECTIONS, RideProject
from attraction_editor.sprites.scanner import frame_path

BBox = tuple[int, int, int, int]

# Sample frames used for the cheap per-direction/per-car check, matching the
# manual 9-frame sampling used during the TiltAWhirl rider rollout.
SAMPLE_FRAMES: tuple[int, ...] = (0, 16, 32, 48, 64, 80, 96, 112, 127)


@dataclass
class ValidationIssue:
    severity: str  # "error" | "warning"
    message: str


@dataclass
class FrameSetReport:
    name: str
    sample_bboxes: dict[tuple[int, int], BBox | None] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


def alpha_bbox(image: Image.Image) -> BBox | None:
    """Return the bounding box of non-transparent pixels, or None if the
    image has no alpha channel content (fully transparent or opaque-free)."""
    alpha = image.getchannel("A") if "A" in image.getbands() else None
    if alpha is None:
        return None
    return alpha.getbbox()


def has_any_alpha(image: Image.Image) -> bool:
    return alpha_bbox(image) is not None


def _sample_frames(frames_per_dir: int, sample_frames: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(f for f in sample_frames if f < frames_per_dir)


def validate_frame_set(
    sprite_dir,
    frames_per_dir: int,
    name: str = "",
    sample_frames: tuple[int, ...] = SAMPLE_FRAMES,
) -> FrameSetReport:
    """Sample a handful of frames per direction and record their alpha bboxes.

    If every sampled frame in a direction is blank, fall back to a full
    frames_per_dir scan (has_any_alpha) before flagging that direction as
    entirely blank — brief occlusion windows can leave all sampled frames
    empty even though the direction isn't actually broken.
    """
    report = FrameSetReport(name=name or str(sprite_dir))
    samples = _sample_frames(frames_per_dir, sample_frames)

    for direction in range(DIRECTIONS):
        any_sample_non_blank = False

        for frame in samples:
            with Image.open(frame_path(sprite_dir, direction, frame)) as img:
                bbox = alpha_bbox(img)
            report.sample_bboxes[(direction, frame)] = bbox
            if bbox is not None:
                any_sample_non_blank = True

        if not any_sample_non_blank:
            if _direction_fully_blank(sprite_dir, direction, frames_per_dir):
                report.issues.append(
                    ValidationIssue("error", f"Direction {direction} is entirely blank (0/{frames_per_dir} frames)")
                )
            else:
                report.issues.append(
                    ValidationIssue(
                        "warning",
                        f"Direction {direction}: all {len(samples)} sampled frames are blank, "
                        "but other frames contain pixels (likely an occlusion window)",
                    )
                )

    return report


def _direction_fully_blank(sprite_dir, direction: int, frames_per_dir: int) -> bool:
    for frame in range(frames_per_dir):
        with Image.open(frame_path(sprite_dir, direction, frame)) as img:
            if has_any_alpha(img):
                return False
    return True


def detect_duplicate_trajectories(reports: dict[str, FrameSetReport]) -> list[ValidationIssue]:
    """Compare sample-frame bbox sequences pairwise across reports. Identical
    sequences for two different frame sets indicate a render pass was
    accidentally duplicated (e.g. cars 2-6 all rendering as gondola 2)."""
    issues: list[ValidationIssue] = []
    names = list(reports)

    for i, name_a in enumerate(names):
        for name_b in names[i + 1 :]:
            bboxes_a = reports[name_a].sample_bboxes
            bboxes_b = reports[name_b].sample_bboxes
            shared_keys = bboxes_a.keys() & bboxes_b.keys()
            if not shared_keys:
                continue
            if all(bboxes_a[k] == bboxes_b[k] for k in shared_keys):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"{name_a!r} and {name_b!r} have identical sprite trajectories "
                        "at every sampled frame - likely a duplicated render pass",
                    )
                )

    return issues


def validate_programs(project: RideProject) -> list[ValidationIssue]:
    """Validate AnimationProgram/AnimationPhase frame ranges and next_phase
    references against project.frames_per_dir (the TOTAL combined frame count
    across all phases of all programs, when project.programs is non-empty)."""
    issues: list[ValidationIssue] = []

    for program in project.programs:
        num_phases = len(program.phases)
        for phase in program.phases:
            if phase.frame_count <= 0:
                issues.append(
                    ValidationIssue(
                        "error",
                        f"Program {program.name!r} phase {phase.name!r}: frame_count must be "
                        f"positive, got {phase.frame_count}",
                    )
                )
                continue

            frame_end = phase.frame_start + phase.frame_count
            if phase.frame_start < 0 or frame_end > project.frames_per_dir:
                issues.append(
                    ValidationIssue(
                        "error",
                        f"Program {program.name!r} phase {phase.name!r}: frames "
                        f"[{phase.frame_start}, {frame_end}) out of range for "
                        f"frames_per_dir={project.frames_per_dir}",
                    )
                )

            if not (0 <= phase.next_phase < num_phases):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"Program {program.name!r} phase {phase.name!r}: next_phase="
                        f"{phase.next_phase} is out of range (program has {num_phases} phases)",
                    )
                )

    return issues


def validate_project(project: RideProject) -> dict[str, FrameSetReport]:
    """Validate the core structure and every rider car's frame set, plus
    cross-car duplicate-trajectory detection and (if project.programs is
    non-empty) animation phase/program frame-range checks. Returns a dict
    keyed by "Core" / car.name / "Programs"; cross-car issues are appended to
    each involved report's issue list."""
    if project.project_dir is None:
        raise ValueError("RideProject.project_dir is not set")

    reports: dict[str, FrameSetReport] = {}

    core_dir = project.project_dir / project.core_sprite_dir
    reports["Core"] = validate_frame_set(core_dir, project.frames_per_dir, name="Core")

    for car in project.cars:
        car_dir = project.project_dir / car.sprite_dir
        reports[car.name] = validate_frame_set(car_dir, project.frames_per_dir, name=car.name)

    car_reports = {name: r for name, r in reports.items() if name != "Core"}
    for issue in detect_duplicate_trajectories(car_reports):
        for name in car_reports:
            if f"{name!r}" in issue.message:
                reports[name].issues.append(issue)

    if project.programs:
        reports["Programs"] = FrameSetReport(name="Programs", issues=validate_programs(project))

    return reports
