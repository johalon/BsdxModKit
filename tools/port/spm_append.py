#!/usr/bin/env python3
"""Append-preserving BSDX .spm editor (SPM VER-2.00 / 2.02).

Why: NeXAS_DX's SpmGenerator drops the unparsed tail that ~157 BSDX spm have (e.g. Tama.spm, docs/formats/01_formats_and_tools.md §2.4), so a
shared spm must not be regenerated through NeXAS_DX. This module parses the spm *layout* (byte offsets of every
section) and writes a new file that consists of the ORIGINAL bytes with insertions:

    [header+numPages] [orig pages]  + new pages
    [numImages]       [orig images] + new images
    [patPageNum numAnims] [orig anims] + new anims
    [orig tail]  - every vanilla tail found (157/1989 files) is an exact byte copy of the anim table
                   ([patPageNum numAnims anims]); such a tail gets its count patched and the same new anims appended,
                   so it stays a copy. Any other tail would be left untouched.

Only the count ints (numPageData, numImageData, numAnimData, + the tail copy's numAnimData) change. Existing page/image/anim indices stay
valid because everything new is appended after the existing entries of each section. The writer refuses to add an
anim whose patData width differs from the file's patPageNum.

API
  layout = parse(data)                          -> dict with offsets, counts, raw section slices
  pages, images, anims = extract(data, layout, anim_ids)   -> raw bytes of the anims + the pages/images they use,
                                                  re-indexed to be self contained (page 0.., image 0..)
  out, info = append(base_bytes, donor_bytes, anim_ids)  -> new file bytes, info {anim_map, page_base, image_base, images}
  verify_append(base, out, info)                -> asserts the preservation properties (used by the test + builds)
"""
import struct

ENC = 'cp932'
V202 = b'SPM VER-2.02'


class R:
    def __init__(self, b, o=0):
        self.b, self.o = b, o

    def i(self):
        v = struct.unpack_from('<i', self.b, self.o)[0]; self.o += 4; return v

    def u8(self):
        v = self.b[self.o]; self.o += 1; return v

    def cstr(self):
        e = self.b.index(b'\0', self.o); s = self.b[self.o:e]; self.o = e + 1; return s


def _page(r, v202):
    """returns dict(start, end, chip_image_offsets[list of byte offsets of imageNo], nchip)"""
    st = r.o
    nchip = r.i(); r.o += 4 * 2 + 16 + 4 + 8          # w h rect option rotX rotY
    hit = r.i() & 0xFFFFFFFF
    if v202:
        r.o += 1
    for k in range(32):
        if hit & (1 << k):
            r.o += 4 + 16 + 8
    imgoffs = []
    for _ in range(nchip):
        imgoffs.append(r.o)
        r.o += 4 + 16 + 8 + 16 + 4 + (1 if v202 else 0) + 8
    return {'start': st, 'end': r.o, 'img_offs': imgoffs}


def _anim(r, ppn):
    st = r.o
    name = r.cstr(); numpat = r.i(); r.o += 8
    pageoffs = []
    for _ in range(numpat & 0xFFFF):
        r.o += 4
        for _ in range(ppn):
            pageoffs.append(r.o); r.o += 4
    return {'start': st, 'end': r.o, 'name': name, 'numPat': numpat & 0xFFFF, 'page_offs': pageoffs}


def parse(data):
    r = R(data)
    ver = r.cstr()
    v202 = ver == V202
    L = {'version': ver, 'v202': v202}
    L['off_numPage'] = r.o; npg = r.i()
    L['pages'] = [_page(r, v202) for _ in range(npg)]
    L['pages_end'] = r.o
    L['off_numImage'] = r.o; nim = r.i()
    L['images'] = []
    for _ in range(nim):
        st = r.o; nm = r.cstr(); L['images'].append({'start': st, 'end': r.o, 'name': nm})
    L['images_end'] = r.o
    L['off_patPageNum'] = r.o; ppn = r.i()
    L['off_numAnim'] = r.o; nan = r.i()
    L['patPageNum'] = ppn
    L['anims'] = [_anim(r, ppn) for _ in range(nan)]
    L['anims_end'] = r.o
    L['tail'] = data[r.o:]
    assert r.o <= len(data)
    return L


def page_bytes(data, L, k, image_map):
    """raw bytes of page k with chip imageNo remapped through image_map (old -> new)"""
    p = L['pages'][k]
    b = bytearray(data[p['start']:p['end']])
    for o in p['img_offs']:
        rel = o - p['start']
        old = struct.unpack_from('<i', b, rel)[0]
        struct.pack_into('<i', b, rel, image_map[old])
    return bytes(b)


def anim_bytes(data, L, k, page_map):
    a = L['anims'][k]
    b = bytearray(data[a['start']:a['end']])
    for o in a['page_offs']:
        rel = o - a['start']
        old = struct.unpack_from('<i', b, rel)[0]
        struct.pack_into('<i', b, rel, page_map[old] if old >= 0 else old)
    return bytes(b)


def tail_kind(data, L):
    """'' (no tail), 'animdup' (tail == byte copy of the anim table [patPageNum numAnims anims...]; true for all 157
    vanilla BSDX spm that have a tail) or 'unknown'"""
    if not L['tail']:
        return ''
    return 'animdup' if L['tail'] == data[L['off_patPageNum']:L['anims_end']] else 'unknown'


def append(base, donor, anim_ids, image_rename=None):
    """append donor anims `anim_ids` (with the pages and images they use) to the end of each section of `base`.
    Both are BSDX-format spm bytes (donor typically = a BHE spm converted to BSDX by PortTool). Returns (bytes, info)."""
    Lb, Ld = parse(base), parse(donor)
    assert Lb['v202'] == Ld['v202'], 'version mismatch'
    assert Lb['patPageNum'] == Ld['patPageNum'], ('patPageNum differs', Lb['patPageNum'], Ld['patPageNum'])
    pb, ib, ab = len(Lb['pages']), len(Lb['images']), len(Lb['anims'])
    # pages used by the anims (order of first use), images used by those pages (order of first use)
    pages = []
    for k in anim_ids:
        for o in Ld['anims'][k]['page_offs']:
            pg = struct.unpack_from('<i', donor, o)[0]
            if pg >= 0 and pg not in pages:
                pages.append(pg)
    imgs = []
    for pg in pages:
        for o in Ld['pages'][pg]['img_offs']:
            im = struct.unpack_from('<i', donor, o)[0]
            if im not in imgs:
                imgs.append(im)
    # reuse a base image entry when the same png name is already there (never the case for the BHE-only pngs)
    base_names = {x['name'].lower(): i for i, x in enumerate(Lb['images'])}
    image_map, new_images = {}, []
    for im in imgs:
        nm = Ld['images'][im]['name']
        if image_rename:
            nm = image_rename(nm)
        if nm.lower() in base_names:
            image_map[im] = base_names[nm.lower()]
        else:
            image_map[im] = ib + len(new_images); new_images.append(nm)
    page_map = {pg: pb + n for n, pg in enumerate(pages)}
    new_pages = b''.join(page_bytes(donor, Ld, pg, image_map) for pg in pages)
    new_imgs = b''.join(nm + b'\0' for nm in new_images)
    new_anims = b''.join(anim_bytes(donor, Ld, k, page_map) for k in anim_ids)
    out = bytearray()
    out += base[:Lb['off_numPage']]
    out += struct.pack('<i', pb + len(pages))
    out += base[Lb['off_numPage'] + 4:Lb['pages_end']] + new_pages
    out += struct.pack('<i', ib + len(new_images))
    out += base[Lb['off_numImage'] + 4:Lb['images_end']] + new_imgs
    out += base[Lb['off_patPageNum']:Lb['off_numAnim']]
    out += struct.pack('<i', ab + len(anim_ids))
    out += base[Lb['off_numAnim'] + 4:Lb['anims_end']] + new_anims
    tk = tail_kind(base, Lb)
    if tk == 'animdup':
        # the tail is a second copy of the anim table: keep its bytes, patch its count, append the same new anims so
        # the invariant "tail == anim table" of the vanilla files still holds (whichever copy the engine reads)
        t = Lb['tail']
        out += t[:4] + struct.pack('<i', ab + len(anim_ids)) + t[8:] + new_anims
    else:
        out += Lb['tail']          # '' or unknown: untouched
    info = {'anim_map': {k: ab + n for n, k in enumerate(anim_ids)}, 'page_base': pb, 'n_pages': len(pages),
            'image_base': ib, 'images': [nm.decode(ENC) for nm in new_images],
            'anim_names': {k: Ld['anims'][k]['name'].decode(ENC, 'replace').strip() for k in anim_ids},
            'counts_before': (pb, ib, ab), 'tail_len': len(Lb['tail']), 'tail_kind': tk}
    return bytes(out), info


def verify_append(base, out, info):
    """the original bytes survive: every original section is a byte-identical run in `out`, the tail is the exact
    file suffix, only the three counts changed, and the result re-parses with the expected counts."""
    Lb, Lo = parse(base), parse(out)
    pb, ib, ab = info['counts_before']
    assert len(Lo['pages']) == pb + info['n_pages'] and len(Lo['images']) == ib + len(info['images'])
    assert len(Lo['anims']) == ab + len(info['anim_map'])
    # header (version) identical
    assert out[:Lb['off_numPage']] == base[:Lb['off_numPage']]
    # original pages / images / anims: identical bytes, in the same order, at the start of each section
    assert out[Lo['off_numPage'] + 4:Lo['off_numPage'] + 4 + (Lb['pages_end'] - Lb['off_numPage'] - 4)] == base[Lb['off_numPage'] + 4:Lb['pages_end']]
    assert out[Lo['off_numImage'] + 4:Lo['off_numImage'] + 4 + (Lb['images_end'] - Lb['off_numImage'] - 4)] == base[Lb['off_numImage'] + 4:Lb['images_end']]
    assert out[Lo['off_patPageNum']:Lo['off_numAnim']] == base[Lb['off_patPageNum']:Lb['off_numAnim']]
    assert out[Lo['off_numAnim'] + 4:Lo['off_numAnim'] + 4 + (Lb['anims_end'] - Lb['off_numAnim'] - 4)] == base[Lb['off_numAnim'] + 4:Lb['anims_end']]
    # tail: untouched, or (animdup) original bytes + patched count + the same appended anims, still == anim table
    tk = info['tail_kind']
    if tk == 'animdup':
        t0, t1 = Lb['tail'], Lo['tail']
        nnew = Lo['anims_end'] - Lo['anims'][ab]['start']
        assert t1[:4] == t0[:4] and t1[8:len(t0)] == t0[8:] and struct.unpack_from('<i', t1, 4)[0] == len(Lo['anims'])
        assert t1 == out[Lo['off_patPageNum']:Lo['anims_end']] and len(t1) == len(t0) + nnew
    else:
        assert Lo['tail'] == Lb['tail'] and out.endswith(Lb['tail'])
    # the file minus the inserted runs and the 3 counts == the original file
    ins = [(Lo['pages'][pb]['start'] if info['n_pages'] else Lo['pages_end'], Lo['pages_end']),
           (Lo['images'][ib]['start'] if info['images'] else Lo['images_end'], Lo['images_end']),
           (Lo['anims'][ab]['start'], Lo['anims_end'])]
    rebuilt = bytearray(out)
    if tk == 'animdup':
        del rebuilt[len(out) - nnew:]
        tail_cnt = len(rebuilt) - len(Lb['tail']) + 4
        rebuilt[tail_cnt:tail_cnt + 4] = struct.pack('<i', ab)
    for s, e in reversed(ins):
        del rebuilt[s:e]
    for off, n in ((Lb['off_numAnim'], ab), (Lb['off_numImage'], ib), (Lb['off_numPage'], pb)):
        rebuilt[off:off + 4] = struct.pack('<i', n)
    assert bytes(rebuilt) == base, 'original bytes not preserved'
    # new anims reference only new pages, new pages only valid images
    for k, na in info['anim_map'].items():
        for o in Lo['anims'][na]['page_offs']:
            pg = struct.unpack_from('<i', out, o)[0]
            assert pg < 0 or pb <= pg < len(Lo['pages'])
    for p in Lo['pages'][pb:]:
        for o in p['img_offs']:
            assert 0 <= struct.unpack_from('<i', out, o)[0] < len(Lo['images'])
    return True


def nexas_regen_equivalent(orig, regen):
    """NeXAS_DX parse->generate of `orig` gave `regen`. True when identical, or when the only difference is the
    dropped tail and that tail is the anim-table copy (the known NeXAS_DX limitation, docs/formats/01_formats_and_tools.md §2.4)."""
    if orig == regen:
        return True
    L = parse(orig)
    return tail_kind(orig, L) == 'animdup' and regen == orig[:len(orig) - len(L['tail'])]
