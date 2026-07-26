#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拼一张「输入图 → 生成图纸(+备料清单)」的对比展示图,用于 README 介绍。

只用自绘零版权素材(mushroom),可安全入库。
运行前需先生成过 output/mushroom-simple/。
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "samples" / "mushroom.png"
PATTERN = ROOT / "output" / "mushroom-simple" / "pattern.png"
LIST = ROOT / "output" / "mushroom-simple" / "shopping-list.png"
OUT = ROOT / "examples" / "showcase.png"

PANEL = 460          # 每块面板目标高度
GAP = 40
PAD = 32
LABEL_H = 46
BG = (250, 250, 250)
ARROW = (90, 90, 90)


def cjk_font(size: int) -> ImageFont.FreeTypeFont:
    for c in ("/System/Library/Fonts/PingFang.ttc",
              "/System/Library/Fonts/STHeiti Medium.ttc",
              "/System/Library/Fonts/Hiragino Sans GB.ttc"):
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def fit(img: Image.Image, h: int) -> Image.Image:
    w = round(img.width * h / img.height)
    return img.resize((w, h), Image.LANCZOS)


def main() -> None:
    if not PATTERN.exists():
        raise SystemExit("先运行:./.venv/bin/python scripts/generate.py "
                         "assets/samples/mushroom.png --palette mixiaowo --mode simple")

    src = fit(Image.open(SRC).convert("RGB"), PANEL)
    pat = fit(Image.open(PATTERN).convert("RGB"), PANEL)
    lst = fit(Image.open(LIST).convert("RGB"), PANEL)

    arrow_w = 90
    title_h = 70
    total_w = PAD * 2 + src.width + GAP + arrow_w + GAP + pat.width + GAP + lst.width
    total_h = title_h + LABEL_H + PANEL + PAD

    canvas = Image.new("RGB", (total_w, total_h), BG)
    d = ImageDraw.Draw(canvas)

    tfont = cjk_font(30)
    sfont = cjk_font(18)
    lfont = cjk_font(20)
    d.text((PAD, 20), "bead-pattern · 图片转拼豆图纸", font=tfont, fill=(20, 20, 20))
    d.text((PAD, 56), "上传任意图片,自动生成带色号的拼豆图纸和备料清单",
           font=sfont, fill=(110, 110, 110))

    top = title_h + LABEL_H
    x = PAD

    def label(cx: int, text: str, color=(70, 70, 70)):
        tb = d.textbbox((0, 0), text, font=lfont)
        d.text((cx - (tb[2] - tb[0]) / 2, title_h + 8), text, font=lfont, fill=color)

    # 原图
    canvas.paste(src, (x, top))
    label(x + src.width // 2, "① 输入图片")
    x += src.width + GAP

    # 箭头
    ay = top + PANEL // 2
    d.line([x + 10, ay, x + arrow_w - 10, ay], fill=ARROW, width=5)
    d.polygon([(x + arrow_w - 10, ay - 12), (x + arrow_w - 10, ay + 12),
               (x + arrow_w + 6, ay)], fill=ARROW)
    d.text((x + 6, ay - 40), "生成", font=sfont, fill=ARROW)
    x += arrow_w + GAP

    # 图纸
    canvas.paste(pat, (x, top))
    label(x + pat.width // 2, "② 色号图纸", (200, 40, 40))
    x += pat.width + GAP

    # 清单
    canvas.paste(lst, (x, top))
    label(x + lst.width // 2, "③ 备料清单", (200, 40, 40))

    OUT.parent.mkdir(exist_ok=True)
    canvas.save(OUT)
    print(f"对比图已生成:{OUT} ({canvas.width}×{canvas.height})")


if __name__ == "__main__":
    main()
