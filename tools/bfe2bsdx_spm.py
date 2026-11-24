#!/usr/bin/env python3
"""bfe2bsdx_spm.py - BALDR FORCE EXE mech sprite (SPR + GR2 sheets) -> BALDR SKY DiveX spm (NeXAS_DX JSON) + PNGs.

Usage: bfe2bsdx_spm.py <tooru.spr.json> <png_dir> <named_waz.json> <out_dir> [--name tooru]
  <tooru.spr.json>  output of tools/bfe_spr.py (work/bfe_spr/tooru.json)
  <png_dir>         sheets decoded by tools/bfe_gr2.py (work/bfe_png/tooruNNN.png, RGBA, index 255 -> alpha 0)
  <named_waz.json>  tools/bfe_waz.py named JSON of the mech (work/bfe_waz/TOORU_named.json): used only to know which
                    SPR hit slots each animation really activates as attack areas
  out_dir/<name>.spm.json + out_dir/png/<name>_NNN_KKKK.png ; then PortTool j2b -> <name>.spm (done by the build)

Conversion rules (notes/09_tooru_port.md §2):
  * page i = SPR frame i (8 per pattern: dir 0..7). Dirs 5..7 are EMPTY pages (BSDX mirrors 1..3 itself when
    animReverseDirection=1), like kou.spm - EXCEPT the frames of the side-dash anims 8-13/20-25 whose
    animReverseDirection is 0: there BSDX reads pages 5..7 as they are, so they are written (2026-10-27 fix).
  * part fields are re-attributed by true_layout() (frame flip / per-part flags, exe-verified 2026-10-27).
  * part -> chip (dst rect relative to the mech origin is kept 1:1; BFE and BSDX use the same pixel scale).
    SPR parts with mirror=1 inside dirs 0..4 (10 parts) get a pre-flipped copy in an extra atlas PNG.
    drawAttr (exe-verified 2026-10-24, blend_of): 0x8/0x400/0x800 add 100/50/25 %, 0x10/0x1000/0x2000 subtract, 0x4 half;
    bits 0/1 = H/V flip. Flipped and additive/subtractive parts go to a separate atlas (additive baked into alpha).
  * sheets larger than 1024 px are sliced into several PNGs at rows no part crosses (BSDX/BHE sheets are <= 1024).
  * hit slots (SPR 32 fixed slots -> BSDX hitFlag bits):
      SPR 0  (body box, stand frame)        -> bit 13 {unk0 2, unk2 72}  (= kou.spm page 0 layout)
      SPR 14/15 (4x4 hand/muzzle points)    -> bits 18/19
      SPR attack slots activated by some WAZ sprite event of an animation using the frame
                                            -> bits 0..n in slot order, unk0 = height class 1 下段 / 2 中段 / 3 上段
      SPR 6/5 (thin lines) when not activated as attack -> bits 14/15
      others (SPR 9 down box, 13, leftovers)  dropped
  * anims: 0..47 = BSDX standard basic motions (names/rotate flags as kou.spm) built from the BFE slots of BASIC;
    48..59 empty; 60+s = SPR anim slot s (all 512 slots up to the last used one). waitFrame = (BFE wait+1) x2 (a pattern
    shows wait+1 ticks: exe 0x413244 sets the counter to wait+1; BFE logic
    runs at 30 fps: frame interval table 0x4e0634 = {66,50,33,16} ms, default index 2; BSDX runs at 60 fps).
"""
import json, os, sys, collections, argparse
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')    # この作業ツリーの根（tools/ の 1 つ上）
from PIL import Image

MAXSHEET = 1024
# SKILL_BASE (mech anim = SKILL_BASE + BFE SPR slot) and BASIC (DiveX basic anims 0..47 <- BFE SPR slots) are BFE-wide
# conventions shared with bfe2bsdx_waz / the build: bfe2bsdx_common (docs/porting/09_porting_another_mech.md §6 案 7, 2026-11-16)
from bfe2bsdx_common import SKILL_BASE, BASIC
# attack_rects bit (WAZ sprite event) -> SPR slot. OBSOLETE (2026-10-24): the data shows bit n = SPR rect slot n
# (e.g. ｱﾙﾃｨﾒｯﾄﾅｯｸﾙ mask 2 -> frames carry slot 1 ; ﾗﾝｽ 2nd hit mask 1<<19 -> slot 19 ; 118/160 events have every
# enabled slot present vs 72/160 with this table; the rest only enable extra, absent slots). Kept for reference.
ATKBIT2SLOT = {0: 1, 1: 10, 2: 2, 3: 11, 4: 16, 5: 17, 6: 18, 7: 4, 8: 19, 9: 12, 10: 20, 11: 5, 12: 6, 13: 7, 14: 8}
HEIGHT = {1: 1, 10: 1, 2: 2, 11: 2, 16: 2, 17: 2, 18: 2, 4: 3, 19: 3, 12: 3, 20: 3, 3: 3, 5: 2, 6: 2, 7: 2, 8: 2}
def blend_of(a):
    """BFE part drawAttr -> (kind, intensity 0..1, flip bits).  [確定: BaldrForce.exe]
    The blit dispatcher 0x413460 tests the flag word: 0x8 add 100% (0x405b80: 16-bit saturating add), 0x400 add 50%
    (0x4062b0: src>>1), 0x800 add 25% (0x4069e0: src>>2), 0x10 / 0x1000 / 0x2000 subtract 100/50/25% (0x407110 /
    0x407820 / 0x407f50: saturating sub), 0x4 half transparent. Bits 0/1 are NOT intensities but the H/V flip bits:
    the caller 0x413d15 XORs them with the object's mirror (in the file, a blended part keeps its flips in drawAttr and
    has mirror 0). A sprite event's 描画属性 (0x443665 table 0,1,2,4,8,0x400,0x800,0x10,0x1000,0x2000,...) overrides
    the part blend for the whole object (handled in bfe2bsdx_waz as slot 7)."""
    flip = a & 3
    if a & 0x8:
        return ('add', 1.0, flip)
    if a & 0x400:
        return ('add', 0.5, flip)
    if a & 0x800:
        return ('add', 0.25, flip)
    if a & 0x10:
        return ('sub', 1.0, flip)
    if a & 0x1000:
        return ('sub', 0.5, flip)
    if a & 0x2000:
        return ('sub', 0.25, flip)
    if a & 0x4:
        return ('half', 0.5, flip)
    return (None, 1.0, flip)


def true_layout(spr):
    """Re-attribute the SPR fields to the layout the exe really uses [確定: BaldrForce.exe, 2026-10-27].
    Both SPR loaders (0x412822 / 0x412ab2) copy a 10-byte frame header (memory frame +0 u16 partCount, +8 u16 FRAME
    FLIP), then partCount x 40 raw bytes, then the 512-byte rect table. The memory part (draw loop 0x413c30) is
    {+0 u16 image, +2 u16 unk(0x12), +4 dst[4], +0x14 src[4], +0x24 u16 flags (blend | flip bits 0/1)}.
    tools/bfe_spr.py / bfe2bsdx_effspr.py read a 6-byte header and put drawAttr/mirror at the START of each part, i.e.
    4 bytes early, so their fields belong elsewhere:
      frame flip        = parts[0].mirror           (data: parts[0].drawAttr is always 0 = header padding)
      part k flags      = parts[k+1].drawAttr, last part = frame 'attr' low 16 bits ('attr' high 16 / parts[k>0].mirror
                          are always 0 = high half of the u32 flags)
    The draw loop: frame flip ^ object flip -> bit0: x = -dst.right (dst mirrored about the origin), bit1: y likewise
    (0x413cf7..0x413d12); the image flip of a part = (frame flip ^ part flags ^ object flip) & 3 (0x413d32..0x413d43);
    the blend comes from part flags (0x413460 dispatch). Hit rects are stored already mirrored (no runtime flip).
    Adds f['fflip'] and pt['flags']; idempotent."""
    for f in spr['frames']:
        if '_tl' in f:
            continue
        ps = f['parts']
        f['fflip'] = (ps[0]['mirror'] & 3) if ps else 0
        for k, pt in enumerate(ps):
            pt['flags'] = ps[k + 1]['drawAttr'] if k + 1 < len(ps) else (f['attr'] & 0xFFFF)
        f['_tl'] = True
    return spr


def part_flip(pt, f):
    """effective image flip bits of a part (1 = H, 2 = V): frame flip xor part flags bits 0/1 (exe 0x413d32)"""
    return (f['fflip'] ^ pt['flags']) & 3


def part_dst(pt, f):
    """dst rect of a part after the frame flip (exe 0x413cf7: bit0 -> [-r, t, -l, b], bit1 -> [l, -b, r, -t])"""
    l, t, r, b = pt['dst']
    if f['fflip'] & 1:
        l, r = -r, -l
    if f['fflip'] & 2:
        t, b = -b, -t
    return [l, t, r, b]


def draw_of(a, baked=True):
    """part drawAttr -> BSDX chip (drawOption, value). Additive / subtractive parts are BAKED into their own atlas
    piece (bake_piece): alpha = max(r,g,b) x intensity, so they look right whether BSDX draws chip option 256 additively
    (SRCALPHA/ONE -> exactly the BFE sum) or as plain alpha (in-game 2026-10-24 the 0x400 lattice of the block barrier
    showed black lines, so chip-level 256 alone is not reliable). Value is then 256 (the intensity is in the alpha)."""
    kind, k, _ = blend_of(a)
    if kind == 'add':
        return (256, 256 if baked else int(256 * k))
    if kind == 'half':
        return (128, 128)
    return (0, 256)     # 'sub' is baked as a darkening alpha layer drawn normally


def bake_piece(p, kind, k):
    """RGBA piece of a BFE additive / subtractive part -> straight-alpha image approximating the blend:
    add: a = max(rgb)*k, rgb = rgb/max ; sub: a = max(rgb)*k, rgb = 0 (darkens what is behind)"""
    if kind not in ('add', 'sub'):
        return p
    out = []
    for (r, g, b, a) in p.getdata():
        m = max(r, g, b) if a else 0
        if m == 0:
            out.append((0, 0, 0, 0)); continue
        al = int(round(m * k))
        out.append(((r * 255 // m, g * 255 // m, b * 255 // m, al) if kind == 'add' else (0, 0, 0, al)))
    q = p.copy(); q.putdata(out)
    return q


def clear_rgb(im, black_key=False):
    """transparent pixels (palette index 255) -> RGB 0, so additive parts do not add the key colour.
    black_key: also make every pixel whose RGB565 value is 0 (r<8, g<4, b<8) transparent - BFE blits sprites with
    DDBLT_KEYSRC (0x403ab0) and the colour key of all sprite surfaces is 0 (global 0x533eb4 = 0, passed to
    SetColorKey 0x4035d0 at 0x412413) [確定]; Effect sheets rely on it (near-black backgrounds, e.g. effect_02 index 0
    = (1,1,1))."""
    data = [(0, 0, 0, 0) if a == 0 or (black_key and r < 8 and g < 4 and b < 8) else (r, g, b, a) for (r, g, b, a) in im.getdata()]
    im.putdata(data)
    return im


def slice_sheet(img, rects):
    """cut rows (y) so that no src rect crosses a cut and every slice <= MAXSHEET high"""
    w, h = img.size
    if h <= MAXSHEET and w <= MAXSHEET:
        return [(0, h)]
    assert w <= MAXSHEET, w
    cuts, y0 = [], 0
    while h - y0 > MAXSHEET:
        y = y0 + MAXSHEET
        while y > y0 and any(t < y < b for (l, t, r, b) in rects):
            y -= 1
        assert y > y0, 'cannot slice'
        cuts.append((y0, y)); y0 = y
    cuts.append((y0, h))
    return cuts


def convert(spr, pngdir, wazj, outdir, name):
    rep = collections.Counter()
    true_layout(spr)
    F, A = spr['frames'], spr['anims']
    os.makedirs(outdir + '/png', exist_ok=True)
    kou = json.load(open(_ROOT + '/work/nexas_rt/json/spm/kou.spm.json', encoding='utf-8'))['animData']
    # Frames whose dirs 5..7 must be real pages: anims with animReverseDirection 0 are NOT mirrored by BSDX (it reads
    # pages base+5..7 as they are). In kou.spm these are exactly the side dashes 8-13 / 20-25 (ground/air, right/left)
    # and their dirs 5..7 are filled (= flipped other-side dash, e.g. 右ダッシュ2 dir 5 = 左ダッシュ2 dir 3 flipped);
    # BFE stores the same thing in its own dirs 5..7 (slot 15 dir 5 = slot 18 dir 3 flipped). 2026-10-27 fix of the
    # "mech disappears while dashing" bug (tooru wrote these pages empty).
    full8 = set()
    for i, slots in BASIC.items():
        if kou[i]['animReverseDirection'] == 0:
            for sl in slots:
                for p in A[sl]:
                    full8.update(p['frame'] + d for d in (5, 6, 7))
    emit = lambda fi: fi % 8 < 5 or fi in full8
    # ---------- which attack slots each anim activates (union over all sprite events of all skills)
    act = collections.defaultdict(set)
    for s in wazj:
        for ph in s['phases']:
            for e in ph['events']:
                if e['anim'] >= 0 and e['attack_rects']:
                    for b in range(32):
                        if e['attack_rects'] >> b & 1:
                            act[e['anim']].add(b)     # attack bit n = SPR rect slot n (2026-10-24, see ATKBIT2SLOT)
    frame_act = collections.defaultdict(set)
    frame_used_by_basic_only = collections.defaultdict(lambda: True)
    for a, pats in enumerate(A):
        for p in pats:
            for d in range(8):
                frame_act[p['frame'] + d] |= act.get(a, set())
                if a >= 51:
                    frame_used_by_basic_only[p['frame'] + d] = False
    # ---------- sheets -> PNG slices
    rects_by_img = collections.defaultdict(list)
    for f in F:
        for pt in f['parts']:
            rects_by_img[pt['image']].append(tuple(pt['src']))
    images, slices = [], {}   # slices[img] = [(y0,y1,newImageNo)] for small sheets, or ('pack', {src:(img,newsrc)})
    for i, nm in enumerate(spr['images']):
        im = clear_rgb(Image.open('%s/%s.png' % (pngdir, nm)).convert('RGBA'))
        if im.size[0] <= MAXSHEET and im.size[1] <= MAXSHEET:
            fn = '%s_%03d_%04d.png' % (name, i, 1)
            im.save(outdir + '/png/' + fn, optimize=True)
            slices[i] = [(0, im.size[1], len(images))]; images.append(fn)
            continue
        # too large for a texture of the size BSDX/BHE use (<= 1024): shelf-pack the used part rects into new sheets
        uniq = sorted(set(rects_by_img[i]), key=lambda q: -(q[3] - q[1]))
        placed, sheets, cur = {}, [], None
        for q in uniq:
            w, h = q[2] - q[0], q[3] - q[1]
            if cur is None or cur['x'] + w > MAXSHEET:
                if cur is not None:
                    cur['y'] += cur['rowh']; cur['x'] = 0; cur['rowh'] = 0
                if cur is None or cur['y'] + h > MAXSHEET:
                    cur = {'x': 0, 'y': 0, 'rowh': 0, 'items': []}; sheets.append(cur)
            placed[q] = (len(sheets) - 1, [cur['x'], cur['y'], cur['x'] + w, cur['y'] + h])
            cur['items'].append((q, cur['x'], cur['y'])); cur['x'] += w; cur['rowh'] = max(cur['rowh'], h)
        base = len(images)
        for k, sh in enumerate(sheets):
            H = max(y + q[3] - q[1] for q, x, y in sh['items']); W = max(x + q[2] - q[0] for q, x, y in sh['items'])
            out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            for q, x, y in sh['items']:
                out.paste(im.crop(q), (x, y))
            fn = '%s_%03d_%04d.png' % (name, i, k + 1)
            out.save(outdir + '/png/' + fn, optimize=True); images.append(fn)
        slices[i] = ('pack', {q: (base + k, r) for q, (k, r) in placed.items()})
        rep['sheet %s %dx%d repacked into %d sheets <= %d' % (nm, im.size[0], im.size[1], len(sheets), MAXSHEET)] += 1
    # special parts atlas: flipped (mirror field / drawAttr bits 0-1) and additive/subtractive parts (baked alpha)
    keys = collections.OrderedDict()
    for fi, f in enumerate(F):
        if emit(fi):
            for pt in f['parts']:
                kind, k, _ = blend_of(pt['flags'])
                fl = part_flip(pt, f)
                if fl or kind in ('add', 'sub'):
                    keys.setdefault((pt['image'], tuple(pt['src']), fl, kind if kind in ('add', 'sub') else None,
                                     k if kind in ('add', 'sub') else 1.0), []).append(pt)
    flipmap = {}
    if keys:  # noqa
        order = sorted(keys, key=lambda q: (-(q[1][3] - q[1][1]), q[0], q[1], q[2], str(q[3]), q[4]))
        sheets_, cur = [], None
        place = {}
        for q in order:
            l, t, r, b = q[1]; w, h = r - l, b - t
            if cur is None or cur['x'] + w > MAXSHEET:
                if cur is not None:
                    cur['y'] += cur['rowh']; cur['x'] = 0; cur['rowh'] = 0
                if cur is None or cur['y'] + h > MAXSHEET:
                    cur = {'x': 0, 'y': 0, 'rowh': 0, 'items': []}; sheets_.append(cur)
            place[q] = (len(sheets_) - 1, cur['x'], cur['y']); cur['items'].append(q)
            cur['x'] += w; cur['rowh'] = max(cur['rowh'], h)
        srcim = {}
        base = len(images)
        for n, sh in enumerate(sheets_):
            W = max(place[q][1] + q[1][2] - q[1][0] for q in sh['items']); H = max(place[q][2] + q[1][3] - q[1][1] for q in sh['items'])
            atlas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            for q in sh['items']:
                if q[0] not in srcim:
                    srcim[q[0]] = clear_rgb(Image.open('%s/%s.png' % (pngdir, spr['images'][q[0]])).convert('RGBA'))
                p = srcim[q[0]].crop(q[1])
                if q[2] & 1:
                    p = p.transpose(Image.FLIP_LEFT_RIGHT)
                if q[2] & 2:
                    p = p.transpose(Image.FLIP_TOP_BOTTOM)
                p = bake_piece(p, q[3], q[4])
                _, ax, ay = place[q]
                atlas.paste(p, (ax, ay))
                l, t, r, b = q[1]
                for pt in keys[q]:
                    flipmap[id(pt)] = (base + n, [ax, ay, ax + r - l, ay + b - t])
            fn = '%s_%03d_%04d.png' % (name, len(spr['images']), n + 1)
            atlas.save(outdir + '/png/' + fn, optimize=True); images.append(fn)
        rep['special parts (flip / baked additive-subtractive) -> %d atlas sheets, %d pieces' % (len(sheets_), len(keys))] += 1

    def chip(pt, f):
        if id(pt) in flipmap:
            img, src = flipmap[id(pt)]
        else:
            l, t, r, b = pt['src']
            if slices[pt['image']][0] == 'pack':
                img, src = slices[pt['image']][1][tuple(pt['src'])]
                src = list(src)
            else:
              for y0, y1, ni in slices[pt['image']]:
                if y0 <= t and b <= y1:
                    img, src = ni, [l, t - y0, r, b - y0]; break
              else:
                raise ValueError('part crosses slice')
        dst = part_dst(pt, f)
        dl, dt, dr, db = dst
        assert dr - dl == src[2] - src[0] and db - dt == src[3] - src[1]
        dopt, dval = draw_of(pt['flags'])
        if pt['flags']:
            rep['part flags %d -> drawOption %d/%d' % (pt['flags'], dopt, dval)] += 1
        R = lambda q: {'left': q[0], 'top': q[1], 'right': q[2], 'bottom': q[3]}
        return {'imageNo': img, 'dstRect': R(dst), 'chipWidth': dr - dl, 'chipHeight': db - dt, 'srcRect': R(src),
                'drawOption': dopt, 'drawOptionValue': dval, 'option': 0, 'unk5': 0}

    pages = []
    for fi, f in enumerate(F):
        pg = {'numChipData': 0, 'pageWidth': 0, 'pageHeight': 0, 'pageRect': {'left': 0, 'top': 0, 'right': 0, 'bottom': 0},
              'pageOption': 0, 'rotateCenterX': 0, 'rotateCenterY': 0, 'hitFlag': 0, 'hitRects': [], 'chipData': [], 'unk3': 0}
        if emit(fi) and f['parts']:
            ch = [chip(pt, f) for pt in f['parts']]
            l = min(c['dstRect']['left'] for c in ch); t = min(c['dstRect']['top'] for c in ch)
            r = max(c['dstRect']['right'] for c in ch); b = max(c['dstRect']['bottom'] for c in ch)
            pg.update(numChipData=len(ch), chipData=ch, pageWidth=r - l, pageHeight=b - t,
                      pageRect={'left': l, 'top': t, 'right': r, 'bottom': b})
        if emit(fi):
            bits = {}
            rects = {int(k): v for k, v in f['rects'].items()}
            atk = sorted(s for s in rects if s in frame_act[fi] and s not in (0, 14, 15))
            for n, s in enumerate(atk[:10]):
                bits[n if n < 9 else 10] = (HEIGHT.get(s, 2), rects[s], 0, 0)
            if len(atk) > 10:
                rep['frame with >10 attack rects (dropped rest)'] += 1
            if 0 in rects and fi == 0:
                bits[13] = (2, rects[0], 0, 72)
            for s, b in ((6, 14), (5, 15)):
                if s in rects and s not in atk:
                    bits[b] = (2, rects[s], 0, 0)
            for s, b in ((14, 18), (15, 19)):
                if s in rects:
                    bits[b] = (2, rects[s], 0, 0)
            for s in rects:
                if s not in atk and s not in (5, 6, 14, 15) and not (s == 0 and fi == 0):
                    rep['dropped SPR rect slot %d' % s] += 1
            for b in sorted(bits):
                u0, rc, u1, u2 = bits[b]
                pg['hitFlag'] |= 1 << b
                pg['hitRects'].append({'unk0': u0, 'hitRect': {'left': rc[0], 'top': rc[1], 'right': rc[2], 'bottom': rc[3]},
                                       'unk1': u1, 'unk2': u2})
        pages.append(pg)
    rep['dirs 5-7 written for %d frames of the non-mirrored (animReverseDirection 0) side-dash anims' % len(full8)] += 1
    # ---------- anims
    anims = []

    def pats_of(slots):
        out = []
        for s in slots:
            for p in A[s]:
                out.append({'pageNo': [p['frame']], 'waitFrame': (p['wait'] + 1) * 2})
        return out
    for i in range(SKILL_BASE):
        if i in BASIC:
            pt = pats_of(BASIC[i]); k = kou[i]
            anims.append({'animName': k['animName'], 'numPat': len(pt), 'animRotateDirection': k['animRotateDirection'],
                          'animReverseDirection': k['animReverseDirection'], 'patData': pt})
        else:
            anims.append({'animName': '\r', 'numPat': 0, 'animRotateDirection': 0, 'animReverseDirection': 0, 'patData': []})
    last = max(s for s, p in enumerate(A) if p)
    for s in range(last + 1):
        pt = pats_of([s]) if A[s] else []
        anims.append({'animName': ('BFE%03d\r' % s) if pt else '\r', 'numPat': len(pt), 'animRotateDirection': 3 if pt else 0,
                      'animReverseDirection': 1 if pt else 0, 'patData': pt})
    spm = {'spmVersion': 'SPM VER-2.00', 'numPageData': len(pages), 'pageData': pages, 'numImageData': len(images),
           'imageData': [{'imageName': n} for n in images], 'patPageNum': 1, 'numAnimData': len(anims), 'animData': anims,
           'extensionName': 'spm'}
    json.dump(spm, open('%s/%s.spm.json' % (outdir, name), 'w', encoding='utf-8'), ensure_ascii=False)
    return spm, rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('spr'); ap.add_argument('pngdir'); ap.add_argument('waz'); ap.add_argument('out')
    ap.add_argument('--name', default='tooru')
    a = ap.parse_args()
    spm, rep = convert(json.load(open(a.spr)), a.pngdir, json.load(open(a.waz, encoding='utf-8')), a.out, a.name)
    print('pages %d images %d anims %d' % (spm['numPageData'], spm['numImageData'], spm['numAnimData']))
    for k, v in sorted(rep.items()):
        print('  %s x%d' % (k, v))


if __name__ == '__main__':
    main()
