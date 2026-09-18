"""Generate Windows icon variants from the checked-in source PNG."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "assets" / "icons"
SOURCE = ICON_DIR / "app_source.png"
SIZES = (16, 32, 48, 64, 128, 256)


def main() -> None:
    source = Image.open(SOURCE).convert("RGBA")
    frames = []
    for size in SIZES:
        frame = source.resize((size, size), Image.Resampling.LANCZOS)
        frames.append(frame)
        if size in {32, 64, 128, 256}:
            frame.save(ICON_DIR / f"app_{size}.png", format="PNG", optimize=True)
    frames[-1].save(
        ICON_DIR / "app.ico",
        format="ICO",
        append_images=frames[:-1],
        sizes=[(size, size) for size in SIZES],
    )


if __name__ == "__main__":
    main()

