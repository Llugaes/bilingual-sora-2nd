"""Extract only the UI slices used by this local design study.

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
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    args = parser.parse_args()
    output = Path(__file__).parent / "game-assets"
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
            images[atlas].crop(box).save(output / f"{name}.png", optimize=True)
            manifest["slices"][name] = {"entry": entry, "crop": box, "source_sha256": hashes[atlas]}
    (output / "provenance.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
