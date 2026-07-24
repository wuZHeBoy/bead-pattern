#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bead-pattern · 图片 → 拼豆图纸生成器

流水线:
    图片 →(去背景)→ 缩放到网格 → 主导色像素化 → CIEDE2000 色差匹配到色卡
        →(可选:抖动 / 限色 / 去杂)→ 图纸 PNG + 备料清单 CSV/PNG + 可打印 PDF

用法示例:
    python generate.py 图.jpg --palette mixiaowo --mode simple
    python generate.py 图.png --palette mard --size 29x29 --mode fine
    python generate.py 图.jpg --max-side 48 --max-colors 20 --remove-bg ai --dither on

设计说明见 README.md;色卡来源见 references/source.md。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, deque
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PALETTE_DIR = ROOT / "palettes"

# 常见成品规格(格子数),midi=5mm 单板 29×29
SIZE_PRESETS = {
    "29x29": (29, 29),
    "58x58": (58, 58),
    "29x58": (29, 58),
    "58x29": (58, 29),
}

# ---------------------------------------------------------------------------
# 色彩科学:sRGB → CIE-Lab,以及 CIEDE2000 感知色差
# ---------------------------------------------------------------------------

def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """rgb: (..., 3) 取值 0-255 → 返回同形状 (..., 3) 的 Lab。"""
    arr = np.asarray(rgb, dtype=np.float64) / 255.0
    arr = np.where(arr > 0.04045, ((arr + 0.055) / 1.055) ** 2.4, arr / 12.92)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505
    x /= 0.95047
    z /= 1.08883
    d = 6.0 / 29.0

    def f(t: np.ndarray) -> np.ndarray:
        return np.where(t > d ** 3, np.cbrt(t), t / (3 * d * d) + 4.0 / 29.0)

    fx, fy, fz = f(x), f(y), f(z)
    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    bb = 200.0 * (fy - fz)
    return np.stack([L, a, bb], axis=-1)


def ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """成对 CIEDE2000 色差。lab1:(M,3) lab2:(N,3) → (M,N)。"""
    L1 = lab1[:, 0][:, None]; a1 = lab1[:, 1][:, None]; b1 = lab1[:, 2][:, None]
    L2 = lab2[:, 0][None, :]; a2 = lab2[:, 1][None, :]; b2 = lab2[:, 2][None, :]

    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cbar = (C1 + C2) / 2.0
    Cbar7 = Cbar ** 7
    G = 0.5 * (1 - np.sqrt(Cbar7 / (Cbar7 + 25.0 ** 7)))

    a1p = (1 + G) * a1
    a2p = (1 + G) * a2
    C1p = np.hypot(a1p, b1)
    C2p = np.hypot(a2p, b2)

    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0

    dLp = L2 - L1
    dCp = C2p - C1p

    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, dhp)
    dhp = np.where(dhp < -180, dhp + 360, dhp)
    dhp = np.where((C1p * C2p) == 0, 0.0, dhp)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp) / 2.0)

    Lbarp = (L1 + L2) / 2.0
    Cbarp = (C1p + C2p) / 2.0

    hsum = h1p + h2p
    habs = np.abs(h1p - h2p)
    hbarp = np.where(
        (C1p * C2p) == 0, hsum,
        np.where(habs <= 180, hsum / 2.0,
                 np.where(hsum < 360, (hsum + 360) / 2.0, (hsum - 360) / 2.0)),
    )

    T = (1
         - 0.17 * np.cos(np.radians(hbarp - 30))
         + 0.24 * np.cos(np.radians(2 * hbarp))
         + 0.32 * np.cos(np.radians(3 * hbarp + 6))
         - 0.20 * np.cos(np.radians(4 * hbarp - 63)))

    dtheta = 30 * np.exp(-(((hbarp - 275) / 25.0) ** 2))
    Cbarp7 = Cbarp ** 7
    Rc = 2 * np.sqrt(Cbarp7 / (Cbarp7 + 25.0 ** 7))
    Sl = 1 + (0.015 * (Lbarp - 50) ** 2) / np.sqrt(20 + (Lbarp - 50) ** 2)
    Sc = 1 + 0.045 * Cbarp
    Sh = 1 + 0.015 * Cbarp * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc

    dE = np.sqrt(
        (dLp / Sl) ** 2
        + (dCp / Sc) ** 2
        + (dHp / Sh) ** 2
        + Rt * (dCp / Sc) * (dHp / Sh)
    )
    return dE


# ---------------------------------------------------------------------------
# 色卡
# ---------------------------------------------------------------------------

class Palette:
    def __init__(self, name: str, rows: List[dict]):
        self.name = name
        self.codes = [r["code"] for r in rows]
        self.hexes = [r["hex"] for r in rows]
        self.rgb = np.array([r["rgb"] for r in rows], dtype=np.float64)  # (N,3)
        self.lab = srgb_to_lab(self.rgb)

    def __len__(self) -> int:
        return len(self.codes)


def load_palette(name: str) -> Palette:
    path = PALETTE_DIR / f"{name}.json"
    if not path.exists():
        avail = ", ".join(sorted(p.stem for p in PALETTE_DIR.glob("*.json")))
        sys.exit(f"[错误] 找不到色卡 '{name}'。可用:{avail}")
    rows = json.loads(path.read_text(encoding="utf-8"))
    return Palette(name, rows)


# ---------------------------------------------------------------------------
# 图片预处理:去背景 + 网格化
# ---------------------------------------------------------------------------

def remove_bg_ai(img: Image.Image) -> Image.Image:
    """用 rembg(AI)抠图。懒加载,未安装则提示。"""
    try:
        from rembg import remove  # type: ignore
    except ImportError:
        sys.exit(
            "[错误] --remove-bg ai 需要 rembg。安装:\n"
            "    ~/bead-pattern/.venv/bin/pip install rembg onnxruntime\n"
            "(首次运行会自动下载 ~170MB 模型)"
        )
    return remove(img.convert("RGBA"))


def to_grid(img: Image.Image, gw: int, gh: int, fit: bool) -> np.ndarray:
    """把图片降采样成 (gh, gw, 4) 的网格 RGBA。

    fit=True:保持比例缩放并居中,空白补透明(适合固定板尺寸)。
    fit=False:直接缩放到 gw×gh(auto 模式已按比例算好网格,不失真)。
    """
    img = img.convert("RGBA")
    if not fit:
        small = img.resize((gw, gh), Image.BOX)  # BOX=区域平均,抗锯齿
        return np.array(small)

    ratio = min(gw / img.width, gh / img.height)
    nw = max(1, round(img.width * ratio))
    nh = max(1, round(img.height * ratio))
    small = img.resize((nw, nh), Image.BOX)
    canvas = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
    canvas.paste(small, ((gw - nw) // 2, (gh - nh) // 2))
    return np.array(canvas)


def flood_remove_bg(grid_rgb: np.ndarray, alpha: np.ndarray, tol: float = 12.0) -> np.ndarray:
    """从四边做洪水填充,把与边界连通且颜色相近的格子标记为背景(alpha=0)。

    适合纯色/浅色背景。tol 为 CIEDE2000 阈值。返回更新后的 alpha。
    """
    gh, gw = alpha.shape
    lab = srgb_to_lab(grid_rgb)
    # 边界种子的平均色
    border = []
    for x in range(gw):
        border.append(grid_rgb[0, x]); border.append(grid_rgb[gh - 1, x])
    for y in range(gh):
        border.append(grid_rgb[y, 0]); border.append(grid_rgb[y, gw - 1])
    seed_lab = srgb_to_lab(np.array(border, dtype=np.float64)).mean(axis=0, keepdims=True)

    flat = lab.reshape(-1, 3)
    dist = ciede2000(flat, seed_lab).reshape(gh, gw)
    similar = dist <= tol

    visited = np.zeros((gh, gw), dtype=bool)
    q: deque = deque()
    for x in range(gw):
        for y in (0, gh - 1):
            if similar[y, x] and not visited[y, x]:
                visited[y, x] = True; q.append((y, x))
    for y in range(gh):
        for x in (0, gw - 1):
            if similar[y, x] and not visited[y, x]:
                visited[y, x] = True; q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < gh and 0 <= nx < gw and not visited[ny, nx] and similar[ny, nx]:
                visited[ny, nx] = True; q.append((ny, nx))

    out = alpha.copy()
    out[visited] = 0
    return out


# ---------------------------------------------------------------------------
# 色卡匹配(可选抖动)
# ---------------------------------------------------------------------------

def match_direct(grid_rgb: np.ndarray, mask: np.ndarray, pal: Palette) -> np.ndarray:
    """对每个有效格取 CIEDE2000 最近色号。返回 idx 网格(-1=空)。"""
    gh, gw = mask.shape
    idx = np.full((gh, gw), -1, dtype=np.int32)
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return idx
    lab = srgb_to_lab(grid_rgb[ys, xs].astype(np.float64))
    nearest = np.argmin(ciede2000(lab, pal.lab), axis=1)
    idx[ys, xs] = nearest.astype(np.int32)
    return idx


def match_dither(grid_rgb: np.ndarray, mask: np.ndarray, pal: Palette) -> np.ndarray:
    """Floyd–Steinberg 抖动 + CIEDE2000 最近色。适合照片渐变。"""
    gh, gw = mask.shape
    work = grid_rgb.astype(np.float64).copy()
    idx = np.full((gh, gw), -1, dtype=np.int32)
    for y in range(gh):
        for x in range(gw):
            if not mask[y, x]:
                continue
            old = work[y, x].copy()
            lab = srgb_to_lab(old[None, :])
            k = int(np.argmin(ciede2000(lab, pal.lab)[0]))
            idx[y, x] = k
            err = old - pal.rgb[k]
            # 误差扩散(仅扩到有效格)
            for ny, nx, w in ((y, x + 1, 7 / 16), (y + 1, x - 1, 3 / 16),
                              (y + 1, x, 5 / 16), (y + 1, x + 1, 1 / 16)):
                if 0 <= ny < gh and 0 <= nx < gw and mask[ny, nx]:
                    work[ny, nx] = np.clip(work[ny, nx] + err * w, 0, 255)
    return idx


# ---------------------------------------------------------------------------
# 后处理:去杂点 + 限色
# ---------------------------------------------------------------------------

def despeckle(idx: np.ndarray, min_region: int = 2) -> np.ndarray:
    """把面积 < min_region 的同色连通块并入相邻多数色,清理杂点。"""
    gh, gw = idx.shape
    out = idx.copy()
    seen = np.zeros((gh, gw), dtype=bool)
    for y0 in range(gh):
        for x0 in range(gw):
            if seen[y0, x0] or out[y0, x0] < 0:
                continue
            color = out[y0, x0]
            comp = []
            q = deque([(y0, x0)]); seen[y0, x0] = True
            while q:
                y, x = q.popleft(); comp.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < gh and 0 <= nx < gw and not seen[ny, nx] and out[ny, nx] == color:
                        seen[ny, nx] = True; q.append((ny, nx))
            if len(comp) >= min_region:
                continue
            neigh = Counter()
            for y, x in comp:
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < gh and 0 <= nx < gw and out[ny, nx] >= 0 and out[ny, nx] != color:
                        neigh[out[ny, nx]] += 1
            if neigh:
                repl = neigh.most_common(1)[0][0]
                for y, x in comp:
                    out[y, x] = repl
    return out


def limit_colors(idx: np.ndarray, pal: Palette, max_colors: int) -> np.ndarray:
    """迭代把用量最少的色号并入色卡中最接近的保留色,直到色数 <= max_colors。"""
    out = idx.copy()
    counts = Counter(int(v) for v in out[out >= 0].ravel())
    while len(counts) > max_colors:
        victim = min(counts, key=lambda c: counts[c])
        others = [c for c in counts if c != victim]
        d = ciede2000(pal.lab[victim][None, :], pal.lab[others])[0]
        repl = others[int(np.argmin(d))]
        out[out == victim] = repl
        counts[repl] += counts.pop(victim)
    return out


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def load_cjk_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return load_font(size)


def _text_color(rgb) -> Tuple[int, int, int]:
    lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return (0, 0, 0) if lum > 140 else (255, 255, 255)


def render_pattern(idx: np.ndarray, pal: Palette, board: Optional[int]) -> Image.Image:
    gh, gw = idx.shape
    cell = 34
    gutter = 34           # 行列坐标区
    title_h = 70
    W = gutter + gw * cell + 12
    H = title_h + gutter + gh * cell + 12
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    code_font = load_font(13)
    coord_font = load_font(15)
    title_font = load_cjk_font(26)
    sub_font = load_cjk_font(15)

    distinct = len(set(int(v) for v in idx[idx >= 0].ravel()))
    total = int((idx >= 0).sum())
    d.text((gutter, 16), f"拼豆图纸 · {pal.name}", font=title_font, fill=(20, 20, 20))
    d.text((gutter, 48),
           f"{gw}×{gh} 格 · {distinct} 色 · 共 {total} 颗", font=sub_font, fill=(90, 90, 90))

    ox, oy = gutter, title_h + gutter
    checker = (245, 245, 245)
    for y in range(gh):
        for x in range(gw):
            x0 = ox + x * cell; y0 = oy + y * cell
            k = int(idx[y, x])
            if k < 0:
                # 空格画浅色棋盘,便于识别镂空
                if (x + y) % 2 == 0:
                    d.rectangle([x0, y0, x0 + cell, y0 + cell], fill=checker)
                continue
            rgb = tuple(int(c) for c in pal.rgb[k])
            d.rectangle([x0, y0, x0 + cell, y0 + cell], fill=rgb)
            code = pal.codes[k]
            tc = _text_color(rgb)
            tb = d.textbbox((0, 0), code, font=code_font)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
            d.text((x0 + (cell - tw) / 2, y0 + (cell - th) / 2 - tb[1]),
                   code, font=code_font, fill=tc)

    # 网格线:细线每格,粗线每 10 格,板界(board)最醒目
    for gx in range(gw + 1):
        x0 = ox + gx * cell
        if board and gx % board == 0:
            col, wdt = (220, 40, 40), 3
        elif gx % 10 == 0:
            col, wdt = (110, 110, 110), 2
        else:
            col, wdt = (205, 205, 205), 1
        d.line([x0, oy, x0, oy + gh * cell], fill=col, width=wdt)
    for gy in range(gh + 1):
        y0 = oy + gy * cell
        if board and gy % board == 0:
            col, wdt = (220, 40, 40), 3
        elif gy % 10 == 0:
            col, wdt = (110, 110, 110), 2
        else:
            col, wdt = (205, 205, 205), 1
        d.line([ox, y0, ox + gw * cell, y0], fill=col, width=wdt)

    # 坐标数字:每 5 格标一次(含第 1 格)
    for gx in range(gw):
        if gx == 0 or (gx + 1) % 5 == 0:
            s = str(gx + 1)
            tb = d.textbbox((0, 0), s, font=coord_font)
            d.text((ox + gx * cell + (cell - (tb[2] - tb[0])) / 2, oy - 22),
                   s, font=coord_font, fill=(70, 70, 70))
    for gy in range(gh):
        if gy == 0 or (gy + 1) % 5 == 0:
            s = str(gy + 1)
            tb = d.textbbox((0, 0), s, font=coord_font)
            d.text((ox - 26, oy + gy * cell + (cell - (tb[3] - tb[1])) / 2),
                   s, font=coord_font, fill=(70, 70, 70))
    return img


def color_stats(idx: np.ndarray, pal: Palette) -> List[Tuple[str, str, int]]:
    counts = Counter(int(v) for v in idx[idx >= 0].ravel())
    rows = [(pal.codes[k], pal.hexes[k], n) for k, n in counts.items()]
    rows.sort(key=lambda r: r[2], reverse=True)
    return rows


def render_shopping_list(rows: List[Tuple[str, str, int]], pal: Palette) -> Image.Image:
    rh = 40
    W = 460
    H = 80 + rh * len(rows) + 20
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    title_font = load_cjk_font(24)
    hdr_font = load_cjk_font(15)
    cell_font = load_font(16)
    total = sum(r[2] for r in rows)
    d.text((24, 20), "备料清单", font=title_font, fill=(20, 20, 20))
    d.text((24, 52), f"{len(rows)} 种色号 · 共 {total} 颗", font=hdr_font, fill=(90, 90, 90))
    y = 84
    for code, hx, n in rows:
        rgb = tuple(int(hx[i:i + 2], 16) for i in (1, 3, 5))
        d.rectangle([24, y + 4, 24 + 28, y + 32], fill=rgb, outline=(180, 180, 180))
        d.text((66, y + 8), f"{code}", font=cell_font, fill=(20, 20, 20))
        d.text((190, y + 8), hx, font=cell_font, fill=(120, 120, 120))
        d.text((330, y + 8), f"{n} 颗", font=cell_font, fill=(20, 20, 20))
        y += rh
    return img


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def parse_size(size: str, max_side: int, img: Image.Image) -> Tuple[int, int, bool, Optional[int]]:
    """返回 (gw, gh, fit, board)。board=画板界线周期(midi 单板 29),自定义尺寸时 None。"""
    if size == "auto":
        if img.width >= img.height:
            gw = max_side
            gh = max(1, round(max_side * img.height / img.width))
        else:
            gh = max_side
            gw = max(1, round(max_side * img.width / img.height))
        return gw, gh, False, 29
    if size in SIZE_PRESETS:
        gw, gh = SIZE_PRESETS[size]
        return gw, gh, True, 29
    if "x" in size:
        w, h = size.lower().split("x")
        return int(w), int(h), True, None
    sys.exit(f"[错误] 无法识别的 --size '{size}'(用 auto / 29x29 / 58x58 / 宽x高)")


def apply_mode_defaults(args: argparse.Namespace) -> None:
    """精细/简易两档:仅在用户未显式指定时填默认。"""
    # 抖动是"照片渐变专用",不绑进精细档(用在扁平色块上会制造噪点、色号爆炸),
    # 需要时用 --dither on 手动开。
    presets = {
        "fine":   dict(max_side=50, dither="off", max_colors=0,  despeckle=False),
        "simple": dict(max_side=32, dither="off", max_colors=24, despeckle=True),
    }
    p = presets[args.mode]
    if args.max_side is None:
        args.max_side = p["max_side"]
    if args.dither is None:
        args.dither = p["dither"]
    if args.max_colors is None:
        args.max_colors = p["max_colors"]
    if args.despeckle is None:
        args.despeckle = p["despeckle"]


def main() -> None:
    ap = argparse.ArgumentParser(description="图片 → 拼豆图纸生成器")
    ap.add_argument("image", help="输入图片路径")
    ap.add_argument("--palette", default="mixiaowo",
                    help="色卡:mixiaowo/mard/coco/manman/panpan(默认 mixiaowo)")
    ap.add_argument("--mode", choices=["fine", "simple"], default="simple",
                    help="精细(高还原)/ 简易(限色去杂,好拼)。默认 simple")
    ap.add_argument("--size", default="auto",
                    help="auto(按图比例)/ 29x29 / 58x58 / 宽x高。默认 auto")
    ap.add_argument("--max-side", type=int, default=None, help="auto 模式下最长边格子数")
    ap.add_argument("--max-colors", type=int, default=None, help="限制色号数(0=不限)")
    ap.add_argument("--dither", choices=["on", "off"], default=None, help="Floyd-Steinberg 抖动")
    ap.add_argument("--despeckle", dest="despeckle", action="store_const", const=True, default=None,
                    help="清理杂点(简易档默认开)")
    ap.add_argument("--no-despeckle", dest="despeckle", action="store_const", const=False,
                    help="关闭杂点清理")
    ap.add_argument("--remove-bg", choices=["none", "flood", "ai"], default="flood",
                    help="去背景:flood(轻量洪水填充,默认)/ ai(rembg 抠图)/ none")
    ap.add_argument("--out", default=None, help="输出目录(默认 output/<图片名>)")
    args = ap.parse_args()

    apply_mode_defaults(args)

    src = Path(args.image)
    if not src.exists():
        sys.exit(f"[错误] 图片不存在:{src}")
    out_dir = Path(args.out) if args.out else (ROOT / "output" / f"{src.stem}-{args.mode}")
    out_dir.mkdir(parents=True, exist_ok=True)

    pal = load_palette(args.palette)
    img = Image.open(src).convert("RGBA")

    if args.remove_bg == "ai":
        img = remove_bg_ai(img)

    gw, gh, fit, board = parse_size(args.size, args.max_side, img)
    grid = to_grid(img, gw, gh, fit)
    rgb = grid[:, :, :3].astype(np.float64)
    alpha = grid[:, :, 3]

    if args.remove_bg == "flood":
        alpha = flood_remove_bg(rgb, alpha)
    mask = alpha > 128

    if mask.sum() == 0:
        sys.exit("[错误] 去背景后没有剩下任何格子,试试 --remove-bg none 或换图。")

    if args.dither == "on":
        idx = match_dither(rgb, mask, pal)
    else:
        idx = match_direct(rgb, mask, pal)

    if args.despeckle:
        idx = despeckle(idx, min_region=2)
    if args.max_colors and args.max_colors > 0:
        idx = limit_colors(idx, pal, args.max_colors)

    # 产出
    pattern = render_pattern(idx, pal, board)
    pattern_path = out_dir / "pattern.png"
    pattern.save(pattern_path)

    rows = color_stats(idx, pal)
    csv_path = out_dir / "shopping-list.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["色号", "HEX", "颗数"])
        for r in rows:
            w.writerow(r)
    list_img = render_shopping_list(rows, pal)
    list_path = out_dir / "shopping-list.png"
    list_img.save(list_path)

    pdf_path = out_dir / "pattern.pdf"
    pattern.convert("RGB").save(pdf_path, save_all=True, append_images=[list_img.convert("RGB")])

    total = sum(r[2] for r in rows)
    print(f"✓ 完成:{gw}×{gh} 格 · {len(rows)} 色 · {total} 颗豆")
    print(f"  图纸    {pattern_path}")
    print(f"  备料表  {csv_path}")
    print(f"  备料图  {list_path}")
    print(f"  打印版  {pdf_path}")
    print("  TOP5 用量:" + " ".join(f"{c}×{n}" for c, _, n in rows[:5]))


if __name__ == "__main__":
    main()
