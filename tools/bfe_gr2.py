#!/usr/bin/env python3
"""bfe_gr2.py - BALDR FORCE EXE GR2 image (and GR2-style compressed SPR) decoder.

GR2 header (little-endian):
  +0x00 'GR2'   (GR1 = raw, GR3 = 3-bit count variant used by later NeXAS)
  +0x03 u16 bpp            (8 for all BFE mech sheets; 16/24/32 also possible)
  +0x05 u32 width
  +0x09 u32 height
  +0x0D u32 unpacked_size  (= w*h*bpp/8 [+0x300 palette if 8bpp])
  +0x11 u32 ctl_bit_count
  +0x15 u8  ctl[(ctl_bit_count+7)/8]   (LSB-first flag bits)
  +.... u32 data_size (ignored)
  +.... data stream: bit 0 -> literal byte; bit 1 -> u16 w,
        count = (w & 0x1F) + 1, dist = (w >> 5) + 1  (GR3: 3/13 split)
Pixels: 8bpp indices, rows TOP-DOWN (confirmed visually on tooru sheets),
palette = 256 * RGB (3 bytes, R,G,B order) at the END of the unpacked buffer.
Transparent colour: palette INDEX 255 (verified: it is the dominant/background
index on all 80 tooru sheets; its RGB varies - magenta/green/yellow - so key by index).

The same LZ (5-bit count) is used by .SPR files:
  'SPR' + u32 unpacked_size + u32 ctl_bit_count + ctl + u32 + data.

Usage:
  bfe_gr2.py info  <file.grp>...
  bfe_gr2.py png   <file.grp> <out.png> [--alpha0]   (--alpha0: index 255 -> transparent)
  bfe_gr2.py unspr <file.spr> <out.bin>
"""
import struct
import sys
import zlib


def lz_unpack(buf, pos, out_size, count_bits=5):
    nbits = struct.unpack_from('<I', buf, pos)[0]; pos += 4
    ctl_len = (nbits + 7) // 8
    ctl = buf[pos:pos + ctl_len]; pos += ctl_len
    pos += 4  # data size
    mask = (1 << count_bits) - 1
    out = bytearray(out_size)
    dst = 0
    for i in range(nbits):
        if dst >= out_size:
            break
        if (ctl[i >> 3] >> (i & 7)) & 1:
            w = buf[pos] | (buf[pos + 1] << 8); pos += 2
            cnt = (w & mask) + 1
            dist = (w >> count_bits) + 1
            s = dst - dist
            for k in range(cnt):
                if dst >= out_size:
                    break
                out[dst] = out[s + k] if s + k >= 0 else 0
                dst += 1
        else:
            out[dst] = buf[pos]; pos += 1; dst += 1
    return bytes(out), dst


def read_gr2(path):
    b = open(path, 'rb').read()
    if b[:2] != b'GR':
        raise ValueError('not GRx: %s' % path)
    ver = b[2] - 0x30
    bpp, w, h = struct.unpack_from('<HII', b, 3)
    if ver == 1:
        usize = w * h * bpp // 8 + (0x300 if bpp == 8 else 0)
        data = b[0xD:0xD + usize]
        got = len(data)
    else:
        usize = struct.unpack_from('<I', b, 0xD)[0]
        data, got = lz_unpack(b, 0x11, usize, 3 if ver == 3 else 5)
    return dict(ver=ver, bpp=bpp, w=w, h=h, usize=usize, got=got, data=data)


def to_rgba(img, alpha0=True, key=255):
    w, h, bpp, d = img['w'], img['h'], img['bpp'], img['data']
    rows = []
    if bpp == 8:
        pal = d[w * h:w * h + 0x300]
        lut = []
        for i in range(256):
            r, g, bl = pal[i * 3:i * 3 + 3]
            lut.append(bytes((r, g, bl, 0 if (alpha0 and i == key) else 255)))
        for y in range(h):
            row = d[y * w:(y + 1) * w]
            rows.append(b''.join(lut[p] for p in row))
    elif bpp in (24, 32):
        st = w * bpp // 8
        for y in range(h):
            row = d[y * st:(y + 1) * st]
            px = []
            for x in range(w):
                bb, g, r = row[x * bpp // 8:x * bpp // 8 + 3]
                px.append(bytes((r, g, bb, 255)))
            rows.append(b''.join(px))
    else:
        raise NotImplementedError('bpp %d' % bpp)
    return rows


def write_png(path, w, h, rows):
    raw = b''.join(b'\0' + r for r in rows)
    def chunk(t, c):
        return struct.pack('>I', len(c)) + t + c + struct.pack('>I', zlib.crc32(t + c) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b'')
    open(path, 'wb').write(png)


def unspr(path):
    b = open(path, 'rb').read()
    if b[:3] != b'SPR':
        raise ValueError('not SPR')
    usize = struct.unpack_from('<I', b, 3)[0]
    data, got = lz_unpack(b, 7, usize, 5)
    return data, got, usize


def main(a):
    if len(a) < 3:
        print(__doc__); return 1
    if a[1] == 'info':
        for p in a[2:]:
            i = read_gr2(p)
            print('%s GR%d bpp=%d %dx%d usize=%d decoded=%d %s' % (
                p, i['ver'], i['bpp'], i['w'], i['h'], i['usize'], i['got'],
                'OK' if i['got'] == i['usize'] else 'SHORT'))
    elif a[1] == 'png':
        i = read_gr2(a[2])
        write_png(a[3], i['w'], i['h'], to_rgba(i, '--alpha0' in a))
    elif a[1] == 'unspr':
        data, got, us = unspr(a[2])
        open(a[3], 'wb').write(data)
        print('SPR unpacked %d/%d bytes' % (got, us))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
