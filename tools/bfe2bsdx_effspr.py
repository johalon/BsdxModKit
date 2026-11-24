#!/usr/bin/env python3
"""bfe2bsdx_effspr.py - parser for BALDR FORCE EXE Bmp/Effect/Effect.spr (the shared effect/bullet sprite).

Same container and part/rect layout as the mech SPR (tools/bfe_spr.py) except the frame header:
  u16 partCount ; u16 frameFlag (0, once 0xFF) ; u16 0        (mech SPR: u32 partCount ; u16 0)
Frames are NOT grouped by 8 directions (2899 frames); an anim pattern's baseFrame is a plain frame index.
512 anim slots (186 used). Validated: parses to EOF exactly.
Usage: bfe2bsdx_effspr.py <Effect.spr> [out.json]
"""
import json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bfe_gr2 import unspr


def parse(path):
    d = unspr(path)[0]
    n = struct.unpack_from('<H', d, 0)[0]; p = 2; images = []
    for _ in range(n):
        e = d.index(b'\0', p); images.append(d[p:e].decode('cp932')); p = e + 1
    nf = struct.unpack_from('<H', d, p)[0]; p += 2
    frames = []
    for _ in range(nf):
        c, flag, unk = struct.unpack_from('<HHH', d, p); p += 6
        parts = []
        for _ in range(c):
            attr_, mir, img, fl = struct.unpack_from('<HHHH', d, p)
            parts.append(dict(image=img, mirror=mir, drawAttr=attr_, unk=fl,
                              dst=struct.unpack_from('<4i', d, p + 8), src=struct.unpack_from('<4i', d, p + 24)))
            p += 40
        attr = struct.unpack_from('<I', d, p)[0]
        rects = {}
        for s in range(32):
            r = struct.unpack_from('<4i', d, p + 4 + 16 * s)
            if any(r):
                rects[s] = r
        p += 516
        frames.append(dict(flag=flag, parts=parts, attr=attr, rects=rects))
    anims = []
    for _ in range(512):
        c = struct.unpack_from('<H', d, p)[0]; p += 2
        anims.append([dict(frame=f, wait=w, unk=u) for f, w, u in (struct.unpack_from('<HHi', d, p + 8 * i) for i in range(c))])
        p += 8 * c
    if p != len(d):
        raise ValueError('trailing bytes %d' % (len(d) - p))
    return dict(images=images, frames=frames, anims=anims)


if __name__ == '__main__':
    s = parse(sys.argv[1])
    print('images %d frames %d anims used %d' % (len(s['images']), len(s['frames']), sum(1 for a in s['anims'] if a)))
    if len(sys.argv) > 2:
        json.dump(s, open(sys.argv[2], 'w'), ensure_ascii=False)
