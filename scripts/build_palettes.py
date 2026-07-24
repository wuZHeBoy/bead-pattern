#!/usr/bin/env python3
"""从事实型色卡映射源(references/zippland-colorSystemMapping.json)构建各品牌调色板。

源数据格式:  { "#FAF4C8": { "MARD": "A01", "COCO": "E02", "咪小窝": "77", ... }, ... }
产出 palettes/<brand>.json:  [ { "code": "A01", "hex": "#FAF4C8", "rgb": [250,244,200] }, ... ]

色号↔RGB 属事实数据,不受版权约束;来源与说明见 references/source.md。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "references" / "zippland-colorSystemMapping.json"
OUT_DIR = ROOT / "palettes"

# 源里的品牌键 -> 输出文件名(拼音/英文,避免中文文件名)
BRANDS = {
    "咪小窝": "mixiaowo",
    "MARD": "mard",
    "COCO": "coco",
    "漫漫": "manman",
    "盼盼": "panpan",
}


def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)]


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(exist_ok=True)

    for brand_key, fname in BRANDS.items():
        rows = []
        seen_codes = set()
        for hex_code, mapping in data.items():
            code = mapping.get(brand_key)
            if not code:
                continue
            # 同一色号可能对应多个近似 HEX,保留首个,避免备料表重复色号
            if code in seen_codes:
                continue
            seen_codes.add(code)
            rows.append({"code": str(code), "hex": hex_code.upper(), "rgb": hex_to_rgb(hex_code)})
        out = OUT_DIR / f"{fname}.json"
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{brand_key:6} -> {out.name}: {len(rows)} 色")


if __name__ == "__main__":
    main()
