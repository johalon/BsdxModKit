#!/usr/bin/env python3
"""BSDX .dat table codec (read/write) — byte-exact.
.dat: int32 colCount; int32 colType[colCount] (0/2 = int32, 1 = cp932 NUL-terminated string); rows until EOF.
CLI:
  bsdx_dat.py dump  <in.dat> <out.json>
  bsdx_dat.py build <in.json> <out.dat>
  bsdx_dat.py rt    <dat>...            (round-trip self test)
"""
import struct, sys, json

def read(b):
    n, = struct.unpack_from('<i', b, 0); p = 4
    types = list(struct.unpack_from('<%di' % n, b, p)); p += 4 * n
    rows = []
    while p < len(b):
        row = []
        for t in types:
            if t == 1:
                e = b.index(b'\0', p); row.append(b[p:e].decode('cp932')); p = e + 1
            elif t in (0, 2):
                row.append(struct.unpack_from('<i', b, p)[0]); p += 4
            else:
                raise ValueError('unsupported column type %d' % t)
        rows.append(row)
    return types, rows

def write(types, rows):
    out = bytearray(struct.pack('<i', len(types)) + struct.pack('<%di' % len(types), *types))
    for r in rows:
        assert len(r) == len(types), r
        for t, v in zip(types, r):
            out += (v.encode('cp932') + b'\0') if t == 1 else struct.pack('<i', int(v))
    return bytes(out)

if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'dump':
        t, r = read(open(sys.argv[2], 'rb').read())
        json.dump({'types': t, 'rows': r}, open(sys.argv[3], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    elif cmd == 'build':
        j = json.load(open(sys.argv[2], encoding='utf-8'))
        open(sys.argv[3], 'wb').write(write(j['types'], j['rows']))
    elif cmd == 'rt':
        bad = 0
        for f in sys.argv[2:]:
            b = open(f, 'rb').read()
            ok = write(*read(b)) == b; bad += not ok
            if not ok: print('MISMATCH', f)
        print('done, mismatches:', bad, '/', len(sys.argv) - 2)
