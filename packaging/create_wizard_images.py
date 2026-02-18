"""Generate Inno Setup wizard BMP images from the ShuperWhisper logo."""

from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGING = PROJECT_ROOT / "packaging"
SRC = PROJECT_ROOT / "Shuper_Blk.png"


def main():
    logo = Image.open(SRC).convert("RGB")

    # Wizard image: 164x314 (left panel of installer wizard)
    wizard = logo.resize((164, 314), Image.LANCZOS)
    wizard.save(PACKAGING / "wizard_image.bmp", format="BMP")
    print("Created wizard_image.bmp (164x314)")

    # Small wizard image: 55x55 (top-right corner of wizard pages)
    small = logo.resize((55, 55), Image.LANCZOS)
    small.save(PACKAGING / "wizard_small_image.bmp", format="BMP")
    print("Created wizard_small_image.bmp (55x55)")


if __name__ == "__main__":
    main()
