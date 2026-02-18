"""Convert ShuperWhisper_left.png to a multi-size .ico file."""

from pathlib import Path

from PIL import Image

SIZES = [16, 32, 48, 64, 128, 256]
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "ShuperWhisper_left.png"
DST = PROJECT_ROOT / "packaging" / "ShuperWhisper.ico"


def main():
    img = Image.open(SRC).convert("RGBA")
    resized = [img.resize((s, s), Image.LANCZOS) for s in SIZES]
    resized[-1].save(
        DST,
        format="ICO",
        append_images=resized[:-1],
        sizes=[(s, s) for s in SIZES],
    )
    print(f"Created {DST} with sizes: {SIZES}")


if __name__ == "__main__":
    main()
