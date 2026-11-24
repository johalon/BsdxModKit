#!/usr/bin/env python3
"""attack_count_check.py - count, for every converted TOORU technique (and every converted bullet), the attack events of
the BFE original and of the DiveX output, and list the differences (R 2026-11-03, 調査記録 25).

  BFE side (work/bfe_waz/TOORU_named.json / Tama_named.json): the phase flow of BaldrForce.exe
    * next phase = go_end / go_anim_end when set (-1 = next alg position), else the next ALG POSITION with the loop table
      (0x443491: per-loop counters at obj+0x1d+i, start/end = alg positions, count = total passes, counter reset on exit)
    * "hit" assumption: a phase with a mech hit connects -> go_hit_mech is taken (when set); go_hits_le_mech not taken
    * other conditions (go_land, go_dist_in, go_air, go_obstacle, go_mech_*, go_origin_null, go_counter) not taken, noted
    * per visited phase: hits = HIT数 (power > 0, 1..253; 255 = unlimited 'U'; mech: only with attack rects),
      shots = fire bursts: anim_type 4 -> all loops; else min(loops, 1 + (phase ticks - 1 - fire tick) // (interval+1))
      (0x44a1c0: timer = interval after a shot, tested before the decrement -> one shot per interval+1 ticks)
  DiveX side (work/tooru_port/check/waz/*.json, this build): a frame interpreter of slot 71 changes in list order
    (無条件, 汎用カウンタ ≤/超過 with slot 35 set/add, 残りメカＨＩＴ数→0 = all hits of an open window delivered,
    NOT flag; any other condition = false and noted), counting slot 41 hitCount of hit objects whose window opens, and
    fire bursts = distinct start frames of slot 48 spawns into the bullet / laser files (4 / 6).
  Mech techniques run with every hit connecting (go_hit_mech / 残りメカＨＩＴ数 taken once the hits are delivered),
  bullets run without hitting (go_hit_mech / 残りメカＨＩＴ数 not taken): the flight as fired.
Usage: python3 tools/attack_count_check.py [--dx DIR] [--out FILE]
"""
import sys, os, json, collections, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bfe2bsdx_waz import TermText, Converter

P = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')
W = P + '/work/tooru_port'
from bfe2bsdx_common import BULLET_FILE, LASER_FILE
BULLET_FILES = (BULLET_FILE, LASER_FILE)


class _Rep:
    def add(self, *a): pass


def bfe_phase_ticks(conv, ph):
    """(ticks, fire tick or None, anim_type 4 present) of one BFE phase (exe timing via Converter.ev_timing, frames / 2)"""
    t = 0; fire = None; t4 = False
    for e in ph['events']:
        n, _ = conv.ev_timing(e, ph)
        if e['flags'] & 8 and fire is None:
            fire = t // 2
        if e['anim_type'] == 4:
            t4 = True
        t += n
    return max(1, t // 2), fire, t4


def bfe_count(skill, conv, bullet, hit_mode=True, maxsteps=2000):
    h = skill['header']; phases = skill['phases']; nph = len(phases)
    alg = [a for a in h['alg_list'] if a != 99 and 0 <= a < nph] or [0]
    loops = [dict(l) for l in h['loops'] if l['end'] != 99 and l['count'] > 0]
    cnt = [0] * len(loops)
    notes = set(); hits = 0; unl = False; shots = 0; pellets = 0; seq = []
    pos = 0; steps = 0
    while steps < maxsteps:
        steps += 1
        p = alg[pos] if pos < len(alg) else None
        if p is None:
            break
        ph = phases[p]; seq.append(p)
        hi = ph['hit']
        rects = any(e['attack_rects'] for e in ph['events'])
        has_hit = hi['power'] > 0 and hi['hits_mech'] not in (0, 254) and (bullet or rects)
        if has_hit:
            if hi['hits_mech'] >= 255:
                unl = True
            else:
                hits += hi['hits_mech']
        ticks, ft, t4 = bfe_phase_ticks(conv, ph)
        f = ph['fire']
        if f['tama'] >= 0 and ft is not None:
            iv = max(0, f['interval'][0])
            n = max(1, f['loops']) if t4 else max(1, min(max(1, f['loops']), 1 + (ticks - 1 - ft) // (iv + 1)))
            shots += n; pellets += n * max(1, f['count'][0])
        for k in ('go_land', 'go_dist_in', 'go_air', 'go_obstacle', 'go_mech_alg', 'go_mech_spr', 'go_mech_skill',
                  'go_origin_null', 'go_counter', 'go_hit_weapon', 'go_dist_out', 'go_hits_le_weapon'):
            if ph.get(k, -99) != -99:
                notes.add(k)
        if ph.get('go_hits_le_mech', -99) != -99:
            notes.add('go_hits_le_mech')
        # next phase
        g = None
        if ph['go_hit_mech'] != -99 and has_hit:
            notes.add('go_hit_mech')
        if hit_mode and has_hit and ph['go_hit_mech'] != -99:
            g = ph['go_hit_mech']
        elif ph['go_end'] != -99:
            g = ph['go_end']
        elif ph['go_anim_end'] != -99:
            g = ph['go_anim_end']
        if g is not None and g != -1:
            if g == 99 or not (0 <= g < nph):
                break
            pos = alg.index(g) if g in alg else None
            if pos is None:
                notes.add('jump outside alg'); break
            continue
        # 0x443491: loops on the current alg position, then +1
        nxt = None
        for i, l in enumerate(loops):
            if pos == l['end']:
                cnt[i] += 1
                if cnt[i] < l['count']:
                    nxt = l['start']; break
                cnt[i] = 0
        pos = nxt if nxt is not None else pos + 1
    if steps >= maxsteps:
        notes.add('step cap')
    return dict(hits=hits, unl=unl, shots=shots, pellets=pellets, notes=sorted(notes), seq=seq)


def units(turn):
    d = collections.defaultdict(list)
    for u in turn['skillUnitCollection']:
        d[u['unitQuantity']] += u['skillInfoObjectList']
    return d


def effect_target(o):
    for u in o.get('ceventEffectUnitList') or []:
        if u['unitSlotNum'] == 3 and u.get('data') and 'wazFileNo' in u['data']:
            return (u['data']['wazFileNo'], u['data']['wazSequenceNo'])
    return None


def dx_count(skill, tt, hit_mode=True, maxframes=20000):
    turns = skill['phasesInfo']; nt = len(turns)
    U = [units(t) for t in turns]
    notes = set(); hits = 0; unl = False; bursts = 0; pellets = 0; seq = []
    counter = 0
    t = 0; frames = 0
    while 0 <= t < nt and frames < maxframes:
        u = U[t]; seq.append(t)
        ch = [o for o in u[71] if o['typeId'] == 34]
        hitobjs = u[41]
        lastf = max([o['endFrame'] for o in ch] + [0])
        jump = None; f = 0
        while f <= lastf + 1 and frames < maxframes:
            for o in u[35]:
                if o['startFrame'] == f:
                    counter = (counter + o['int4']) if o['int3'] == 1 else o['int4']
            for o in ch:
                if not (o['startFrame'] <= f <= o['endFrame']):
                    continue
                ok = True
                for b in o['bsdxInfoCollectionList1']:
                    s = tt.text(b); v = b['paramList'][0] if b['paramList'] else 0
                    if '無条件' in s:
                        r = True
                    elif '汎用カウンタ' in s and '以下' in s:
                        r = counter <= v
                    elif '汎用カウンタ' in s and '超過' in s:
                        r = counter > v
                    elif '汎用カウンタ' in s and '以上' in s:
                        r = counter >= v
                    elif '残りメカＨＩＴ数' in s:
                        r = False
                        if not hit_mode:
                            notes.add('hit->'); hitobjs_ = ()
                        else:
                            hitobjs_ = hitobjs
                        for hb in hitobjs_:
                            n = hb.get('hitCount', 1)
                            if n is None or n < 0:
                                continue
                            iv = hb.get('hitInterval') or 0
                            if hb['startFrame'] + max(0, n - 1) * iv <= f:
                                r = True
                    else:
                        r = False; notes.add(s.split('→')[-1][:18])
                    if b.get('int2'):
                        r = not r
                    if not r:
                        ok = False; break
                if ok:
                    j = o['bsdxInfoCollectionList2'][0]; js = tt.text(j)
                    if '終了' in js:
                        jump = 'end'
                    elif '１つ先' in js:
                        jump = t + 1
                    else:
                        jump = j['paramList'][0]
                    break
            if jump is not None:
                break
            f += 1; frames += 1
        ran = f + 1     # frames executed in this turn (0..f)
        for hb in hitobjs:
            if hb['startFrame'] < ran:
                n = hb.get('hitCount', 1)
                if n is None or n < 0:
                    unl = True
                else:
                    hits += n
        fr = set()
        for o in u[48]:
            tg = effect_target(o)
            if tg and tg[0] in BULLET_FILES and o['startFrame'] < ran:
                fr.add(o['startFrame'])
                c = 1
                for x in o['ceventEffectUnitList']:
                    if x['unitSlotNum'] == 4 and x.get('data'):
                        c = max(1, x['data'].get('int5') or 1)
                pellets += c
        bursts += len(fr)
        if jump is None or jump == 'end':
            break
        t = jump
    if frames >= maxframes:
        notes.add('frame cap')
    return dict(hits=hits, unl=unl, shots=bursts, pellets=pellets, notes=sorted(notes), seq=seq)


def fmt(c):
    return '%d%s' % (c['hits'], '+U' if c['unl'] else '')


def run(dxdir):
    term = json.load(open(W + '/json/Term.grp.json'))['termList']
    tt = TermText(term)
    spr = json.load(open(P + '/work/bfe_spr/tooru.json'))
    bw = json.load(open(P + '/work/bfe_waz/TOORU_named.json'))
    tama = json.load(open(P + '/work/bfe_waz/Tama_named.json'))
    weapons = json.load(open(W + '/weapons.json'))
    tw = json.load(open(dxdir + '/Tooru.waz.json'))['skillList']
    t4 = json.load(open(dxdir + '/Tama04.waz.json'))['skillList']
    conv = Converter(None, spr['anims'], None, _Rep(), None, mode='mech')
    import bfe2bsdx_effspr
    effspr = bfe2bsdx_effspr.parse(P + '/work/bfe_effect/Effect.spr')
    rows = []
    for w in weapons:
        if w.get('bfe') is None or w.get('waz') is None:
            continue
        b = bfe_count(bw[w['bfe']], conv, False)
        d = dx_count(tw[w['waz']], tt)
        rows.append(('mech', w['name'], w['bfe'], w['waz'], b, d))
    bconv = Converter(None, effspr['anims'], None, _Rep(), None, mode='bullet') if effspr else None
    if bconv:
        for i, s in enumerate(t4):
            if not s or not str(s.get('skillNameEnglish', '')).startswith('BFE_TAMA'):
                continue
            ti = int(s['skillNameEnglish'][8:11])
            b = bfe_count(tama[ti], bconv, True, hit_mode=False)
            d = dx_count(s, tt, hit_mode=False)
            rows.append(('bullet', s['skillNameJapanese'], ti, i, b, d))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dx', default=W + '/check/waz')
    ap.add_argument('--out')
    a = ap.parse_args()
    rows = run(a.dx)
    L = ['# attack count check (BFE vs DiveX output %s)' % a.dx, '',
         '| 種別 | 名前 | BFE | DX | BFE ヒット | DX ヒット | BFE 発射 | DX 発射 | BFE 弾数 | DX 弾数 | 注記 |', '|' + '---|' * 11]
    nd = 0
    for kind, name, bi, di, b, d in rows:
        diff = (b['hits'], b['unl'], b['shots']) != (d['hits'], d['unl'], d['shots'])
        if not diff:
            continue
        nd += 1
        L.append('| %s | %s | %s | %s | %s | %s | %d | %d | %d | %d | %s |' % (
            kind, name, bi, di, fmt(b), fmt(d), b['shots'], d['shots'], b['pellets'], d['pellets'],
            ', '.join(['BFE:' + x for x in b['notes']] + ['DX:' + x for x in d['notes']])))
    L += ['', 'rows %d, differing %d' % (len(rows), nd)]
    txt = '\n'.join(L) + '\n'
    if a.out:
        open(a.out, 'w').write(txt)
    print(txt)
    # full table as JSON for later diffs
    json.dump([dict(kind=k, name=n, bfe=bi, dx=di, b=b, d=d) for k, n, bi, di, b, d in rows],
              open((a.out or '/dev/null') + '.json' if a.out else os.devnull, 'w'), ensure_ascii=False, indent=0)


if __name__ == '__main__':
    main()
