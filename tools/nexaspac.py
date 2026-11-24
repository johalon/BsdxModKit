#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nexaspac.py - NeXAS engine .pac archive tool (BALDR SKY DiveX etc.)

Format ("new" NeXAS PAC, used by all BSDX pacs):
  0x00  char[3]  "PAC"
  0x03  u8       (unused by readers; observed 00/2E/62 - garbage byte)
  0x04  u32      entry count
  0x08  u32      pack type  (0=none 1=lzss 2=huffman 3=deflate 4=deflate-or-stored
                             5=stored; zstd(6/7) only in later engines; BSDX uses 4)
  0x0C  ...      entry data (concatenated)
  EOF-4-N ..EOF-4  index: Huffman-coded, then every byte bitwise NOT-ed
  EOF-4  u32     N = size of encoded index
  Decoded index = count * 0x4C bytes:
     char name[0x40]  (cp932, NUL padded)
     u32  offset      (absolute file offset)
     u32  unpacked_size
     u32  packed_size
  Type 4 (BSDX): per-entry method decided by the exe from the EXTENSION:
     ogg/wav/png/fnt/mpg/mpeg/avi = stored, all others = zlib (level 6 in originals).
     (GARbro instead uses packed_size != unpacked_size; equivalent for originals.)
  Lookup in the game: case-insensitive filename (no directories), first mounted wins.

Usage:
  nexaspac.py list    X.pac
  nexaspac.py extract X.pac outdir
  nexaspac.py create  indir X.pac [--type 4] [--order listfile] [--level 6]
  nexaspac.py roundtrip X.pac workdir
"""
import os
import struct
import sys
import zlib
import heapq
import argparse

ENC = 'cp932'
NAME_LEN = 0x40
ENTRY_SIZE = 0x4C
# BaldrSky.exe strings at VA 0x819B94.. : extensions that are stored raw in a type-4 pac
TYPE4_STORED_EXT = ('ogg', 'wav', 'png', 'fnt', 'mpg', 'mpeg', 'avi')


def ext_of(name):
    n = name.lower()
    return n.rsplit('.', 1)[-1] if '.' in n else ''


# ---------------------------------------------------------------- Huffman
class _BitReader:
    __slots__ = ('data', 'pos', 'bit', 'cur')

    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.bit = 0
        self.cur = 0

    def get(self, n):
        v = 0
        for _ in range(n):
            if self.bit == 0:
                if self.pos >= len(self.data):
                    return -1
                self.cur = self.data[self.pos]
                self.pos += 1
                self.bit = 8
            self.bit -= 1
            v = (v << 1) | ((self.cur >> self.bit) & 1)
        return v


def huffman_decode(src, out_size):
    """NeXAS/GARbro HuffmanDecompressor: MSB-first, pre-order tree
    (1 => internal node {left,right}, 0 => 8-bit leaf), nodes numbered from 256."""
    br = _BitReader(src)
    lhs = [0] * 512
    rhs = [0] * 512
    token = [256]

    def tree():
        b = br.get(1)
        if b == -1:
            raise EOFError('huffman: eof in tree')
        if b:
            v = token[0]
            token[0] += 1
            if v >= 512:
                raise ValueError('huffman: bad tree')
            lhs[v] = tree()
            rhs[v] = tree()
            return v
        return br.get(8)

    sys.setrecursionlimit(10000)
    root = tree()
    out = bytearray()
    while len(out) < out_size:
        s = root
        while s >= 0x100:
            b = br.get(1)
            if b == -1:
                return bytes(out)
            s = rhs[s] if b else lhs[s]
        out.append(s)
    return bytes(out)


def huffman_encode(data):
    """Inverse of huffman_decode."""
    freq = [0] * 256
    for b in data:
        freq[b] += 1
    heap = [(f, i, i) for i, f in enumerate(freq) if f]  # (freq, tiebreak, node)
    if not heap:
        heap = [(1, 0, 0)]
    if len(heap) == 1:  # force an internal root so decoder consumes bits
        heap.append((0, 1 if heap[0][2] != 1 else 2, 1 if heap[0][2] != 1 else 2))
    heapq.heapify(heap)
    children = {}
    nxt = 256
    while len(heap) > 1:
        f1, _, a = heapq.heappop(heap)
        f2, _, b = heapq.heappop(heap)
        children[nxt] = (a, b)
        heapq.heappush(heap, (f1 + f2, nxt, nxt))
        nxt += 1
    root = heap[0][2]
    codes = {}
    bits = []

    def walk(n, code):
        if n >= 256:
            bits.append('1')
            a, b = children[n]
            walk(a, code + '0')
            walk(b, code + '1')
        else:
            bits.append('0' + format(n, '08b'))
            codes[n] = code
    walk(root, '')
    bits.extend(codes[b] for b in data)
    s = ''.join(bits)
    s += '0' * (-len(s) % 8)
    return int(s, 2).to_bytes(len(s) // 8, 'big') if s else b''


# ---------------------------------------------------------------- LZSS (type 1)
def lzss_decode(src, out_size):
    """Classic Okumura LZSS (GARbro LzssStream defaults: 4K window, fill 0, pos 0xFEE)."""
    win = bytearray(0x1000)
    wp = 0xFEE
    out = bytearray()
    i = 0
    n = len(src)
    while i < n and len(out) < out_size:
        ctl = src[i]; i += 1
        for bit in range(8):
            if i >= n or len(out) >= out_size:
                break
            if ctl & (1 << bit):
                c = src[i]; i += 1
                out.append(c); win[wp] = c; wp = (wp + 1) & 0xFFF
            else:
                if i + 1 >= n:
                    break
                lo, hi = src[i], src[i + 1]; i += 2
                off = lo | ((hi & 0xF0) << 4)
                cnt = (hi & 0x0F) + 3
                for k in range(cnt):
                    c = win[(off + k) & 0xFFF]
                    out.append(c); win[wp] = c; wp = (wp + 1) & 0xFFF
    return bytes(out)


def lzss_encode_literal(data):
    """'Compressed' LZSS stream using only literals (valid, not smaller)."""
    out = bytearray()
    for i in range(0, len(data), 8):
        chunk = data[i:i + 8]
        out.append((1 << len(chunk)) - 1 if len(chunk) < 8 else 0xFF)
        out += chunk
    return bytes(out)


# ---------------------------------------------------------------- PAC
class Entry:
    __slots__ = ('name', 'offset', 'usize', 'psize')

    def __init__(self, name, offset, usize, psize):
        self.name, self.offset, self.usize, self.psize = name, offset, usize, psize


class Pac:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            self.data = f.read()
        d = self.data
        if d[:3] != b'PAC':
            raise ValueError('not a PAC')
        self.byte3 = d[3]
        self.count, self.pack_type = struct.unpack_from('<II', d, 4)
        self.entries = self._read_index_new()
        self.index_kind = 'new'

    def _read_index_new(self):
        d = self.data
        isz = struct.unpack_from('<I', d, len(d) - 4)[0]
        enc = bytes((~b) & 0xFF for b in d[len(d) - 4 - isz:len(d) - 4])
        raw = huffman_decode(enc, self.count * ENTRY_SIZE)
        if len(raw) != self.count * ENTRY_SIZE:
            raise ValueError('index decode short')
        self.index_raw = raw
        self.index_enc_size = isz
        out = []
        for i in range(self.count):
            rec = raw[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE]
            name = rec[:NAME_LEN].split(b'\0', 1)[0].decode(ENC)
            off, us, ps = struct.unpack_from('<III', rec, NAME_LEN)
            out.append(Entry(name, off, us, ps))
        return out

    def is_packed(self, e):
        """Mirrors BaldrSky.exe CPack mount (0x794150): for pack type 4 the
        per-entry method is chosen by EXTENSION (lower-cased), not by size:
        ogg/wav/png/fnt/mpg/mpeg/avi -> stored (0), everything else -> zlib (3)."""
        t = self.pack_type
        if t in (0, 5):
            return False
        if t == 4:
            return ext_of(e.name) not in TYPE4_STORED_EXT
        return True

    def read(self, e):
        raw = self.data[e.offset:e.offset + e.psize]
        if not self.is_packed(e):
            return raw
        t = self.pack_type
        if t == 1:
            return lzss_decode(raw, e.usize)
        if t == 2:
            return huffman_decode(raw, e.usize)
        if t in (3, 4):
            return zlib.decompress(raw)
        raise ValueError('unknown/unsupported pack type %d (BSDX exe supports 0-5)' % t)


def write_pac(path, items, pack_type=4, level=6, byte3=0):
    """items: list of (name, bytes). Writes a 'new'-style NeXAS PAC."""
    body = bytearray()
    index = bytearray()
    pos = 0x0C
    for name, data in items:
        bname = name.encode(ENC)
        if len(bname) >= NAME_LEN:
            raise ValueError('name too long (>=64 bytes cp932): %s' % name)
        if pack_type == 0:
            blob = data
        elif pack_type == 1:
            blob = lzss_encode_literal(data)
        elif pack_type == 2:
            blob = huffman_encode(data)
        elif pack_type == 3:
            blob = zlib.compress(data, level)
        elif pack_type == 4:
            # MUST follow the exe's extension rule (see Pac.is_packed); never fall
            # back to 'stored' just because zlib output is larger.
            if ext_of(name) in TYPE4_STORED_EXT:
                blob = data
            else:
                blob = zlib.compress(data, level)
        else:
            raise ValueError('pack type %d not supported for writing' % pack_type)
        index += bname.ljust(NAME_LEN, b'\0')
        index += struct.pack('<III', pos, len(data), len(blob))
        body += blob
        pos += len(blob)
    enc = bytes((~b) & 0xFF for b in huffman_encode(bytes(index)))
    with open(path, 'wb') as f:
        f.write(b'PAC' + bytes([byte3]) + struct.pack('<II', len(items), pack_type))
        f.write(body)
        f.write(enc)
        f.write(struct.pack('<I', len(enc)))


# ---------------------------------------------------------------- CLI
def safe_join(root, name):
    name = name.replace('\\', '/')
    p = os.path.normpath(os.path.join(root, name))
    if not p.startswith(os.path.abspath(root)):
        raise ValueError('unsafe name ' + name)
    return p


def cmd_list(a):
    p = Pac(a.pac)
    print('# %s  count=%d  pack_type=%d  byte3=0x%02X  index_enc=%d' % (
        a.pac, p.count, p.pack_type, p.byte3, p.index_enc_size))
    for e in p.entries:
        print('%08X %10d %10d %s %s' % (e.offset, e.usize, e.psize,
                                        'Z' if p.is_packed(e) else '-', e.name))


def extract(pacpath, outdir):
    p = Pac(pacpath)
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)
    order = []
    for e in p.entries:
        data = p.read(e)
        if len(data) != e.usize:
            raise ValueError('size mismatch %s' % e.name)
        fp = safe_join(outdir, e.name)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, 'wb') as f:
            f.write(data)
        order.append(e.name)
    # keep original order + header info next to (not inside) the output dir
    with open(outdir.rstrip('/') + '.order.txt', 'w', encoding='utf-8') as f:
        f.write('#pack_type=%d byte3=%d\n' % (p.pack_type, p.byte3))
        f.write('\n'.join(order) + '\n')
    return p


def cmd_extract(a):
    p = extract(a.pac, a.outdir)
    print('extracted %d files (pack_type=%d)' % (p.count, p.pack_type))


def gather(indir, orderfile=None):
    indir = os.path.abspath(indir)
    names = None
    if orderfile is None and os.path.exists(indir.rstrip('/') + '.order.txt'):
        orderfile = indir.rstrip('/') + '.order.txt'
    files = []
    for r, _, fs in os.walk(indir):
        for fn in fs:
            files.append(os.path.relpath(os.path.join(r, fn), indir).replace(os.sep, '\\'))
    if orderfile:
        with open(orderfile, encoding='utf-8') as f:
            names = [l.rstrip('\n') for l in f if l.strip() and not l.startswith('#')]
        extra = sorted(set(files) - set(names))
        names = [n for n in names if n in set(files)] + extra
    else:
        names = sorted(files)
    return [(n, open(safe_join(indir, n), 'rb').read()) for n in names]


def cmd_create(a):
    items = gather(a.indir, a.order)
    write_pac(a.pac, items, a.type, a.level)
    print('wrote %s: %d entries, type %d' % (a.pac, len(items), a.type))


def cmd_roundtrip(a):
    base = os.path.splitext(os.path.basename(a.pac))[0]
    d1 = os.path.join(a.workdir, base + '_rt1')
    d2 = os.path.join(a.workdir, base + '_rt2')
    p = extract(a.pac, d1)
    out = os.path.join(a.workdir, base + '_rt.pac')
    items = gather(d1)
    write_pac(out, items, p.pack_type, 6, p.byte3)
    q = Pac(out)
    assert [e.name for e in q.entries] == [e.name for e in p.entries], 'order differs'
    bad = 0
    for e1, e2 in zip(p.entries, q.entries):
        if p.read(e1) != q.read(e2):
            bad += 1
            print('MISMATCH', e1.name)
    extract(out, d2)
    body_same = p.data[:q.entries[-1].offset + q.entries[-1].psize] == \
        q.data[:q.entries[-1].offset + q.entries[-1].psize] if q.count else True
    idx_same = p.index_raw == q.index_raw
    print('%s: %d entries, content_mismatches=%d, orig=%d B, repack=%d B, '
          'header+body_identical=%s, decoded_index_identical=%s, whole_file_identical=%s' % (
              base, p.count, bad, len(p.data), len(q.data), body_same, idx_same, p.data == q.data))
    return bad


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('list'); s.add_argument('pac'); s.set_defaults(fn=cmd_list)
    s = sp.add_parser('extract'); s.add_argument('pac'); s.add_argument('outdir'); s.set_defaults(fn=cmd_extract)
    s = sp.add_parser('create'); s.add_argument('indir'); s.add_argument('pac')
    s.add_argument('--type', type=int, default=4); s.add_argument('--level', type=int, default=6)
    s.add_argument('--order'); s.set_defaults(fn=cmd_create)
    s = sp.add_parser('roundtrip'); s.add_argument('pac'); s.add_argument('workdir'); s.set_defaults(fn=cmd_roundtrip)
    a = ap.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
