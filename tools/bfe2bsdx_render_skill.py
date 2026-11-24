#!/usr/bin/env python3
"""bfe2bsdx_render_skill.py - visual check of a converted waz skill: one cell per sprite event (turn:frame), drawn from
the spm it references (spm -1 = the mech spm given with --self), with the hit window / spawn events of that moment
written under the cell. Spawned shared-waz skills can be rendered by passing their file/index the same way.

Usage: bfe2bsdx_render_skill.py <out.png> <waz.json> <skill> [--self spm.json:pngdir] [--spm G=spm.json:pngdir ...]
                                [--dir 2] [--max 30]
"""
import json, sys, argparse
from PIL import Image, ImageDraw, ImageChops

ap = argparse.ArgumentParser()
ap.add_argument('out'); ap.add_argument('waz'); ap.add_argument('skill', type=int)
ap.add_argument('--self'); ap.add_argument('--spm', action='append', default=[])
ap.add_argument('--dir', type=int, default=2); ap.add_argument('--max', type=int, default=30)
ap.add_argument('--cell', type=int, default=220)
a = ap.parse_args()
spms = {}
def load(spec):
    j, d = spec.split(':', 1); return (json.load(open(j, encoding='utf-8')), d)
if a.self:
    spms[-1] = load(a.self)
for s in a.spm:
    g, spec = s.split('=', 1); spms[int(g)] = load(spec)
imgs = {}
def img(d, name):
    k = d + '/' + name
    if k not in imgs:
        imgs[k] = Image.open(k).convert('RGBA')
    return imgs[k]
sk = json.load(open(a.waz, encoding='utf-8'))['skillList'][a.skill]
C = a.cell
cells = []
for t, ph in enumerate(sk['phasesInfo']):
    evs = {u['unitQuantity']: u['skillInfoObjectList'] for u in ph['skillUnitCollection']}
    for o in evs.get(0, [])[:a.max]:
        g = o['spmFileSequence']; s, pd = spms.get(g, (None, None))
        c = Image.new('RGBA', (C, C), (55, 55, 65, 255)); ox, oy = C // 2, int(C * 0.7)
        dr = ImageDraw.Draw(c)
        if s:
            an = s['animData'][o['actionGroupNumber']]; pt = an['patData'][o['actionNumber']]
            base = pt['pageNo'][0] + (a.dir if (g == -1 and an['animRotateDirection'] == 3) else 0)
            pg = s['pageData'][base]
            for ch in pg['chipData']:
                sr, ds = ch['srcRect'], ch['dstRect']
                part = img(pd, s['imageData'][ch['imageNo']]['imageName']).crop((sr['left'], sr['top'], sr['right'], sr['bottom']))
                x, y = ox + ds['left'], oy + ds['top']
                if ch['drawOption'] == 256:
                    bg = c.crop((x, y, x + part.size[0], y + part.size[1])).convert('RGB')
                    pm = ImageChops.multiply(Image.merge('RGB', part.split()[:3]), Image.merge('RGB', [part.split()[3]] * 3))
                    c.paste(ImageChops.add(bg, pm).convert('RGBA'), (x, y))   # additive = SRCALPHA/ONE
                else:
                    c.alpha_composite(part, (max(0, x), max(0, y)))
        f0 = o['startFrame']
        notes = []
        for h in evs.get(41, []):
            if h['startFrame'] <= f0 <= h['endFrame']:
                notes.append('HIT')
        for e in evs.get(48, []):
            if f0 <= e['startFrame'] <= o['endFrame']:
                for u in e['ceventEffectUnitList']:
                    if u['unitSlotNum'] == 3:
                        notes.append('>%d:%d' % (u['data']['wazFileNo'], u['data']['wazSequenceNo']))
        dr.text((2, 2), 't%d f%d-%d a%d/%d g%d' % (t, f0, o['endFrame'], o['actionGroupNumber'], o['actionNumber'], g), fill=(255, 255, 255))
        dr.text((2, C - 14), ' '.join(notes)[:40], fill=(255, 220, 80))
        dr.line((ox - 3, oy, ox + 3, oy), fill=(255, 255, 0))
        cells.append(c)
W = 6
out = Image.new('RGBA', (C * min(W, max(1, len(cells))), C * max(1, (len(cells) + W - 1) // W)), (0, 0, 0, 255))
for i, c in enumerate(cells):
    out.paste(c, (C * (i % W), C * (i // W)))
out.save(a.out); print(a.out, len(cells))
