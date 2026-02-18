"""Generate Inno Setup wizard BMP images from the ShuperWhisper logo."""

from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGING = PROJECT_ROOT / "packaging"
SRC = PROJECT_ROOT / "ShuperWhisper_left.png"

BG_COLOR = (26, 26, 46)  # #1a1a2e — app theme background


def _composite_on_bg(logo: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize logo and composite onto dark background, handling alpha."""
    bg = Image.new("RGB", size, BG_COLOR)
    resized = logo.resize(size, Image.LANCZOS)
    bg.paste(resized, mask=resized.split()[3])
    return bg


def main():
    logo = Image.open(SRC).convert("RGBA")

    # Wizard image: 164x314 (left panel of installer wizard)
    wizard = Image.new("RGB", (164, 314), BG_COLOR)
    logo_fit = _composite_on_bg(logo, (140, 140))
    wizard.paste(logo_fit, ((164 - 140) // 2, 60))
    wizard.save(PACKAGING / "wizard_image.bmp", format="BMP")
    print("Created wizard_image.bmp (164x314)")

    # Small wizard image: 55x55 (top-right corner of wizard pages)
    small = Image.new("RGB", (55, 55), BG_COLOR)
    logo_small = _composite_on_bg(logo, (48, 48))
    small.paste(logo_small, (3, 3))
    small.save(PACKAGING / "wizard_small_image.bmp", format="BMP")
    print("Created wizard_small_image.bmp (55x55)")


if __name__ == "__main__":
    main()
