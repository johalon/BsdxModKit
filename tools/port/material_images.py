#!/usr/bin/env python3
"""MaterialBlock sprite lists: BHE -> BSDX semantics.

BHE mek MaterialBlock spriteGroups[g] = flat (anim, pattern) PAIRS (e.g. smoke anim 0 patterns 0..6).
BSDX mek MaterialBlock spriteGroups[g] = sorted unique IMAGE indices (png entries of spm g) to preload:
  in all 5795 non-empty lists of the 103 registered vanilla meks every list is sorted+unique, 53% have odd length,
  and no value reaches the spm's image count (調査記録 08 §2.7; the TOORU port builds them the same way, 調査記録 09).
bhe2bsdx.RefMap.material() keeps the BHE pair layout (only remapped); pairs_to_images() converts such a block.
"""


def page_images(spm, anim, pat):
    a = spm['animData'][anim]
    out = set()
    for pg in a['patData'][pat]['pageNo']:
        if pg >= 0:
            for ch in spm['pageData'][pg]['chipData']:
                out.add(ch['imageNo'])
    return out


def pairs_to_images(mb, spm_of, rep=None):
    """mb: BSDX-typed MaterialBlock whose spriteGroups hold (anim, pattern) pairs already mapped to BSDX groups/anims.
    spm_of(g) -> NeXAS spm JSON of BSDX group g. Returns a new block with sorted image-index lists."""
    ents = []
    for e in mb['entries']:
        spr = []
        for g, ids in enumerate(e['spriteGroups']):
            imgs = set()
            if ids:
                s = spm_of(g)
                for k in range(0, len(ids), 2):
                    imgs |= page_images(s, ids[k], ids[k + 1])
                if rep:
                    rep.add('MATERIAL_IMAGES', 'group %d: %d pairs -> %d images' % (g, len(ids) // 2, len(imgs)))
            spr.append(sorted(imgs))
        ents.append(dict(e, spriteGroups=spr))
    reg = mb['regularCount']
    return dict(mb, entries=ents, regularEntries=ents[:reg], trailingEntries=ents[reg:])


def check_images(mb, spm_of):
    """every list sorted/unique and inside the spm's image table -> list of problems"""
    bad = []
    for n, e in enumerate(mb['entries']):
        for g, ids in enumerate(e['spriteGroups']):
            if ids:
                ni = len(spm_of(g)['imageData'])
                if ids != sorted(set(ids)) or not all(0 <= i < ni for i in ids):
                    bad.append((n, g, ids[:10], ni))
    return bad
