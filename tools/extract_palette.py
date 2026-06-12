"""One-time offline tool: writes standard_palette.json (ported from
OpenRCT2's StandardPalette in ImageImporter.h) and colour_ramps.json (the
54x12 colour-remap ramps extracted from RCT2's base g1.dat).

Usage:
    python tools/extract_palette.py <path-to-g1.dat>

Background: OpenRCT2 recolours a "Colour" by copying a 12-entry palette-index
ramp into the secondary (202-213) / tertiary (46-57) / primary (243-254)
remap ranges (see ColourMap.cpp / Drawing.Sprite.cpp::GfxDrawSpriteGetPalette).
That ramp is G1 sprite (SPR_G1_PALETTE_2_START + colour_enum_value)'s pixel
data at byte offsets 243-254 - baked sprite data in g1.dat, not available as
C++ source, hence this offline extractor.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "src" / "attraction_editor" / "palette"

SPR_G1_PALETTE_2_START = 4915
COLOUR_NUM_TOTAL = 56
RAMP_START = 243  # PaletteIndex::primaryRemap0
RAMP_LENGTH = 12  # kPaletteLengthRemap

G1_HEADER_FORMAT = "<II"  # numEntries, totalSize
G1_ELEMENT_FORMAT = "<IhhhhHH"  # offset, width, height, xOffset, yOffset, flags, zoomedOffset
G1_ELEMENT_SIZE = struct.calcsize(G1_ELEMENT_FORMAT)

# Colour enum order (0-55), from Colour.h / Colour.cpp's kLookupTable.
COLOUR_NAMES = [
    "black", "grey", "white", "dark_purple", "light_purple", "bright_purple",
    "dark_blue", "light_blue", "icy_blue", "teal", "aquamarine", "saturated_green",
    "dark_green", "moss_green", "bright_green", "olive_green", "dark_olive_green",
    "bright_yellow", "yellow", "dark_yellow", "light_orange", "dark_orange",
    "light_brown", "saturated_brown", "dark_brown", "salmon_pink", "bordeaux_red",
    "saturated_red", "bright_red", "dark_pink", "bright_pink", "light_pink",
    "dark_olive_dark", "dark_olive_light", "saturated_brown_light", "bordeaux_red_dark",
    "bordeaux_red_light", "grass_green_dark", "grass_green_light", "olive_dark",
    "olive_light", "saturated_green_light", "tan_dark", "tan_light", "dull_purple_light",
    "dull_green_dark", "dull_green_light", "saturated_purple_dark", "saturated_purple_light",
    "orange_light", "aqua_dark", "magenta_light", "dull_brown_dark", "dull_brown_light",
    "invisible", "void",
]
assert len(COLOUR_NAMES) == COLOUR_NUM_TOTAL

# StandardPalette from src/openrct2/drawing/ImageImporter.h, converted from
# {blue, green, red, alpha} to [R, G, B] (alpha is 255 for every entry).
STANDARD_PALETTE_RGB: list[list[int]] = [
    # 0 (Unused/Transparent)
    [0, 0, 0],
    # 1-9 (Misc, e.g. font, water, chain lift)
    [1, 1, 1], [2, 2, 2], [3, 3, 3], [4, 4, 4], [5, 5, 5], [6, 6, 6], [7, 7, 7], [8, 8, 8], [9, 9, 9],
    # 10-21 (Grey)
    [23, 35, 35], [35, 51, 51], [47, 67, 67], [63, 83, 83], [75, 99, 99], [91, 115, 115],
    [111, 131, 131], [131, 151, 151], [159, 175, 175], [183, 195, 195], [211, 219, 219], [239, 243, 243],
    # 22-33 (Olive)
    [51, 47, 0], [63, 59, 0], [79, 75, 11], [91, 91, 19], [107, 107, 31], [119, 123, 47],
    [135, 139, 59], [151, 155, 79], [167, 175, 95], [187, 191, 115], [203, 207, 139], [223, 227, 163],
    # 34-45 (Light Brown)
    [67, 43, 7], [87, 59, 11], [111, 75, 23], [127, 87, 31], [143, 99, 39], [159, 115, 51],
    [179, 131, 67], [191, 151, 87], [203, 175, 111], [219, 199, 135], [231, 219, 163], [247, 239, 195],
    # 46-57 (Yellow, also tertiary remap)
    [71, 27, 0], [95, 43, 0], [119, 63, 0], [143, 83, 7], [167, 111, 7], [191, 139, 15],
    [215, 167, 19], [243, 203, 27], [255, 231, 47], [255, 243, 95], [255, 251, 143], [255, 255, 195],
    # 58-69 (Indian Red)
    [35, 0, 0], [79, 0, 0], [95, 7, 7], [111, 15, 15], [127, 27, 27], [143, 39, 39],
    [163, 59, 59], [179, 79, 79], [199, 103, 103], [215, 127, 127], [235, 159, 159], [255, 191, 191],
    # 70-81 (Grass Green)
    [27, 51, 19], [35, 63, 23], [47, 79, 31], [59, 95, 39], [71, 111, 43], [87, 127, 51],
    [99, 143, 59], [115, 155, 67], [131, 171, 75], [147, 187, 83], [163, 203, 95], [183, 219, 103],
    # 82-93 (Olive Green)
    [31, 55, 27], [47, 71, 35], [59, 83, 43], [75, 99, 55], [91, 111, 67], [111, 135, 79],
    [135, 159, 95], [159, 183, 111], [183, 207, 127], [195, 219, 147], [207, 231, 167], [223, 247, 191],
    # 94-105 (Green)
    [15, 63, 0], [19, 83, 0], [23, 103, 0], [31, 123, 0], [39, 143, 7], [55, 159, 23],
    [71, 175, 39], [91, 191, 63], [111, 207, 87], [139, 223, 115], [163, 239, 143], [195, 255, 179],
    # 106-117 (Tan)
    [79, 43, 19], [99, 55, 27], [119, 71, 43], [139, 87, 59], [167, 99, 67], [187, 115, 83],
    [207, 131, 99], [215, 151, 115], [227, 171, 131], [239, 191, 151], [247, 207, 171], [255, 227, 195],
    # 118-129 (Indigo)
    [15, 19, 55], [39, 43, 87], [51, 55, 103], [63, 67, 119], [83, 83, 139], [99, 99, 155],
    [119, 119, 175], [139, 139, 191], [159, 159, 207], [183, 183, 223], [211, 211, 239], [239, 239, 255],
    # 130-141 (Blue)
    [0, 27, 111], [0, 39, 151], [7, 51, 167], [15, 67, 187], [27, 83, 203], [43, 103, 223],
    [67, 135, 227], [91, 163, 231], [119, 187, 239], [143, 211, 243], [175, 231, 251], [215, 247, 255],
    # 142-153 (Sea Green)
    [11, 43, 15], [15, 55, 23], [23, 71, 31], [35, 83, 43], [47, 99, 59], [59, 115, 75],
    [79, 135, 95], [99, 155, 119], [123, 175, 139], [147, 199, 167], [175, 219, 195], [207, 243, 223],
    # 154-165 (Purple)
    [63, 0, 95], [75, 7, 115], [83, 15, 127], [95, 31, 143], [107, 43, 155], [123, 63, 171],
    [135, 83, 187], [155, 103, 199], [171, 127, 215], [191, 155, 231], [215, 195, 243], [243, 235, 255],
    # 166-177 (Red)
    [63, 0, 0], [87, 0, 0], [115, 0, 0], [143, 0, 0], [171, 0, 0], [199, 0, 0],
    [227, 7, 0], [255, 7, 0], [255, 79, 67], [255, 123, 115], [255, 171, 163], [255, 219, 215],
    # 178-189 (Orange)
    [79, 39, 0], [111, 51, 0], [147, 63, 0], [183, 71, 0], [219, 79, 0], [255, 83, 0],
    [255, 111, 23], [255, 139, 51], [255, 163, 79], [255, 183, 107], [255, 203, 135], [255, 219, 163],
    # 190-201 (Water Blue)
    [0, 51, 47], [0, 63, 55], [0, 75, 67], [0, 87, 79], [7, 107, 99], [23, 127, 119],
    [43, 147, 143], [71, 167, 163], [99, 187, 187], [131, 207, 207], [171, 231, 231], [207, 255, 255],
    # 202-213 (Pink, also secondary remap)
    [63, 0, 27], [103, 0, 51], [123, 11, 63], [143, 23, 79], [163, 31, 95], [183, 39, 111],
    [219, 59, 143], [239, 91, 171], [243, 119, 187], [247, 151, 203], [251, 183, 223], [255, 215, 239],
    # 214-225 (Brown)
    [39, 19, 0], [55, 31, 7], [71, 47, 15], [91, 63, 31], [107, 83, 51], [123, 103, 75],
    [143, 127, 107], [163, 147, 127], [187, 171, 147], [207, 195, 171], [231, 219, 195], [255, 243, 223],
    # 226 (Extra grey)
    [55, 75, 75],
    # 227-229 (Extra yellows)
    [255, 183, 0], [255, 219, 0], [255, 255, 0],
    # 230-234 (Water waves)
    [39, 143, 135], [27, 131, 123], [7, 103, 95], [0, 95, 87], [15, 119, 111],
    # 235-239 (Water sparkles)
    [199, 255, 255], [155, 227, 227], [83, 175, 175], [51, 155, 151], [123, 203, 203],
    # 240-242 (Extra grey)
    [67, 91, 91], [83, 107, 107], [99, 123, 123],
    # 243-254 (Primary remap)
    [111, 51, 47], [131, 55, 47], [151, 63, 51], [171, 67, 51], [191, 75, 47], [211, 79, 43],
    [231, 87, 35], [255, 95, 31], [255, 127, 39], [255, 155, 51], [255, 183, 63], [255, 207, 75],
    # 255 (pure white)
    [255, 255, 255],
]
assert len(STANDARD_PALETTE_RGB) == 256


def extract_colour_ramps(g1_path: Path) -> dict[str, list[int]]:
    data = g1_path.read_bytes()

    num_entries, total_size = struct.unpack_from(G1_HEADER_FORMAT, data, 0)
    header_size = struct.calcsize(G1_HEADER_FORMAT)
    if num_entries < SPR_G1_PALETTE_2_START + COLOUR_NUM_TOTAL:
        raise ValueError(f"g1.dat only has {num_entries} entries, need at least "
                         f"{SPR_G1_PALETTE_2_START + COLOUR_NUM_TOTAL}")

    elements_start = header_size
    pixel_data_start = elements_start + num_entries * G1_ELEMENT_SIZE

    ramps: dict[str, list[int]] = {}
    for colour_index, name in enumerate(COLOUR_NAMES):
        sprite_index = SPR_G1_PALETTE_2_START + colour_index
        element_offset = elements_start + sprite_index * G1_ELEMENT_SIZE
        offset, _width, _height, _x, _y, _flags, _zoom = struct.unpack_from(
            G1_ELEMENT_FORMAT, data, element_offset
        )
        ramp_start = pixel_data_start + offset + RAMP_START
        ramp = list(data[ramp_start : ramp_start + RAMP_LENGTH])
        ramps[name] = ramp

    return ramps


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python tools/extract_palette.py <path-to-g1.dat>")
        raise SystemExit(1)

    g1_path = Path(sys.argv[1])
    ramps = extract_colour_ramps(g1_path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "colour_ramps.json").write_text(json.dumps(ramps, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "standard_palette.json").write_text(json.dumps(STANDARD_PALETTE_RGB, indent=2), encoding="utf-8")

    print(f"Wrote {OUTPUT_DIR / 'colour_ramps.json'} ({len(ramps)} colours)")
    print(f"Wrote {OUTPUT_DIR / 'standard_palette.json'} (256 entries)")


if __name__ == "__main__":
    main()
