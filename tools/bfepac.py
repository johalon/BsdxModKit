#!/usr/bin/env python3
"""bfepac.py - BALDR FORCE EXE (old GIGA/NeXAS) "PAC" archive lister/extractor.

Old PAC layout (all little-endian):
  +0x00 char[3] 'PAC' + 1 byte (0x00 or 'w' (0x77); ignored by reader)
  +0x04 u32 count
  +0x08 u32 pack_type  (0=none, 1=LZSS, 2=Huffman, 3=zlib, 4=zlib-or-none)
  +0x0C entry[count], each 0x4C bytes:
        char name[0x40] (cp932, NUL padded)
        u32  offset      (absolute)
        u32  unpacked_size
        u32  packed_size
  (some very old variants use 0x20-byte names; auto-detected)
  data follows the table.
LZSS = classic Okumura: 4KB window, fill 0x00, init pos 0xFEE,
flag byte LSB-first, 1=literal, 0=ref (12-bit pos, 4-bit len+3).

Usage:
  bfepac.py list    <file.pac>
  bfepac.py extract <file.pac> <outdir>
"""
import os
import struct
import sys
import zlib


def lzss_decode(src, out_size):
    win = bytearray(0x1000)
    wp = 0xFEE
    out = bytearray()
    i = 0
    n = len(src)
    while i < n and len(out) < out_size:
        flags = src[i]; i += 1
        for b in range(8):
            if i >= n or len(out) >= out_size:
                break
            if flags & (1 << b):
                c = src[i]; i += 1
                out.append(c); win[wp] = c; wp = (wp + 1) & 0xFFF
            else:
                if i + 1 >= n:
                    i = n; break
                lo = src[i]; hi = src[i + 1]; i += 2
                pos = lo | ((hi & 0xF0) << 4)
                ln = (hi & 0x0F) + 3
                for k in range(ln):
                    c = win[(pos + k) & 0xFFF]
                    out.append(c); win[wp] = c; wp = (wp + 1) & 0xFFF
    return bytes(out[:out_size])


def read_index(data):
    if data[:3] != b'PAC':
        raise ValueError('not a PAC')
    count, ptype = struct.unpack_from('<II', data, 4)
    for namelen in (0x40, 0x20):
        ents = []
        pos = 0xC
        ok = True
        for _ in range(count):
            raw = data[pos:pos + namelen]
            name = raw.split(b'\0', 1)[0]
            if not name:
                ok = False; break
            off, usize, psize = struct.unpack_from('<III', data, pos + namelen)
            if off + psize > len(data):
                ok = False; break
            ents.append((name.decode('cp932', 'replace'), off, usize, psize))
            pos += namelen + 12
        if ok:
            return ptype, namelen, ents
    raise ValueError('could not parse old-style index')


def unpack(data, ptype, off, usize, psize):
    raw = data[off:off + psize]
    if ptype == 0 or (ptype == 4 and usize == psize):
        return raw
    if ptype == 1:
        return lzss_decode(raw, usize)
    if ptype in (3, 4):
        return zlib.decompress(raw)
    raise NotImplementedError('pack type %d (Huffman) not implemented' % ptype)


def main(argv):
    if len(argv) < 3:
        print(__doc__); return 1
    cmd, path = argv[1], argv[2]
    data = open(path, 'rb').read()
    ptype, namelen, ents = read_index(data)
    if cmd == 'list':
        print('# %s: %d entries, pack_type=%d, namelen=0x%x' % (path, len(ents), ptype, namelen))
        for name, off, us, ps in ents:
            print('%-40s off=0x%08x usize=%9d psize=%9d' % (name, off, us, ps))
    elif cmd == 'extract':
        outdir = argv[3]
        os.makedirs(outdir, exist_ok=True)
        for name, off, us, ps in ents:
            buf = unpack(data, ptype, off, us, ps)
            if len(buf) != us:
                print('WARN size mismatch %s: %d != %d' % (name, len(buf), us))
            safe = name.replace('\\', '/').lstrip('/')
            dst = os.path.join(outdir, safe)
            os.makedirs(os.path.dirname(dst) or outdir, exist_ok=True)
            with open(dst, 'wb') as f:
                f.write(buf)
        print('extracted %d files to %s' % (len(ents), outdir))
    else:
        print(__doc__); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
