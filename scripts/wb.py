#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""白点校正:扣掉环境光偏色,让"本该是白的"回到中性白。

暖调逆光/落日照片里,白色物体的像素本身就是淡驼色,色卡匹配会忠实地
配成褐色豆 —— 拼出来是一坨土黄,而人眼看原图却觉得是白的(色彩恒常性)。
这里取主体最亮的一撮像素当白点参考,按通道增益拉回中性。

用法: wb.py 输入.png 输出.png [强度 0-1,默认 1.0]
"""
import sys

import numpy as np
from PIL import Image


def white_balance(img: Image.Image, strength: float = 1.0) -> Image.Image:
    a = np.array(img.convert("RGBA"))
    mask = a[:, :, 3] > 128
    if not mask.any():
        return img
    rgb = a[:, :, :3].astype(np.float64)
    px = rgb[mask]
    lum = 0.299 * px[:, 0] + 0.587 * px[:, 1] + 0.114 * px[:, 2]
    white = px[lum > np.percentile(lum, 95)].mean(0)
    gain = white.max() / np.maximum(white, 1.0)          # 弱通道拉高
    gain = 1.0 + (gain - 1.0) * float(strength)          # 强度插值
    out = np.clip(rgb * gain, 0, 255)
    a[:, :, :3] = out.astype("uint8")
    print(f"白点 {white.round(1)} 增益 {gain.round(3)}")
    return Image.fromarray(a)


def stretch(img: Image.Image, lo_pct: float = 0.0, hi_pct: float = 75.0) -> Image.Image:
    """明度提亮:把主体的大部分亮度推到接近纯白,让白色物体读作白。

    逆光照片里白色物体整体处于中调,匹配后全是中调灰豆,拼出来读作"灰"
    而不是"白"。这里把 hi_pct 分位的亮度映射到 255(默认 75%,即四分之三
    的主体像素进入高光区),三通道同增益 -> 色相不变。
    """
    a = np.array(img.convert("RGBA"))
    mask = a[:, :, 3] > 128
    if not mask.any():
        return img
    rgb = a[:, :, :3].astype(np.float64)
    lum = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    lo, hi = np.percentile(lum[mask], [lo_pct, hi_pct])
    if hi - lo < 1:
        return img
    scale = 255.0 / (hi - lo)
    # 按亮度比例缩放,三通道同增益 -> 色相不变
    with np.errstate(divide="ignore", invalid="ignore"):
        g = np.where(lum > 1, np.clip((lum - lo) * scale, 0, 255) / np.maximum(lum, 1), 1.0)
    a[:, :, :3] = np.clip(rgb * g[:, :, None], 0, 255).astype("uint8")
    print(f"明度拉伸 [{lo:.0f},{hi:.0f}] -> [0,255]")
    return Image.fromarray(a)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    s = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    stretch(white_balance(Image.open(src), s)).save(dst)
    print("->", dst)


if __name__ == "__main__":
    main()
