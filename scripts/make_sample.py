#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成一张零版权的测试图:纯色背景上的像素蘑菇。用于验证流水线。"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "samples" / "mushroom.png"

BG = (168, 216, 234)      # 纯色浅蓝背景(测洪水去背景)
CAP = (220, 50, 47)       # 红帽
DOT = (250, 250, 250)     # 白点
STEM = (245, 236, 208)    # 米色柄
EYE = (40, 40, 40)

# 24×24 像素图,0=背景,后面用调色
P = 24
grid = [[0] * P for _ in range(P)]

def disc(cx, cy, r, val):
    for y in range(P):
        for x in range(P):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                grid[y][x] = val

# 帽:上半圆
for y in range(4, 13):
    for x in range(P):
        if (x - 11.5) ** 2 / (9.5 ** 2) + (y - 12) ** 2 / (8.0 ** 2) <= 1 and y <= 12:
            grid[y][x] = 1
# 柄
for y in range(12, 20):
    for x in range(8, 15):
        grid[y][x] = 3
# 白点
for (cx, cy, r) in [(7, 8, 1.6), (15, 7, 1.9), (11, 10, 1.4), (5, 11, 1.2), (17, 11, 1.3)]:
    for y in range(P):
        for x in range(P):
            if grid[y][x] == 1 and (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                grid[y][x] = 2
# 眼睛
grid[15][10] = 4; grid[15][13] = 4

COLORS = {0: BG, 1: CAP, 2: DOT, 3: STEM, 4: EYE}

scale = 18
img = Image.new("RGB", (P * scale, P * scale), BG)
d = ImageDraw.Draw(img)
for y in range(P):
    for x in range(P):
        c = COLORS[grid[y][x]]
        d.rectangle([x * scale, y * scale, (x + 1) * scale, (y + 1) * scale], fill=c)

OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(OUT)
print(f"生成测试图:{OUT} ({img.width}×{img.height})")
