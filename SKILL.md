---
name: bead-pattern
description: 把任意图片转成拼豆(拼豆/perler/hama/fuse beads)图纸——像素化 + 按品牌色卡(咪小窝/MARD/COCO/漫漫/盼盼)CIEDE2000 色差匹配,产出带色号的网格图、备料清单(每色几颗)和可打印 PDF。触发词:拼豆、拼豆图纸、拼豆模版、图片转拼豆、perler、hama、像素图纸、色号、备料清单、给顾客出图。
---

# bead-pattern · 图片转拼豆图纸

![showcase](examples/showcase.png)

> 上传任意图片 → 自动生成带色号的拼豆图纸 + 备料清单(每色几颗)+ 可打印 PDF。

## 何时用
用户想把一张图(动漫角色 / logo / 照片 / 像素画)做成**拼豆图纸**时,包括:
"帮我把这张图转成拼豆图纸/模版"、"这个用咪小窝色号要几颗豆"、"出个拼豆备料清单"、
"给顾客做张精细/简易的拼豆图"。

## 怎么用
脚本在本项目内,用项目自带 venv 运行(不要用系统 python):

```bash
cd ~/bead-pattern
./.venv/bin/python scripts/generate.py <图片> [选项]
```

### 常用姿势
- 顾客要**好拼款**(限色、去杂、干净):
  `./.venv/bin/python scripts/generate.py 图.jpg --palette mixiaowo --mode simple`
- 要**高还原**(色多、精细):
  `./.venv/bin/python scripts/generate.py 图.png --palette mard --mode fine`
- 固定成品**单板 29×29**:`--size 29x29`;四拼 `--size 58x58`;自定义 `--size 40x30`
- **照片**(有渐变)加抖动:`--mode fine --dither on --max-colors 20`
- 照片抠图更干净:`--remove-bg ai`(需先装 rembg,见下)

### 关键选项
| 选项 | 说明 | 默认 |
|---|---|---|
| `--palette` | `mixiaowo`/`mard`/`coco`/`manman`/`panpan` | mixiaowo |
| `--mode` | `simple`(限色去杂好拼)/ `fine`(高还原) | simple |
| `--size` | `auto` / `29x29` / `58x58` / `宽x高` | auto |
| `--max-side` | auto 时最长边格子数 | 简易32 / 精细50 |
| `--max-colors` | 限色号数(0=不限) | 简易24 / 精细0 |
| `--dither` | `on`/`off`,照片渐变才开 | off |
| `--remove-bg` | `flood`(轻量,纯色底)/`ai`(rembg)/`none` | flood |
| `--out` | 输出目录 | output/<图名>-<档> |

### 产出(在输出目录)
- `pattern.png` — 带色号 + 行列坐标 + 板界的网格图纸
- `shopping-list.csv` / `shopping-list.png` — 备料清单(每色号颗数,降序)
- `pattern.pdf` — 图纸 + 清单合并的可打印版

## 两档怎么选(给顾客解释)
- **简易 simple**:限 ~24 色、清杂点 → 色少好买、好数格、适合新手/小尺寸。
- **精细 fine**:更大网格、不限色 → 还原度高、适合老手/大幅作品。
- 图是**照片**(非扁平色块)再加 `--dither on`,渐变更顺,否则别开(会制造噪点)。

## 可选:AI 抠图
处理真人/复杂背景照片时:
```bash
./.venv/bin/pip install rembg onnxruntime   # 首次会下 ~170MB 模型
./.venv/bin/python scripts/generate.py 照片.jpg --remove-bg ai --mode simple
```

## 注意
- 颜色是实物豆子的近似值,屏幕与实物有色差,批量采购以实物色卡为准。
- 色卡数据来源与许可见 `references/source.md`(clean-room,可商用)。
- 要注册成全局技能:`ln -s ~/bead-pattern ~/.claude/skills/bead-pattern`。
