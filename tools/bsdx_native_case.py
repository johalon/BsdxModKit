#!/usr/bin/env python3
"""Print exe handler snippet for a BSDX script native id (game natives 410..702 via switch @0x449d87).
usage: bsdx_native_case.py <exe.asm from objdump -d -M intel --no-show-raw-insn> <id> [nlines]
"""
import sys, struct, bisect
EXE = '/path/to/GIGA/BALDRSKY_DIVEX/BaldrSky.exe'
b = open(EXE, 'rb').read()
def case_addr(nid):
    if 410 <= nid <= 410 + 0x124:
        return struct.unpack_from('<I', b, 0x44bea4 - 0x401000 + 0x400 + 4 * (nid - 410))[0]
    if 0 <= nid <= 0x2c1:
        return struct.unpack_from('<I', b, 0x7836f4 - 0x401000 + 0x400 + 4 * nid)[0]
asm, nid = sys.argv[1], int(sys.argv[2]); n = int(sys.argv[3]) if len(sys.argv) > 3 else 30
a = case_addr(nid); print('native %d -> case %#x' % (nid, a))
lines = open(asm).read().split('\n')
key = '  %x:' % a
for i, l in enumerate(lines):
    if l.startswith(key):
        print('\n'.join(lines[i:i + n])); break
