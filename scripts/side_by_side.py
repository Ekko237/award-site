#!/usr/bin/env python3
"""把改动前后的截图并排拼成一张图，给用户把关用。

用法：
  python3 side_by_side.py before.png after.png --out compare.png [--labels 改动前,改动后] [--height 1600]
  多组：python3 side_by_side.py a1.png a2.png b1.png b2.png --out compare.png   （每两张一行）

每张图按同一宽度缩放，顶部标上标签；太长的整页图按 --height 截掉下面的部分，只看首屏和关键区域。
"""
import argparse
from PIL import Image, ImageDraw, ImageFont

def font(size):
    for f in ['/System/Library/Fonts/PingFang.ttc', '/System/Library/Fonts/STHeiti Medium.ttc',
              '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']:
        try: return ImageFont.truetype(f, size)
        except Exception: pass
    return ImageFont.load_default()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('images', nargs='+')
    ap.add_argument('--out', default='compare.png')
    ap.add_argument('--labels', default='改动前,改动后')
    ap.add_argument('--width', type=int, default=900, help='每张缩放到的宽度')
    ap.add_argument('--height', type=int, default=1600, help='每张最多保留的高度')
    a = ap.parse_args()
    if len(a.images) % 2: ap.error('图片要成对给：前、后、前、后……')
    labels = a.labels.split(',')
    f, gap, top = font(28), 24, 56
    rows = []
    for i in range(0, len(a.images), 2):
        pair = []
        for path in a.images[i:i + 2]:
            im = Image.open(path).convert('RGB')
            im = im.resize((a.width, round(im.height * a.width / im.width)))
            pair.append(im.crop((0, 0, a.width, min(im.height, a.height))))
        rows.append(pair)
    H = sum(top + max(x.height for x in r) + gap for r in rows)
    W = a.width * 2 + gap * 3
    canvas = Image.new('RGB', (W, H), (246, 245, 242))
    d = ImageDraw.Draw(canvas)
    y = 0
    for r in rows:
        for j, im in enumerate(r):
            x = gap + j * (a.width + gap)
            d.text((x, y + 14), labels[j % len(labels)], fill=(24, 24, 27), font=f)
            canvas.paste(im, (x, y + top))
        y += top + max(x.height for x in r) + gap
    canvas.save(a.out)
    print('saved', a.out, canvas.size)

if __name__ == '__main__':
    main()
