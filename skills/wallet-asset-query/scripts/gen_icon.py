# -*- coding: utf-8 -*-
"""钱包资产查询 Skill 图标：深蓝渐变底 + 白色钱包 + 链块意象 + 金色总额徽标"""
from PIL import Image, ImageDraw, ImageFont
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "icon-512.png"
SIZE = 512

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

top, bottom = (47, 108, 205), (15, 38, 84)
grad = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
gd = ImageDraw.Draw(grad)
for y in range(SIZE):
    t = y / (SIZE - 1)
    gd.line([(0, y), (SIZE, y)],
            fill=(int(top[0] + (bottom[0] - top[0]) * t),
                  int(top[1] + (bottom[1] - top[1]) * t),
                  int(top[2] + (bottom[2] - top[2]) * t), 255))
mask = Image.new("L", (SIZE, SIZE), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=96, fill=255)
img.paste(grad, (0, 0), mask)

try:
    f_sym = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 74)
    f_txt = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 44)
except Exception:
    f_sym = f_txt = ImageFont.load_default()

# 链块意象：左上与右下三连块，象征多链
def blocks(x, y, color):
    for i in range(3):
        d.rounded_rectangle([x + i * 62, y, x + i * 62 + 46, y + 46], radius=10,
                            outline=color, width=7)
        if i:
            d.line([(x + i * 62 - 16, y + 23), (x + i * 62, y + 23)], fill=color, width=7)

blocks(64, 64, (120, 170, 240, 255))
blocks(266, 400, (120, 170, 240, 255))

# 白色钱包主体
wx0, wy0, wx1, wy1 = 128, 150, 384, 330
d.rounded_rectangle([wx0, wy0, wx1, wy1], radius=30, fill=(255, 255, 255, 255))
d.rounded_rectangle([wx0, wy0, wx1, wy0 + 56], radius=30, fill=(28, 66, 133, 255))
d.rectangle([wx0, wy0 + 28, wx1, wy0 + 56], fill=(28, 66, 133, 255))
# 钱包扣袋
d.rounded_rectangle([wx1 - 96, wy0 + 96, wx1 - 24, wy0 + 168], radius=16,
                    fill=(28, 66, 133, 255))
d.ellipse([wx1 - 72, wy0 + 118, wx1 - 48, wy0 + 142], fill=(255, 255, 255, 255))

# 金色 Σ（总和）徽标
bx, by, br = 396, 128, 62
d.ellipse([bx - br, by - br, bx + br, by + br], fill=(243, 183, 44, 255))
d.ellipse([bx - br, by - br, bx + br, by + br], outline=(255, 255, 255, 255), width=6)
sw = d.textlength("Σ", font=f_sym)
d.text((bx - sw / 2, by - 52), "Σ", font=f_sym, fill=(60, 40, 5, 255))

# 底部标题
tw = d.textlength("钱包资产查询", font=f_txt)
d.text((SIZE / 2 - tw / 2, 428), "钱包资产查询", font=f_txt, fill=(255, 255, 255, 255))

img.save(OUT)
print(f"OK {OUT} written")
