"""Build the logo assets from Shuper_Blk.png (white logo on black).

    python packaging/make_logo_assets.py      # needs: pip install vtracer

Writes, cropped to the logo with no background:
- shuper_whisper/assets/logo_mask.png: the logo as an alpha mask; the tray
  icon fills it with the state colour (tray.py).
- assets/shuper_whisper.png: white logo on transparent.
- assets/shuper_whisper.svg: the same, traced to vector paths.
"""

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "Shuper_Blk.png"
MASK = ROOT / "shuper_whisper" / "assets" / "logo_mask.png"
PNG = ROOT / "assets" / "shuper_whisper.png"
SVG = ROOT / "assets" / "shuper_whisper.svg"
PAD = 0.02     # margin around the logo, as a share of its width
MASK_WIDTH = 512


def logo_alpha() -> Image.Image:
    """White on black -> coverage (0-255), cropped to the logo plus a margin."""
    grey = np.asarray(Image.open(SRC).convert("L"), dtype=np.float32)
    alpha = Image.fromarray(np.clip(grey, 0, 255).astype(np.uint8))
    left, top, right, bottom = alpha.point(lambda v: 255 if v > 16 else 0).getbbox()
    pad = int((right - left) * PAD)
    return alpha.crop((max(left - pad, 0), max(top - pad, 0),
                       min(right + pad, alpha.width), min(bottom + pad, alpha.height)))


def main():
    alpha = logo_alpha()
    MASK.parent.mkdir(parents=True, exist_ok=True)
    PNG.parent.mkdir(parents=True, exist_ok=True)
    height = round(alpha.height * MASK_WIDTH / alpha.width)
    alpha.resize((MASK_WIDTH, height), Image.LANCZOS).save(MASK, optimize=True)

    white = Image.new("RGBA", alpha.size, (255, 255, 255, 0))
    white.putalpha(alpha)
    white.save(PNG, optimize=True)

    import vtracer
    # Trace the hard-edged shape black-on-white, with a margin so nothing
    # touches the edge (vtracer bends shapes that do). Polygon mode keeps the
    # shield's corners sharp; spline mode rounded them.
    margin = 40
    canvas = Image.new("L", (alpha.width + 2 * margin, alpha.height + 2 * margin), 0)
    canvas.paste(alpha, (margin, margin))
    traced = ROOT / "assets" / "_trace.png"
    Image.eval(canvas, lambda v: 0 if v > 127 else 255).convert("RGB").save(traced)
    vtracer.convert_image_to_svg_py(str(traced), str(SVG), colormode="binary", mode="polygon",
                                    filter_speckle=8, length_threshold=4.0, path_precision=2)
    traced.unlink()
    svg = SVG.read_text(encoding="utf-8")
    svg = svg.replace('fill="#000000"', 'fill="#FFFFFF"')
    svg = svg.replace(f'width="{canvas.width}" height="{canvas.height}"',
                      f'width="{canvas.width}" height="{canvas.height}" viewBox="0 0 {canvas.width} {canvas.height}"')
    SVG.write_text(svg, encoding="utf-8")
    print(f"{MASK} {MASK_WIDTH}x{height}\n{PNG} {alpha.width}x{alpha.height}\n{SVG} {len(svg) // 1024} KB")


if __name__ == "__main__":
    main()
