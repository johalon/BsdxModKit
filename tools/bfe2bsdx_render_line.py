#!/usr/bin/env python3
"""bfe2bsdx_render_line.py - visual check of a converted line chain (Laser.waz ライン親/子/先端, bfe2bsdx_line): draws the
root / parent sprite at the origin, the ライン子 segments chained link point to link point (spm hitFlag bit 5, scaled by
the slot 2/3 zoom like the BSDX child events), and the 先端 at the last link - the way OBJECTPOS 16/18 + LINKZ place them.
One cell per heading; with --wave A the segment angle is offset by A*sin(i*0.8) (illustration of うねうね only).

Usage: bfe2bsdx_render_line.py <out.png> <Laser.waz.json> <parent skill> <spm.json> <png_dir> [--n N] [--wave A]
       [--angles 0,30,90] [--label TEXT]
"""
import json, math, sys, argparse
from PIL import Image, ImageDraw, ImageChops

ap = argparse.ArgumentParser()
ap.add_argument('out'); ap.add_argument('waz'); ap.add_argument('parent', type=int); ap.add_argument('spm'); ap.add_argument('png')
ap.add_argument('--n', type=int); ap.add_argument('--wave', type=float, default=0); ap.add_argument('--angles', default='0,35,90')
ap.add_argument('--label', default=''); ap.add_argument('--root', type=int)
a = ap.parse_args()
W = json.load(open(a.waz, encoding='utf-8'))['skillList']
S = json.load(open(a.spm, encoding='utf-8'))
LASER = 6
imgs = {}


def img(n):
    if n not in imgs:
        imgs[n] = Image.open(a.png + '/' + S['imageData'][n]['imageName']).convert('RGBA')
    return imgs[n]


def objs(sk, slot, turn=0):
    return [o for u in sk['phasesInfo'][turn]['skillUnitCollection'] if u['unitQuantity'] == slot for o in u['skillInfoObjectList']]


def target(o):
    for u in o.get('ceventEffectUnitList') or []:
        if u['unitSlotNum'] == 3:
            return u['data']['wazFileNo'], u['data']['wazSequenceNo']


def sub(o, k):
    for u in o.get('ceventEffectUnitList') or []:
        if u['unitSlotNum'] == k:
            return u['data']


def first_sprite(sk):
    sp = objs(sk, 0)
    return (sp[0]['actionGroupNumber'], sp[0]['actionNumber']) if sp else None


def zoom(sk, slot):
    z = objs(sk, slot)
    return z[0]['int5'] / 256.0 if z else 1.0


def page_image(anim, pat):
    pg = S['pageData'][S['animData'][anim]['patData'][pat]['pageNo'][0]]
    r = pg['pageRect']; w, h = r['right'] - r['left'], r['bottom'] - r['top']
    im = Image.new('RGBA', (max(1, w), max(1, h)), (0, 0, 0, 0))
    for ch in pg['chipData']:
        s = ch['srcRect']; t = ch['dstRect']
        im.alpha_composite(img(ch['imageNo']).crop((s['left'], s['top'], s['right'], s['bottom'])), (t['left'] - r['left'], t['top'] - r['top']))
    bits = [b for b in range(32) if pg['hitFlag'] >> b & 1]
    link = None
    for b, hr in zip(bits, pg['hitRects']):
        if b == 5:
            link = (hr['hitRect']['left'], hr['hitRect']['top'])
    return im, (-r['left'], -r['top']), link, pg


def paste(canvas, im, org, at, ang, sx=1.0, sy=1.0, add=False):
    """draw image whose origin pixel is org at canvas point at, scaled (sx, sy), rotated by ang degrees (0 = +y down)"""
    if sx != 1 or sy != 1:
        im = im.resize((max(1, round(im.width * sx)), max(1, round(im.height * sy))), Image.BILINEAR); org = (org[0] * sx, org[1] * sy)
    big = Image.new('RGBA', (int(2 * max(im.size) + 4 * max(abs(org[0]), abs(org[1])) + 8),) * 2, (0, 0, 0, 0))
    c = big.width // 2
    big.alpha_composite(im, (int(c - org[0]), int(c - org[1])))
    big = big.rotate(-ang, center=(c, c), resample=Image.BICUBIC)
    pos = (int(at[0] - c), int(at[1] - c))
    if add:
        reg = canvas.crop((pos[0], pos[1], pos[0] + big.width, pos[1] + big.height)).convert('RGB')
        rgb = Image.merge('RGB', big.split()[:3]); al = big.split()[3]
        rgb = Image.composite(rgb, Image.new('RGB', rgb.size), al)
        canvas.paste(ImageChops.add(reg, rgb), pos)
    else:
        layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0)); layer.paste(big, pos, big)
        canvas.alpha_composite(layer)


par = W[a.parent]
child = tip = None; nmax = 1; per = 1
for o in objs(par, 48):
    t = target(o)
    if t and t[0] == LASER:
        nm = W[t[1]]['skillNameJapanese']
        if 'ライン子' in nm and child is None:
            child = W[t[1]]; s5 = sub(o, 5); s4 = sub(o, 4)
            nmax = s5['int2'] if s5 else 1; per = s4['int2'] if s4 else 1
        elif '先端' in nm:
            tip = W[t[1]]
n = a.n or nmax
root = W[a.root] if a.root is not None else None
cs = first_sprite(child); cim, corg, clink, cpg = page_image(*cs)
zx, zy = zoom(child, 2), zoom(child, 3)
angles = [float(x) for x in a.angles.split(',')]
cells = []
def chain_points(ang0):
    pts, angs, p = [], [], (0.0, 0.0)
    for i in range(n):
        ang = ang0 + (a.wave * math.sin(i * 0.8) if a.wave else 0)
        pts.append(p); angs.append(ang)
        lx, ly = (clink if clink else (0, cim.height - corg[1]))
        lx, ly = lx * zx, ly * zy
        r = math.radians(ang)
        p = (p[0] + lx * math.cos(r) - ly * math.sin(r), p[1] + lx * math.sin(r) + ly * math.cos(r))
    return pts, angs, p


for ang0 in angles:
    pts, angs, end = chain_points(ang0)
    xs = [q[0] for q in pts + [end]]; ys = [q[1] for q in pts + [end]]
    M = 90
    cw, chh = int(max(xs) - min(xs) + 2 * M), int(max(ys) - min(ys) + 2 * M)
    cv = Image.new('RGBA', (max(cw, 300), max(chh, 200)), (40, 40, 52, 255)); dr = ImageDraw.Draw(cv)
    off = (M - min(xs), M - min(ys))
    P = lambda q: (q[0] + off[0], q[1] + off[1])
    origin = P((0, 0))
    for o in (root, par):
        if o is not None and first_sprite(o):
            ri, ro, _, _ = page_image(*first_sprite(o)); paste(cv, ri, ro, origin, 0)
    for q, ang in zip(pts, angs):
        paste(cv, cim, corg, P(q), ang, zx, zy)
    if tip is not None and first_sprite(tip):
        import collections
        cnt = collections.Counter((o['actionGroupNumber'], o['actionNumber']) for ph in range(len(tip['phasesInfo'])) for o in objs(tip, 0, ph))
        ti, to, _, _ = page_image(*cnt.most_common(1)[0][0]); paste(cv, ti, to, P(end), ang0)
    dr.ellipse((origin[0] - 3, origin[1] - 3, origin[0] + 3, origin[1] + 3), outline=(255, 255, 0))
    dr.text((4, 4), '%s %d segs (+%d/F) link=%s zoom=%.2f/%.2f ang %d' % (a.label, n, per, clink, zx, zy, ang0), fill=(255, 255, 255))
    cells.append(cv)
out = Image.new('RGBA', (sum(c.width for c in cells), max(c.height for c in cells)), (20, 20, 26, 255))
x = 0
for c in cells:
    out.paste(c, (x, 0)); x += c.width
if out.width > 2400:
    out = out.resize((2400, int(out.height * 2400 / out.width)))
out.save(a.out); print(a.out, out.size)
