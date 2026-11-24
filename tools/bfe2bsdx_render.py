#!/usr/bin/env python3
"""Render BSDX spm pages (NeXAS_DX JSON + png dir) to a PNG strip for visual checks, with hit rects overlaid
(ground-plane rects drawn at the origin: red = attack bits 0-10, green = body bit 13, blue = points/lines).
Usage: bfe2bsdx_render.py <spm.json> <png_dir> <out.png> <anim>:<pat>[:dirs] ...   (dirs default 01234)"""
import json, sys
from PIL import Image, ImageDraw
spm = json.load(open(sys.argv[1], encoding='utf-8')); pd = sys.argv[2]
imgs = {}
def img(n):
    if n not in imgs: imgs[n] = Image.open(pd + '/' + spm['imageData'][n]['imageName']).convert('RGBA')
    return imgs[n]
cells = []
for spec in sys.argv[4:]:
    p = spec.split(':'); a, k = int(p[0]), int(p[1]); dirs = p[2] if len(p) > 2 else '01234'
    base = spm['animData'][a]['patData'][k]['pageNo'][0]
    for d in dirs:
        pg = spm['pageData'][base + int(d)]
        c = Image.new('RGBA', (200, 200), (60, 60, 70, 255)); ox, oy = 100, 140
        for ch in pg['chipData']:
            s = ch['srcRect']; t = ch['dstRect']
            part = img(ch['imageNo']).crop((s['left'], s['top'], s['right'], s['bottom']))
            if ch['drawOption'] == 256:
                base_ = c.crop((ox + t['left'], oy + t['top'], ox + t['right'], oy + t['bottom']))
                from PIL import ImageChops
                # additive chip = SRCALPHA/ONE (vanilla NeXAS additive art is straight alpha: bright rgb at low alpha)
                pm = ImageChops.multiply(Image.merge('RGB', part.split()[:3]), Image.merge('RGB', [part.split()[3]] * 3))
                c.paste(ImageChops.add(base_.convert('RGB'), pm).convert('RGBA'), (ox + t['left'], oy + t['top']))
            else:
                c.alpha_composite(part, (ox + t['left'], oy + t['top']))
        dr = ImageDraw.Draw(c)
        bits = [b for b in range(32) if pg['hitFlag'] >> b & 1]
        for b, h in zip(bits, pg['hitRects']):
            r = h['hitRect']; col = (255, 0, 0) if b <= 10 else (0, 255, 0) if b == 13 else (80, 160, 255)
            dr.rectangle((ox + r['left'], oy + r['top'] // 2, ox + r['right'], oy + r['bottom'] // 2), outline=col)
        dr.line((ox - 3, oy, ox + 3, oy), fill=(255, 255, 0)); dr.text((2, 2), '%d:%d d%s' % (a, k, d), fill=(255, 255, 255))
        cells.append(c)
W = 5
out = Image.new('RGBA', (200 * min(W, len(cells)), 200 * ((len(cells) + W - 1) // W)))
for i, c in enumerate(cells): out.paste(c, (200 * (i % W), 200 * (i // W)))
out.save(sys.argv[3]); print(sys.argv[3], len(cells))
