#!/usr/bin/env python3
"""pac_list_all.py — フォルダ内の全 .pac のファイル一覧を txt に書き出す（読み取りのみ・高速）。
巨大 pac でも末尾のインデックスだけを読むので、数 GB でも一瞬で終わる。
使い方（Windows）:
  python pac_list_all.py <ゲームフォルダ> <出力フォルダ>
例:
  python <PROJECT>\\tools\\pac_list_all.py <GAME> <PROJECT>\\pac_lists\\BALDRSKY_DIVEX
出力: <出力フォルダ>\\<pac名>.list.txt （列: offset, 展開後サイズ, 格納サイズ, ファイル名）
"""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nexaspac import huffman_decode  # 同じ tools フォルダの nexaspac.py を使う

ENTRY, NAMELEN = 0x4C, 0x40

def list_pac(path):
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        head = f.read(12)
        if head[:3] != b'PAC':
            return None, 'not PAC'
        count, ptype = struct.unpack_from('<II', head, 4)
        f.seek(size - 4)
        isz, = struct.unpack('<I', f.read(4))
        if isz <= 0 or isz > size - 16:
            return None, 'old-style or unknown index'
        f.seek(size - 4 - isz)
        enc = bytes((~b) & 0xFF for b in f.read(isz))
    raw = huffman_decode(enc, count * ENTRY)
    rows = []
    for i in range(count):
        rec = raw[i * ENTRY:(i + 1) * ENTRY]
        name = rec[:NAMELEN].split(b'\0', 1)[0].decode('cp932', 'replace')
        off, us, ps = struct.unpack_from('<III', rec, NAMELEN)
        rows.append((off, us, ps, name))
    return (count, ptype, rows), None

def main():
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(1)
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for fn in sorted(os.listdir(src)):
        if not fn.lower().endswith('.pac'):
            continue
        try:
            res, err = list_pac(os.path.join(src, fn))
        except Exception as e:
            res, err = None, repr(e)
        if err:
            print('%-20s SKIP (%s)' % (fn, err)); continue
        count, ptype, rows = res
        with open(os.path.join(out, fn + '.list.txt'), 'w', encoding='utf-8') as w:
            w.write('# %s count=%d pack_type=%d\n' % (fn, count, ptype))
            for off, us, ps, name in rows:
                w.write('%08X\t%d\t%d\t%s\n' % (off, us, ps, name))
        print('%-20s %6d files' % (fn, count))
    print('done ->', out)

if __name__ == '__main__':
    main()
