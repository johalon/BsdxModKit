#!/usr/bin/env python3
"""BSDX .dat (table) / MekaGroup.grp / WazaGroup.grp reader -> TSV.
Port of NeXAS_DX DatParser / MekaGroupGrpParser / WazaGroupGrpParser.
usage: bsdx_tables.py <datdir> <grpdir> <outdir>
.dat layout: int32 colCount; int32 colType[colCount] (0=int,1=cp932 cstring,2=int(new),3=byte?);
             rows until EOF, each column in order.
"""
import struct, sys, os

def read_cstr(b, p):
    e = b.index(b'\0', p)
    return b[p:e].decode('cp932', 'replace'), e + 1

def parse_dat(b):
    n, = struct.unpack_from('<i', b, 0); p = 4
    types = list(struct.unpack_from('<%di' % n, b, p)); p += 4 * n
    rows = []
    while p < len(b):
        row = []
        for t in types:
            if t == 1:
                s, p = read_cstr(b, p); row.append(s)
            elif t in (0, 2):
                row.append(struct.unpack_from('<i', b, p)[0]); p += 4
            else:
                raise ValueError('coltype %d' % t)
        rows.append(row)
    return types, rows

def parse_group(b, nstr, trailing_int):
    n, = struct.unpack_from('<i', b, 0); p = 4
    out = []
    for i in range(n):
        f, = struct.unpack_from('<i', b, p); p += 4
        if f == 0:
            out.append(None); continue
        e = []
        for _ in range(nstr):
            s, p = read_cstr(b, p); e.append(s)
        if trailing_int:
            e.append(struct.unpack_from('<i', b, p)[0]); p += 4
        out.append(e)
    return out

if __name__ == '__main__':
    datdir, grpdir, out = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    for fn in sorted(os.listdir(datdir)):
        if not fn.endswith('.dat'): continue
        b = open(os.path.join(datdir, fn), 'rb').read()
        try:
            types, rows = parse_dat(b)
        except Exception as ex:
            print('FAIL', fn, ex); continue
        with open(os.path.join(out, fn[:-4] + '.tsv'), 'w', encoding='utf-8') as f:
            f.write('#row\t' + '\t'.join('c%d:%s' % (i, 'S' if t == 1 else 'I') for i, t in enumerate(types)) + '\n')
            for i, r in enumerate(rows):
                f.write('%d\t' % i + '\t'.join(str(x).replace('\t', '\\t').replace('\n', '\\n') for x in r) + '\n')
    for name, nstr, ti in (('MekaGroup', 2, False), ('WazaGroup', 3, True)):
        b = open(os.path.join(grpdir, name + '.grp'), 'rb').read()
        g = parse_group(b, nstr, ti)
        with open(os.path.join(out, name + '.tsv'), 'w', encoding='utf-8') as f:
            for i, e in enumerate(g):
                f.write('%d\t' % i + ('<empty>' if e is None else '\t'.join(map(str, e))) + '\n')
