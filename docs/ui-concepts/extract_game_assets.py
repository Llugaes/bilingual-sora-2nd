"""Extract the original UI slices used by the desktop appearances.

Read-only game input. No hooks, archive edits, or game process access.
Run with a Python environment containing Pillow.
"""
from pathlib import Path
from io import BytesIO
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sora_bilingual.localization.resources import FpacArchive
from tools.inspect_status_sprite_layout import lz4_frame
from PIL import Image

SLICES = {
    "handbook": ("note000", (0, 0, 1754, 934)),
    "guild-emblem": ("window3", (530, 4, 629, 108)),
    "dialogue-frame": ("window3", (1543, 0, 1675, 143)),
    "blue-bar": ("window3", (59, 716, 842, 776)),
    "blue-bar-selected": ("window3", (59, 816, 842, 876)),
    "cursor": ("window3", (756, 925, 854, 975)),
    "gear": ("window3", (1385, 942, 1456, 1016)),
    "camp-background": ("camp000", (128, 16, 2048, 1000)),
    "guild-cover": ("quest_board", (0, 0, 2048, 1080)),
    "guild-page": ("note001", (0, 0, 1520, 934)),
    "bronze-emblem": ("window3", (317, 4, 421, 108)),
    "red-bar": ("window3", (2, 448, 786, 507)),
    "red-bar-selected": ("window3", (2, 544, 786, 604)),
    "tech-frame": ("window3", (1148, 502, 1395, 681)),
    "dark-frame": ("window3", (1398, 0, 1531, 144)),
    "circuit": ("camp001", (78, 18, 240, 75)),
    "orbment-emblem": ("camp008", (4, 8, 214, 214)),
}

# These are low-contrast background textures; full atlas resolution only adds
# decoding and download cost. Metal corners and small icons keep their pixels.
OUTPUT_SIZES = {"camp-background": (960, 492), "guild-cover": (1024, 540)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "game-assets")
    args = parser.parse_args()
    output = args.output
    output.mkdir(exist_ok=True)
    manifest = {"source_archive": "pac/steam/image.pac", "copyright": "Game artwork belongs to Nihon Falcom Corporation.", "slices": {}}
    with FpacArchive(args.game_dir / "pac/steam/image.pac") as archive:
        images = {}
        hashes = {}
        for name, (atlas, box) in SLICES.items():
            entry = f"asset/dx11/image/{atlas}.dds"
            if atlas not in images:
                data = archive.read(entry)
                hashes[atlas] = hashlib.sha256(data).hexdigest()
                images[atlas] = Image.open(BytesIO(lz4_frame(data))).convert("RGBA")
            cropped = images[atlas].crop(box)
            # The BP label belongs to the game gauge, not a settings tab. Build
            # its plain left cap from the same resource's mirrored right cap.
            mirrored_cap = 60 if name in ("red-bar", "red-bar-selected") else 0
            if mirrored_cap:
                cap = cropped.crop((cropped.width - mirrored_cap, 0, cropped.width, cropped.height))
                cropped.paste(cap.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (0, 0))
            if name in OUTPUT_SIZES:
                cropped = cropped.resize(OUTPUT_SIZES[name], Image.Resampling.LANCZOS)
            cropped.save(output / f"{name}.png", optimize=True)
            manifest["slices"][name] = {"entry": entry, "crop": box, "source_sha256": hashes[atlas]}
            if mirrored_cap:
                manifest["slices"][name]["mirrored_right_cap_width"] = mirrored_cap
            if name in OUTPUT_SIZES:
                manifest["slices"][name]["output_size"] = OUTPUT_SIZES[name]
    (output / "provenance.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
