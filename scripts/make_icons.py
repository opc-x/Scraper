"""生成 PWA 图标：近黑底 + 品牌绿色「S」字标，跟终端风视觉（--background / --primary）保持一致。
之前是纯色圆点占位，iOS 加不到桌面时会退化成系统自动生成的字母图标，用户反而觉得那个更好看——
所以换成真正带 S 字标的版本。有真实 logo 以后整个替换即可。

用法：python -m scripts.make_icons
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public" / "icons"

BACKGROUND = (0x0B, 0x0C, 0x0F, 255)  # --background
PRIMARY = (0x22, 0xC5, 0x5E, 255)  # --primary
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Black.ttf"


def make_icon(size: int, *, safe_ratio: float = 1.0) -> Image.Image:
    img = Image.new("RGBA", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(img)
    font_size = int(size * 0.62 * safe_ratio)
    font = ImageFont.truetype(FONT_PATH, font_size)
    text = "S"
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - w) / 2 - bbox[0]
    y = (size - h) / 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=PRIMARY)
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_icon(192).save(OUT_DIR / "icon-192.png")
    make_icon(512).save(OUT_DIR / "icon-512.png")
    make_icon(180).save(OUT_DIR / "apple-touch-icon.png")
    make_icon(512, safe_ratio=0.7).save(OUT_DIR / "maskable-512.png")  # 留安全边距，别被裁切
    print(f"icons written to {OUT_DIR}")


if __name__ == "__main__":
    main()
