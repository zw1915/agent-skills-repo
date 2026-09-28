#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone avatar generator for existing expert-team packages.

Scans each team dir under the plugins dir, reads plugin.json, and (re)generates:
  avatars/team.png              -> team emblem (team zh name)
  avatars/<member-id>.png       -> member badge (initial + profession)
so every members[].avatar path physically exists (upload-validation rule).

Usage:
    python gen_avatars.py [--plugins DIR]
"""
import os, json, argparse

FONT_CANDIDATES = [
    'C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf',
    '/System/Library/Fonts/PingFang.ttc', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
]
COLORS = [(35,120,180),(247,147,26),(98,126,234),(20,160,140),(120,60,200),(230,90,90),
          (0,150,200),(150,120,40),(60,170,90),(190,80,160),(40,90,140),(210,130,30),
          (70,70,180),(0,130,120),(160,60,60),(100,110,20),(30,150,170),(130,80,180)]


def find_font():
    for f in FONT_CANDIDATES:
        if os.path.isfile(f):
            return f
    raise SystemExit("No CJK font found")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plugins', default=os.path.expanduser('~/.workbuddy/plugins/marketplaces/my-experts/plugins'))
    args = ap.parse_args()

    from PIL import Image, ImageDraw, ImageFont
    font_path = find_font()
    cache = {}

    def F(sz):
        if sz not in cache:
            cache[sz] = ImageFont.truetype(font_path, sz)
        return cache[sz]

    def grad(c1, c2, size=(512, 512)):
        img = Image.new('RGB', size); px = img.load(); w, h = size
        for y in range(h):
            t = y / (h - 1)
            r = int(c1[0] + (c2[0] - c1[0]) * t); g = int(c1[1] + (c2[1] - c1[1]) * t); b = int(c1[2] + (c2[2] - c1[2]) * t)
            for x in range(w):
                px[x, y] = (r, g, b)
        return img

    def wrap(s, n):
        return [s[i:i + n] for i in range(0, len(s), n)] or [s]

    total = 0
    for i, d in enumerate(sorted(os.listdir(args.plugins))):
        pj = os.path.join(args.plugins, d, '.codebuddy-plugin', 'plugin.json')
        if not os.path.isfile(pj):
            continue
        data = json.load(open(pj, encoding='utf-8'))
        color = COLORS[i % len(COLORS)]
        av = os.path.join(args.plugins, d, 'avatars')
        os.makedirs(av, exist_ok=True)
        # team emblem
        name = data.get('displayName', {}).get('zh', d).replace('团', '') or d
        img = grad(color, tuple(max(0, c - 50) for c in color)); dr = ImageDraw.Draw(img)
        lines = wrap(name, 5); sy = 256 - (len(lines) - 1) * 44
        for j, ln in enumerate(lines):
            dr.text((256, sy + j * 88), ln, font=F(76), fill=(255, 255, 255), anchor='mm')
        img.save(os.path.join(av, 'team.png'), 'PNG'); total += 1
        # members
        for m in data.get('members', []):
            mid = m.get('id'); nm = m.get('name', {}) or m.get('displayName', {})
            zh = nm.get('zh', '') or mid
            role = (m.get('profession', {}) or {}).get('zh', '')
            img = grad(color, tuple(max(0, c - 50) for c in color)); dr = ImageDraw.Draw(img)
            cx, cy, r = 256, 188, 118
            dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255))
            dr.text((cx, cy), zh[0], font=F(120), fill=color, anchor='mm')
            dr.text((256, 372), role[:9], font=F(34), fill=(255, 255, 255), anchor='mm')
            img.save(os.path.join(av, f'{mid}.png'), 'PNG'); total += 1
    print(f"Generated {total} avatars")


if __name__ == '__main__':
    main()
