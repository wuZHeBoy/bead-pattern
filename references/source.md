# 色卡数据来源与许可说明

## 数据内容
`palettes/*.json` 为各拼豆品牌的**色号 ↔ RGB 对照表**:

| 文件 | 品牌 | 色数 |
|---|---|---|
| `mixiaowo.json` | 咪小窝 | 291 |
| `mard.json` | MARD | 291 |
| `coco.json` | COCO | 291 |
| `manman.json` | 漫漫 | 290 |
| `panpan.json` | 盼盼 | 291 |

字段:`code`(色号)、`hex`(十六进制)、`rgb`([R,G,B])。

## 来源
原始映射数据来自开源项目 **Zippland/perler-beads**（AGPL-3.0）中的
`src/app/colorSystemMapping.json`(291 标准色 → 5 品牌色号)。
本仓库仅提取其中**色号与颜色值的事实型对照关系**,由 `scripts/build_palettes.py`
转换为独立格式,未复制该项目任何源代码。

- 上游仓库: https://github.com/Zippland/perler-beads
- 原始文件已存档: `references/zippland-colorSystemMapping.json`

## 许可说明(clean-room)
- 色号 ↔ RGB 属**事实数据**,不构成受版权保护的独创性表达,可自由使用。
- 本项目 `generate.py` 等全部算法代码为**独立编写**,不衍生自任何 AGPL/闭源代码,
  因此不受上游 AGPL-3.0 的 copyleft 传染,可用于商业用途。
- 建议:对外发布/给顾客使用时,保留本说明的数据来源致谢即可。
- 颜色值均为对实物豆子的**近似测量**,屏幕显示与实物存在色差,批量采购前请以实物色卡为准。
