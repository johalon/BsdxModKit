#!/usr/bin/env python3
"""Summarize BSDX .mek files (basic info + weapon list). Port of NeXAS_DX MekParser (head/basic/weapon blocks).
usage: bsdx_mekinfo.py <mekdir> [--weapons] [--tsv out.tsv]
"""
import struct, sys, os

BASIC = ['waz','spm','type','strLv','force','hp','fc1','fc2','boostLv','boostInc','armor','combo',
         'melee','shoot','dura','mob','weight','walk','dash','sdash','bdash','hover']
WFIELDS = ['switchToMek','wazSeq','fcAmount','heatMax','heatMin','exp','demoDist','category','atkType',
           't_melee','t_weapon','t_missile','t_bullet','t_optical','t_bit','t_explosive','t_defense','weaponId','unk19']

def cs(b, p, enc='cp932'):
    e = b.index(b'\0', p); return b[p:e].decode(enc, 'replace'), e + 1

def parse_mek(b):
    seq = struct.unpack_from('<6i', b, 0)
    p = seq[0]
    name, p = cs(b, p); ruby, p = cs(b, p); pilot, p = cs(b, p); pruby, p = cs(b, p); desc, p = cs(b, p)
    vals = struct.unpack_from('<22i', b, p)
    info = dict(name=name, ruby=ruby, pilot=pilot, desc=desc, **dict(zip(BASIC, vals)))
    # weapon block
    p = seq[2]; n, = struct.unpack_from('<i', b, p); p += 4
    weapons = []
    for i in range(n):
        f, = struct.unpack_from('<i', b, p); p += 4
        if f != 1: weapons.append(None); continue
        wn, p = cs(b, p); wc, p = cs(b, p); wd, p = cs(b, p)
        v = struct.unpack_from('<19i', b, p); p += 76
        weapons.append(dict(idx=i, name=wn, code=wc, desc=wd, **dict(zip(WFIELDS, v))))
    info['weapons'] = weapons
    info['seq'] = seq
    return info

if __name__ == '__main__':
    d = sys.argv[1]
    showw = '--weapons' in sys.argv
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.mek'): continue
        m = parse_mek(open(os.path.join(d, fn), 'rb').read())
        ws = [w for w in m['weapons'] if w]
        print('%-14s %-22s pilot=%-10s waz=%3d spm=%3d type=%2d nWeap=%d(exp>0:%d)' % (
            fn[:-4], m['name'], m['pilot'], m['waz'], m['spm'], m['type'], len(m['weapons']),
            sum(1 for w in ws if w['exp'] > 0)))
        if showw:
            for w in m['weapons']:
                if w is None: print('    <none>'); continue
                print('    [%2d] %-20s %-12s waz=%d exp=%d cat=%d type=%d id=%d sw=%d' % (
                    w['idx'], w['name'], w['code'], w['wazSeq'], w['exp'], w['category'], w['atkType'], w['weaponId'], w['switchToMek']))
