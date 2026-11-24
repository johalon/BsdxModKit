#!/usr/bin/env python3
"""bfe2bsdx_eft.py - BALDR FORCE EXE Bmp/Effect (Effect.spr + *.grp sheets) -> BALDR SKY DiveX effect spm
(NeXAS_DX JSON + PNG atlases), converting ONLY the anim slots that are actually used.

Usage (library): build_effect_spm(effspr, sheet_dir, anims, outdir, name) -> (spm_json, report Counter)
  effspr     tools/bfe2bsdx_effspr.parse(Effect.spr)
  sheet_dir  directory of the Effect sheets decoded to PNG (decode_sheets() does it from work/bfe_effect)
  anims      iterable of Effect.spr anim slots to convert (closure computed by the caller)

Rules (調査記録 09 §8):
  * spm anim index == BFE Effect.spr anim slot (so waz refs are the BFE numbers). Unused slots are empty anims.
  * one page per used BFE frame (effects have no 8-direction groups); patPageNum 1; animRotateDirection 7 (0 for the
    upright anims of upright_anims(): mines, the falling satellite beam, ground shockwaves, explosions) /
    animReverseDirection 0 like the vanilla effect spms (Tama.spm / Mark.spm): the engine rotates the sprite
    (BFE bullet sprites are drawn pointing up/down exactly like BSDX's, e.g. ﾎｰﾐﾝｸﾞﾐｻｲﾙ anim 147).
  * waitFrame = (BFE wait+1) x2 (a pattern shows wait+1 ticks; 30 -> 60 fps); single-pattern anims get 0 like vanilla.
  * frame flip / per-part flags as the exe reads them (bfe2bsdx_spm.true_layout, 2026-10-27: the parsers' drawAttr /
    mirror fields sit 4 bytes early). Frame flip mirrors every part's dst about the origin; image flip = frame flip xor
    part flags bits 0/1 (1 = H, 2 = V) -> pre-flipped copy in the atlas; part-flags blend
    (bfe2bsdx_spm.blend_of, exe-verified: 0x8/0x400/0x800 add 100/50/25 %, 0x10/0x1000/0x2000 subtract) baked into the
    piece's alpha; RGB565-zero pixels transparent (BFE colour key 0).
  * rect slots -> hitFlag bits as in vanilla Tama.spm: SPR 2 (hit box) -> bit 0, SPR 4 (the x=72..88 helper
    rect, same as vanilla bit 4 at x=64..72) -> bit 4, SPR 8 (= editor "slot 9", the 1-px link point at the far end of a
    laser / wire segment) -> bit 5 (Link.spm's 連結位置 point, OBJECTPOS2 LINK), SPR 15 (point) -> bit 14; SPR 5/6 dropped.
  * every used part rect is shelf-packed into atlases <= 1024x1024 named <name>_NNN_0001.png.
"""
import os, sys, collections
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')    # この作業ツリーの根（tools/ の 1 つ上）
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bfe2bsdx_spm import draw_of, clear_rgb, blend_of, part_flip, part_dst, bake_piece, true_layout
from bfe_gr2 import read_gr2, to_rgba

MAX = 1024
RECTBIT = {2: 0, 4: 4, 8: 5, 15: 14}
TAMA_NAMED = _ROOT + '/work/bfe_waz/Tama_named.json'


def upright_anims(tama):
    """Effect anims that must NOT be rotated by BSDX (animRotateDirection 0) [V 2026-10-27].
    BFE: an anim shown only in Tama phases with チップ向き processing type 0 and 移動方向 type 0 (the bullet never turns
    its chip nor steers) is drawn upright (user report: the 地雷 sprite does not follow the mech's facing in BFE).
    Vanilla BSDX encodes such sprites with animRotateDirection 0: Tama.spm 地雷 anims 11/29/30/89-92/176 and
    bomb.spm 48/49 「弾28（ＳＯＬ(青)」 = the 750-px falling satellite beam (same stacked-part layout as BFE anims 30-33,
    which we had at 7 -> the beam was rotated toward the object's (downward) direction and not visible).
    Rule: every use has chip type 0, and move type 0 in the majority of uses. Anims without Tama uses (spawned by the
    effect handlers) keep 7."""
    use = collections.defaultdict(collections.Counter)
    for t in tama:
        for ph in t['phases']:
            for e in ph['events']:
                if e['anim'] >= 0:
                    still = ph['speed']['init'][0] == 0 and ph['speed']['final'][0] == 0 and ph['move_dir']['type'] != 5
                    use[e['anim']][(ph['chip_dir']['type'], ph['move_dir']['type'], still)] += 1
    out = set()
    for a, c in use.items():
        tot = sum(c.values())
        if all(k[0] == 0 for k in c) and sum(v for k, v in c.items() if k[1] == 0) * 2 > tot:
            out.add(a)
        # R 2026-11-15 (user リバースフィールド.mp4 vs 原作 通常武装 3:02: the three ground rings lie flat in BFE, the port
        # showed them standing on edge): also an anim shown only on phases with チップ向き 0 (向き修正なし) that do not move
        # (速度 0, not a follow phase 移動方向 5) even when their 移動方向 type is not 0 (ﾘﾊﾞｰｽﾌｨｰﾙﾄﾞ ph1 type 2 at speed 0):
        # nothing in BFE turns that chip. BSDX had it at 7 and kept the direction of the 4-frame drop phase (anim 29).
        elif all(k[0] == 0 and (k[1] == 0 or k[2]) for k in c):
            out.add(a)
    return out


def decode_sheets(src_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for f in sorted(os.listdir(src_dir)):
        if f.lower().endswith('.grp'):
            out = '%s/%s.png' % (out_dir, f[:-4].lower())
            if not os.path.exists(out):
                g = read_gr2(src_dir + '/' + f)
                rows = to_rgba(g)
                Image.frombytes('RGBA', (g['w'], g['h']), b''.join(rows)).save(out)
    return out_dir


def build_effect_spm(spr, sheet_dir, anims, outdir, name, upright=None):
    rep = collections.Counter()
    os.makedirs(outdir + '/png', exist_ok=True)
    true_layout(spr)      # frame flip + per-part flags as the exe reads them (bfe2bsdx_spm.true_layout)
    A, F = spr['anims'], spr['frames']
    anims = sorted({a for a in anims if 0 <= a < 512 and A[a]})
    if upright is None:
        import json
        upright = upright_anims(json.load(open(TAMA_NAMED, encoding='utf-8'))) if os.path.exists(TAMA_NAMED) else set()
    frames = sorted({p['frame'] for a in anims for p in A[a]})
    # ---- unique (image, src, mirror) pieces -> atlas
    sheets = {}
    def sheet(i):
        if i not in sheets:
            sheets[i] = clear_rgb(Image.open('%s/%s.png' % (sheet_dir, spr['images'][i].lower())).convert('RGBA'), black_key=True)
        return sheets[i]
    def pkey(pt, fr):
        kind, k, _ = blend_of(pt['flags'])
        bk = kind if kind in ('add', 'sub') else None
        return (pt['image'], tuple(pt['src']), part_flip(pt, fr), bk, k if bk else 1.0)
    pieces = {}
    for f in frames:
        for pt in F[f]['parts']:
            pieces[pkey(pt, F[f])] = None
    order = sorted(pieces, key=lambda k: (-(k[1][3] - k[1][1]), k[0], k[1], k[2], str(k[3]), k[4]))
    atlases, cur = [], None
    for k in order:
        l, t, r, b = k[1]; w, h = r - l, b - t
        assert w <= MAX and h <= MAX
        if cur is None or cur['x'] + w > MAX:
            if cur is not None:
                cur['y'] += cur['rowh']; cur['x'] = 0; cur['rowh'] = 0
            if cur is None or cur['y'] + h > MAX:
                cur = {'x': 0, 'y': 0, 'rowh': 0, 'items': []}; atlases.append(cur)
        pieces[k] = (len(atlases) - 1, (cur['x'], cur['y'], cur['x'] + w, cur['y'] + h))
        cur['items'].append((k, cur['x'], cur['y'])); cur['x'] += w; cur['rowh'] = max(cur['rowh'], h)
    images = []
    for n, at in enumerate(atlases):
        W = max(x + k[1][2] - k[1][0] for k, x, y in at['items']); H = max(y + k[1][3] - k[1][1] for k, x, y in at['items'])
        im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        for k, x, y in at['items']:
            p = sheet(k[0]).crop(k[1])
            if k[2] & 1:
                p = p.transpose(Image.FLIP_LEFT_RIGHT)
            if k[2] & 2:
                p = p.transpose(Image.FLIP_TOP_BOTTOM)
            im.paste(bake_piece(p, k[3], k[4]), (x, y))
        fn = '%s_%03d_0001.png' % (name, n)
        im.save(outdir + '/png/' + fn, optimize=True); images.append(fn)
    rep['atlases %d (pieces %d, frames %d, anims %d)' % (len(images), len(pieces), len(frames), len(anims))] += 1
    R = lambda q: {'left': q[0], 'top': q[1], 'right': q[2], 'bottom': q[3]}
    pages, page_of = [], {}
    for f in frames:
        fr = F[f]; ch = []
        for pt in fr['parts']:
            ai, src = pieces[pkey(pt, fr)]
            dopt, dval = draw_of(pt['flags'])
            if pt['flags']:
                rep['part flags %d -> drawOption %d/%d' % (pt['flags'], dopt, dval)] += 1
            if fr['fflip']:
                rep['frame flip %d (dst mirrored about the origin)' % fr['fflip']] += 1
            d = part_dst(pt, fr)
            ch.append({'imageNo': ai, 'dstRect': R(d), 'chipWidth': d[2] - d[0], 'chipHeight': d[3] - d[1], 'srcRect': R(src),
                       'drawOption': dopt, 'drawOptionValue': dval, 'option': 0, 'unk5': 0})
        pg = {'numChipData': len(ch), 'pageWidth': 0, 'pageHeight': 0, 'pageRect': R((0, 0, 0, 0)), 'pageOption': 0,
              'rotateCenterX': 0, 'rotateCenterY': 0, 'hitFlag': 0, 'hitRects': [], 'chipData': ch, 'unk3': 0}
        if ch:
            l = min(c['dstRect']['left'] for c in ch); t = min(c['dstRect']['top'] for c in ch)
            r = max(c['dstRect']['right'] for c in ch); b = max(c['dstRect']['bottom'] for c in ch)
            pg.update(pageWidth=r - l, pageHeight=b - t, pageRect=R((l, t, r, b)))
        bits = {}
        for s, rc in fr['rects'].items():
            s = int(s)
            if s in RECTBIT:
                bits[RECTBIT[s]] = rc
            else:
                rep['dropped Effect rect slot %d' % s] += 1
        for bb in sorted(bits):
            pg['hitFlag'] |= 1 << bb
            pg['hitRects'].append({'unk0': 2, 'hitRect': R(bits[bb]), 'unk1': 0, 'unk2': 0})
        page_of[f] = len(pages); pages.append(pg)
    out_anims = []
    last = max(anims) if anims else 0
    for a in range(last + 1):
        if a in anims:
            pats = A[a]
            pt = [{'pageNo': [page_of[p['frame']]], 'waitFrame': ((p['wait'] + 1) * 2 if len(pats) > 1 else 0)} for p in pats]
            rot = 0 if a in upright else 7
            if not rot:
                rep['anim %d upright (animRotateDirection 0, BFE chip/move direction never processed)' % a] += 1
            out_anims.append({'animName': 'BFE_EFT%03d\r' % a, 'numPat': len(pt), 'animRotateDirection': rot, 'animReverseDirection': 0, 'patData': pt})
        else:
            out_anims.append({'animName': '\r', 'numPat': 0, 'animRotateDirection': 0, 'animReverseDirection': 0, 'patData': []})
    spm = {'spmVersion': 'SPM VER-2.00', 'numPageData': len(pages), 'pageData': pages, 'numImageData': len(images),
           'imageData': [{'imageName': n} for n in images], 'patPageNum': 1, 'numAnimData': len(out_anims), 'animData': out_anims,
           'extensionName': 'spm'}
    return spm, rep
