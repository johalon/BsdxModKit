#!/usr/bin/env python3
"""bfe2bsdx_effmap.py - BFE effect number (calc_effect.effect_no: hit effects, 常時/着地/発射位置 effects) -> Effect.spr anim.

Found in BaldrForce.exe (unprotected 2003 build): the effect spawner 0x426e00 (count from 出現規模 via 0x44eca0) calls
0x426780(type) which creates an Effect.spr sprite object and dispatches through the handler table 0x4d45ec[type]
(44 entries). Each handler sets the anim with 0x4131b0(sprite, anim, 0, 1) and may spawn more effects (0x426780).
This module extracts that table from the objdump listing (work/bfe_disc_exe/bf.asm) + exe bytes; result cached in
work/tooru_full/effmap.json:  {type: {"anims": [...], "spawns": [...], "handler": "0x..."}}
"""
import re, struct, json, os, sys
P = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')
ASM = P + '/work/bfe_disc_exe/bf.asm'
EXE = P + '/work/bfe_disc_exe/x/BaldrForce.exe'
OUT = P + '/work/tooru_full/effmap.json'
TABLE, N = 0x4d45ec, 44


def _pe():
    B = open(EXE, 'rb').read()
    e = struct.unpack_from('<I', B, 0x3c)[0]; ns = struct.unpack_from('<H', B, e + 6)[0]; oh = struct.unpack_from('<H', B, e + 20)[0]
    base = struct.unpack_from('<I', B, e + 24 + 28)[0]; secs = []
    for i in range(ns):
        vs, va, rs, raw = struct.unpack_from('<IIII', B, e + 24 + oh + 40 * i + 8)
        secs.append((va + base, max(vs, rs), raw))
    def u32(v):
        for va, sz, raw in secs:
            if va <= v < va + sz:
                return struct.unpack_from('<I', B, raw + v - va)[0]
    return u32


def build():
    u32 = _pe()
    lines = open(ASM).read().split('\n'); idx = {}
    for i, l in enumerate(lines):
        m = re.match(r'\s+([0-9a-f]+):', l)
        if m:
            idx[int(m.group(1), 16)] = i
    tab = [u32(TABLE + 4 * i) for i in range(N)]
    starts = sorted(set(tab)); out = {}
    for t, a in enumerate(tab):
        nxt = min([s for s in starts if s > a] + [a + 0x600])
        i = idx[a]; pushes = []; anims = []; spawns = []
        while i < len(lines):
            l = lines[i]; m = re.match(r'\s+([0-9a-f]+):', l)
            if m and int(m.group(1), 16) >= nxt:
                break
            mm = re.search(r'push\s+(0x[0-9a-f]+|\d+)$', l.strip())
            if mm:
                pushes.append(int(mm.group(1), 0))
            elif 'push' in l:
                pushes.append(None)
            mc = re.search(r'call\s+0x([0-9a-f]+)', l)
            if mc:
                tg = mc.group(1)
                if tg == '4131b0' and len(pushes) >= 2 and pushes[-2] is not None:
                    anims.append(pushes[-2])          # args: (sprite, anim, 0, 1) pushed right-to-left
                elif tg == '426780':
                    k = [p for p in pushes if p is not None]
                    if k:
                        spawns.append(k[-1])
                pushes = []
            i += 1
        out[t] = {'handler': hex(a), 'anims': anims, 'spawns': spawns}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, 'w'), indent=0)
    return out


def load():
    if not os.path.exists(OUT):
        return {int(k): v for k, v in build().items()}
    return {int(k): v for k, v in json.load(open(OUT)).items()}


if __name__ == '__main__':
    for k, v in build().items():
        print(k, v)
