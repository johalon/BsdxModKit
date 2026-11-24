#!/usr/bin/env python3
"""bfe_spr.py - BALDR FORCE EXE .SPR (mech sprite/animation definition) parser.

Container: 'SPR' + u32 unpacked_size + GR2-style LZ stream (see bfe_gr2.lz_unpack).
Unpacked layout (little-endian, validated on tooru.spr and akira.spr: parses to EOF exactly):
  u16  imageCount
  char imageName[imageCount][]      NUL-terminated, no extension (e.g. "tooru001" -> tooru001.grp)
  u16  frameCount                   (always a multiple of 8: 8 facing directions per "pattern")
  frame[frameCount]:
      u32 partCount
      u16 unk (always 0)
      part[partCount] (40 bytes):
          u16 drawAttr (0 mostly; 1..3, 0x8, 0x400, 0x800 seen -> blend/layer flags?) [guess]
          u16 mirror   (0/1: horizontal flip; dirs 5..7 = mirrored 3..1)
          u16 imageNo  (index into imageName[] -> <name>.grp)
          u16 unk      (always 0x12 in tooru)
          i32 dst[4]  (l,t,r,b relative to mech origin = feet)
          i32 src[4]  (l,t,r,b on the GR2 sheet)
      u32 frameAttr  (0, 0x8, 0x400, 0x800, ... meaning unknown)
      i32 rect[32][4]   fixed 32 hit/marker slots (all-zero = unused)
  anim[512] (fixed slot count; slot index = engine action id):
      u16 patCount
      pat[patCount]: u16 baseFrame (multiple of 8; +dir 0..7), u16 wait, i32 unk(0)

Usage: bfe_spr.py <file.spr> [out.json]
"""
import json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bfe_gr2 import unspr  # noqa: E402

N_ANIM = 512


def parse_unpacked(d):
    n = struct.unpack_from('<H', d, 0)[0]
    p = 2
    images = []
    for _ in range(n):
        e = d.index(b'\0', p)
        images.append(d[p:e].decode('cp932'))
        p = e + 1
    nf = struct.unpack_from('<H', d, p)[0]
    p += 2
    frames = []
    for _ in range(nf):
        c, unk = struct.unpack_from('<IH', d, p)
        p += 6
        parts = []
        for _ in range(c):
            attr_, mir, img, fl = struct.unpack_from('<HHHH', d, p)
            dst = struct.unpack_from('<4i', d, p + 8)
            src = struct.unpack_from('<4i', d, p + 24)
            parts.append(dict(image=img, mirror=mir, drawAttr=attr_, unk=fl, dst=dst, src=src))
            p += 40
        attr = struct.unpack_from('<I', d, p)[0]
        rects = {}
        for s in range(32):
            r = struct.unpack_from('<4i', d, p + 4 + 16 * s)
            if any(r):
                rects[s] = r
        p += 516
        frames.append(dict(unk=unk, parts=parts, attr=attr, rects=rects))
    anims = []
    for _ in range(N_ANIM):
        c = struct.unpack_from('<H', d, p)[0]
        p += 2
        pats = [struct.unpack_from('<HHi', d, p + 8 * i) for i in range(c)]
        p += 8 * c
        anims.append([dict(frame=f, wait=w, unk=u) for f, w, u in pats])
    if p != len(d):
        raise ValueError('trailing bytes: %d' % (len(d) - p))
    return dict(images=images, frames=frames, anims=anims)


def main(a):
    if len(a) < 2:
        print(__doc__); return 1
    data, got, us = unspr(a[1])
    spr = parse_unpacked(data)
    used = sum(1 for x in spr['anims'] if x)
    print('%s: images=%d frames=%d (patterns=%d) anims used=%d/512' % (
        a[1], len(spr['images']), len(spr['frames']), len(spr['frames']) // 8, used))
    if len(a) > 2:
        json.dump(spr, open(a[2], 'w'), ensure_ascii=False)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
