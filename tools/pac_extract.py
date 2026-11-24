#!/usr/bin/env python3
"""pac_extract.py — pac から名前のパターンに合うファイルだけを取り出す（読み取りのみ・巨大 pac 対応）。
使い方（Windows）:
  python pac_extract.py <pacファイル> <出力フォルダ> <パターン> [<パターン> ...]
  パターンはワイルドカード（大文字小文字は無視）。例: "tsukuyomi*"  "*.spm"
例:
  python <PROJECT>\\tools\\pac_extract.py <BHE>\\Bmp.pac <PROJECT>\\extract\\BHE_Bmp "tsukuyomi*"
"""
import os, sys, struct, zlib, fnmatch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nexaspac import huffman_decode, lzss_decode, TYPE4_STORED_EXT, ext_of

ENTRY, NAMELEN = 0x4C, 0x40

def main():
    if len(sys.argv) < 4:
        print(__doc__); sys.exit(1)
    pac, out, pats = sys.argv[1], sys.argv[2], [p.lower() for p in sys.argv[3:]]
    os.makedirs(out, exist_ok=True)
    size = os.path.getsize(pac)
    with open(pac, 'rb') as f:
        head = f.read(12)
        assert head[:3] == b'PAC', 'not a PAC'
        count, ptype = struct.unpack_from('<II', head, 4)
        f.seek(size - 4); isz, = struct.unpack('<I', f.read(4))
        f.seek(size - 4 - isz)
        raw = huffman_decode(bytes((~b) & 0xFF for b in f.read(isz)), count * ENTRY)
        n = 0
        for i in range(count):
            rec = raw[i * ENTRY:(i + 1) * ENTRY]
            name = rec[:NAMELEN].split(b'\0', 1)[0].decode('cp932', 'replace')
            if not any(fnmatch.fnmatch(name.lower(), p) for p in pats):
                continue
            off, us, ps = struct.unpack_from('<III', rec, NAMELEN)
            f.seek(off); data = f.read(ps)
            packed = ptype not in (0, 5) and not (ptype == 4 and ext_of(name) in TYPE4_STORED_EXT)
            if packed:
                if ptype == 1: data = lzss_decode(data, us)
                elif ptype == 2: data = huffman_decode(data, us)
                else: data = zlib.decompress(data)
            if os.path.basename(name) != name or name in ('.', '..'):
                print('skip unsafe name', name); continue
            open(os.path.join(out, name), 'wb').write(data)
            n += 1
    print('extracted %d files -> %s' % (n, out))

if __name__ == '__main__':
    main()
