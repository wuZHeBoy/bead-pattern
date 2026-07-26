#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保留 alpha 蒙版里的最大连通域,剔除周边零碎(如主体旁的岩石、地面)。

用法: keep_main.py 输入.png 输出.png [最小占比]
"""
import sys
from collections import deque

import numpy as np
from PIL import Image


def largest_component(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    cur = 0
    sizes = {}
    for sy in range(h):
        for sx in range(w):
            if not mask[sy, sx] or lab[sy, sx]:
                continue
            cur += 1
            n = 0
            q = deque([(sy, sx)])
            lab[sy, sx] = cur
            while q:
                y, x = q.popleft()
                n += 1
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                        lab[ny, nx] = cur
                        q.append((ny, nx))
            sizes[cur] = n
    if not sizes:
        return mask
    keep = max(sizes, key=sizes.get)
    return lab == keep


def main():
    src, dst = sys.argv[1], sys.argv[2]
    a = np.array(Image.open(src).convert("RGBA"))
    mask = a[:, :, 3] > 128
    before = int(mask.sum())
    main_m = largest_component(mask)
    a[:, :, 3] = np.where(main_m, 255, 0).astype("uint8")
    ys, xs = np.where(main_m)
    out = Image.fromarray(a).crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    out.save(dst)
    print(f"主体 {int(main_m.sum())} / 原 {before} px  ({100*main_m.sum()/before:.1f}%)  -> {out.size}")


if __name__ == "__main__":
    main()
