"""Regenerate the app and installer icons from the logo kit in branding/saims-logo.

    python tools/make_icon.py

The kit itself (SVG, PNG, print files) is built from branding/brand.json; branding/mark.py constructs the
mark's geometry. Small Windows icon sizes use the kit's simplified small-size cut (thicker tick).
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "branding" / "saims-logo" / "icons"


def main() -> None:
    big = Image.open(ICONS / "icon-512.png").convert("RGBA")
    small = {n: Image.open(ICONS / f"favicon-{n}.png").convert("RGBA") for n in (16, 32)}
    big.resize((256, 256), Image.LANCZOS).save(ROOT / "saims" / "assets" / "icon.png")
    big.save(ROOT / "packaging" / "saims-512.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [small[n] if n in small else big.resize((n, n), Image.LANCZOS) for n in sizes]
    frames[-1].save(ROOT / "packaging" / "saims.ico", sizes=[(n, n) for n in sizes], append_images=frames[:-1])
    print("Wrote saims/assets/icon.png, packaging/saims-512.png, packaging/saims.ico")


if __name__ == "__main__":
    main()
