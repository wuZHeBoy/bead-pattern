#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从已生成的 pattern.png 反推主体轮廓,输出 ASCII 缩略图。

用途:源图丢失时,判断图纸主体形状是否符合预期。
依赖 render_pattern 的固定几何:cell=34, gutter=34, title_h=70。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

CELL = 34
GUTTER = 34
TITLE_H = 70


def cell_fill(px, ox, oy, x, y):
    """取格子内环形采样的中位色,避开中央色号文字。"""
    x0, y0 = ox + x * CELL, oy + y * CELL
    band = []
    for dx, dy in ((5, 5), (CELL - 5, 5), (5, CELL - 5), (CELL - 5, CELL - 5),
                   (CELL // 2, 5), (CELL // 2, CELL - 5)):
        band.append(px[y0 + dy, x0 + dx][:3])
    return np.median(np.array(band, dtype=np.int16), axis=0)


def main():
    path = Path(sys.argv[1])
    gw, gh = int(sys.argv[2]), int(sys.argv[3])
    img = Image.open(path).convert("RGB")
    px = np.array(img)
    ox, oy = GUTTER, TITLE_H + GUTTER

    rows = []
    for y in range(gh):
        line = []
        for x in range(gw):
            c = cell_fill(px, ox, oy, x, y)
            # 白底(255)或棋盘灰(245)判为空格
            if c.min() >= 238 and (c.max() - c.min()) <= 6:
                line.append(".")
            else:
                lum = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
                line.append("#" if lum < 110 else ("+" if lum < 190 else "o"))
        rows.append("".join(line))

    filled = sum(ch != "." for r in rows for ch in r)
    print(f"# {path}  {gw}x{gh}  有豆 {filled} / {gw*gh} 格")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
