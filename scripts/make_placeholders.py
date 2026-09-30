r"""Draw the placeholder health-check photos in docs/assets/ (stdlib only; no image library needed).

Each image is a flat colour field with diagonal stripes and the words "PLACEHOLDER - NOT A REAL PHOTO" in big
block letters, so nobody can mistake it for a real photo of a bird (docs/SOURCES.md, "Placeholder images").
They exist only to exercise the photo-input path; they show no bird, sign or disease.

Usage (Windows):
    <venv python> scripts/make_placeholders.py          write the images
    <venv python> scripts/make_placeholders.py --check  exit 1 if a committed image differs (deterministic)
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from clucktalk.domain.photos import PLACEHOLDER_PHOTOS  # noqa: E402

WIDTH, HEIGHT, SCALE = 320, 240, 4
# 5x7 block letters for exactly the characters the caption uses.
GLYPHS = {
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    " ": ("00000",) * 7,
}
LINES = ("PLACEHOLDER", "NOT A REAL", "PHOTO")
GLYPHS.update({"B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110")})


def _row_bits(text: str) -> list[str]:
    rows = [""] * 7
    for ch in text:
        for i, r in enumerate(GLYPHS[ch]):
            rows[i] += r + "0"
    return rows


def _png(pixels: bytearray) -> bytes:
    raw = b"".join(b"\x00" + bytes(pixels[y * WIDTH * 3 : (y + 1) * WIDTH * 3]) for y in range(HEIGHT))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def draw(base: tuple[int, int, int]) -> bytes:
    pixels = bytearray(WIDTH * HEIGHT * 3)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            k = 0.82 if ((x + y) // 16) % 2 else 1.0
            pixels[(y * WIDTH + x) * 3 : (y * WIDTH + x) * 3 + 3] = bytes(int(c * k) for c in base)
    top = 60
    for line in LINES:
        rows = _row_bits(line)
        width = len(rows[0]) * SCALE
        left = (WIDTH - width) // 2
        for ry, bits in enumerate(rows):
            for rx, bit in enumerate(bits):
                if bit != "1":
                    continue
                for dy in range(SCALE):
                    for dx in range(SCALE):
                        px = ((top + ry * SCALE + dy) * WIDTH + left + rx * SCALE + dx) * 3
                        pixels[px : px + 3] = b"\xff\xff\xff"
        top += 7 * SCALE + 14
    return _png(pixels)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for photo in PLACEHOLDER_PHOTOS:
        data = draw(photo.colour)
        target = ROOT / "docs" / "assets" / photo.filename
        if args.check:
            if not target.exists() or target.read_bytes() != data:
                stale.append(photo.filename)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            print(f"wrote docs/assets/{photo.filename} ({len(data):,} bytes)")
    if stale:
        print(f"Out of date: {', '.join(stale)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
