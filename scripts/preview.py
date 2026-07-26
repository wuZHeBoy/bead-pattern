#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 recipe.json 重跑量化,渲染「拼完之后长什么样」的成品预览图。

图纸(pattern.png)是给人照着拼的,格子里写色号;预览图不写字,把每格画成
一颗带孔的圆豆,用来在开拼之前判断成品像不像。

    python scripts/preview.py output/seal-buddha-board87
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate as G  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def rebuild_index(d: Path) -> tuple[np.ndarray, G.Palette]:
    """读 recipe.json,把生成图纸时那条流水线原样再跑一遍,拿回索引网格。"""
    r = json.loads((d / "recipe.json").read_text(encoding="utf-8"))
    pal = G.load_palette(r["palette"])
    img = Image.open(d / r["source"]).convert("RGBA")

    if r["remove_bg"] == "ai":
        img = G.remove_bg_ai(img)
    if r.get("crop_subject") and r["remove_bg"] != "none":
        img = G.crop_to_subject(img)

    gw, gh = (int(v) for v in r["size"].split("x"))
    fit = True
    if r.get("fill"):
        img = G.crop_to_aspect(img, gw, gh)

    grid = G.to_grid(img, gw, gh, fit)
    rgb = grid[:, :, :3].astype(np.float64)
    alpha = grid[:, :, 3]
    if r["remove_bg"] == "flood":
        alpha = G.flood_remove_bg(rgb, alpha)
    mask = alpha > 128

    if r.get("dither") == "on":
        idx = G.match_dither(rgb, mask, pal)
    else:
        idx = G.match_direct(rgb, mask, pal)
    if r.get("despeckle"):
        idx = G.despeckle(idx, min_region=2)
    if r.get("max_colors"):
        idx = G.limit_colors(idx, pal, r["max_colors"])
    return idx, pal


def render_beads(idx: np.ndarray, pal: G.Palette, cell: int = 14,
                 bg: tuple = (250, 250, 250)) -> Image.Image:
    """每格画一颗豆:圆形豆体 + 中间圆孔 + 一点高光,拼出成品的样子。"""
    gh, gw = idx.shape
    ss = 3  # 超采样,画完再缩,边缘不锯齿
    c = cell * ss
    im = Image.new("RGB", (gw * c, gh * c), bg)
    dr = ImageDraw.Draw(im)

    pad = max(1, int(c * 0.06))       # 豆间缝隙
    hole = c * 0.30                   # 孔径
    for y in range(gh):
        for x in range(gw):
            i = idx[y, x]
            if i < 0:
                continue
            rgb = tuple(int(v) for v in pal.rgb[i])
            x0, y0 = x * c + pad, y * c + pad
            x1, y1 = (x + 1) * c - pad, (y + 1) * c - pad
            dr.ellipse([x0, y0, x1, y1], fill=rgb)

            # 高光:左上角一小段浅色弧,让豆子有立体感
            lite = tuple(min(255, int(v * 1.18) + 12) for v in rgb)
            inset = (x1 - x0) * 0.16
            dr.arc([x0 + inset, y0 + inset, x1 - inset, y1 - inset],
                   start=185, end=290, fill=lite, width=max(1, int(c * 0.07)))

            # 孔:比豆体暗一档,别用纯黑,免得整片发脏
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            dark = tuple(int(v * 0.55) for v in rgb)
            dr.ellipse([cx - hole / 2, cy - hole / 2, cx + hole / 2, cy + hole / 2],
                       fill=dark)

    return im.resize((gw * cell, gh * cell), Image.LANCZOS)


def main() -> None:
    ap = argparse.ArgumentParser(description="拼豆成品预览图")
    ap.add_argument("dir", help="图纸目录(含 recipe.json)")
    ap.add_argument("--cell", type=int, default=14, help="每颗豆的像素大小,默认 14")
    ap.add_argument("--out", default=None, help="输出路径,默认 <dir>/preview.png")
    args = ap.parse_args()

    d = Path(args.dir)
    if not (d / "recipe.json").exists():
        sys.exit(f"[错误] 找不到 {d}/recipe.json")

    idx, pal = rebuild_index(d)
    im = render_beads(idx, pal, cell=args.cell)
    out = Path(args.out) if args.out else (d / "preview.png")
    im.save(out)
    gh, gw = idx.shape
    print(f"✓ 预览图 {gw}×{gh} 格 · {im.width}x{im.height}px -> {out}")


if __name__ == "__main__":
    main()
