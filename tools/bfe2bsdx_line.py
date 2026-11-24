#!/usr/bin/env python3
"""bfe2bsdx_line.py - BALDR FORCE EXE lasers / wires (segment chains) -> BALDR SKY DiveX line objects (Laser.waz
ライン親 / ライン子 / 先端), with the BFE sprites, segment count, growth rate, zoom, hits and SE.
Used by bfe2bsdx_tama.Fx.line_chain() (called from bfe2bsdx_waz.Converter for fire_type 1/2 and laser roots).

Both engines build these weapons the same way (調査記録 09 §10):
  BFE  : root Tama fires segment Tamas (fire_type 1 straight / 2 うねうね). A segment's origin (lock1) is target type 6 =
         the PREVIOUS segment (obj+0xC, exe 0x4407fc), attached at its judge slot 9 (Effect.spr rect index 8, a 1-px point
         at the far end of the vertical segment image); `loops` = max segments, `count` = segments added per tick
         (exe 0x4498b0: n = min(loops - alive, count_now, ...)); flags2 bit3 = retract (kill `count` segments per tick).
  BSDX : ライン親 spawns ライン子 (CEventEffect 同時 = per frame, 最大 = max), a child's position is OBJECTPOS 16
         "レーザー割り当てられた位置" = the previous child in the parent's list (exe 0x66572a -> 0x614bc0/0x614ea0) with
         OBJECTPOS2 18 "連結位置（高さなし）" = spm hitFlag bit 5 (Link.spm: 1-px point at the end of each vertical segment,
         e.g. anim 12 鞭 (0,15)-(1,16) == BFE Effect.spr anim 28 slot 9 (0,15)-(1,16)); 先端 = OBJECTPOS 18 "最後尾".
So the conversion keeps the BSDX template chain of the same-named 甲 weapon (the BSDX re-creation of these BFE weapons:
same parts, same turn structure) and replaces its data with the BFE values:
  child  : sprite = BFE segment anim of tooru_eft.spm (bfe2bsdx_eft maps rect slot 8 -> hitFlag bit 5 LINK, slot 2 ->
           bit 0 hit box), BFE zoom (type 1) -> slot 2 + 3 (X/Y; Y also scales the link distance like BFE 0x414a10 does
           [guess for BSDX, cf. ガリアンソード's growing child]), 甲 sprite attribute (slot 7) and 甲 joint effects dropped
  parent : 最大 = BFE segments (+1 for the first segment drawn by the root / ﾗｲﾝ１本目), 同時 = ceil(BFE count/tick / 2),
           hits (slot 41/42) = BFE segment hit (power /4, hit counts, hit SE, hit effect), per BFE phase = turn
  root   : sprite = BFE root anim, SE = BFE root SE
  tip    : sprite = BFE tip anim per turn, hits = BFE tip phases (removed where BFE's tip does not hit), 甲 effects /
           explosions -> the BFE tip phase's own fire (converted bullet) or the BFE explosion phase as a bullet
Kept from the template (no BFE counterpart / unknown units): turn timing, wave amplitude/period (slot 57/58), the
child direction mode (straight / うねうね / ぶんぶん), のけぞり details.
"""
import copy, math, collections
from bfe2bsdx_waz import walk, effect_target, set_effect_target, effect_sub

EXTRA_TIP, EXTRA_TIP_PARENT = 46, 42     # Laser「甲レーザー（先端）」 (at LASER_LAST + LINK) and the parent that spawns it
ROLE_KEYS = (('根元', 'root'), ('ライン親', 'parent'), ('（親）', 'parent'), ('ライン子', 'child'), ('先端', 'tip'))


def role_of(name):
    for k, r in ROLE_KEYS:
        if k in name:
            return r
    return None


def turn_len(ph):
    return max([o['endFrame'] for u in ph['skillUnitCollection'] for o in u['skillInfoObjectList']] + [1]) + 1


def units(ph):
    return {u['unitQuantity']: u for u in ph['skillUnitCollection']}


def drop_slots(ph, slots):
    ph['skillUnitCollection'] = [u for u in ph['skillUnitCollection'] if u['unitQuantity'] not in slots]


def put_slot(ph, slot, objs, lib):
    ph['skillUnitCollection'] = [u for u in ph['skillUnitCollection'] if u['unitQuantity'] != slot]
    if objs:
        for o in objs:
            o['slotNum'] = slot
        ph['skillUnitCollection'].append({'unitQuantity': slot, 'unitDescription': lib.desc[slot],
                                          'skillInfoObjectList': sorted(objs, key=lambda o: o['startFrame']), 'skillInfoUnknownList': []})
        ph['skillUnitCollection'].sort(key=lambda u: u['unitQuantity'])


class LineBuilder:
    def __init__(self, fx):
        self.fx = fx; self.T = fx.tama; self.lib = fx.lib; self.conv = fx.conv; self.rep = fx.rep
        self.cache = {}
        self.pierce = {}            # chain top (file, idx) -> True (pierce) / False (stops at the first hit segment)
        hb = [o for ph in fx.tpl_bullet['phasesInfo'] for u in ph['skillUnitCollection'] if u['unitQuantity'] == 41
              for o in u['skillInfoObjectList']]
        self.hit_sample = hb[0]

    # ------------------------------------------------------------------ BFE side
    def name(self, ti):
        return self.T[ti]['header']['name']

    def describe(self, root, mech_tip=None):
        """BFE chain: root Tama -> {root, line, first, fire (segment fire block), count, tip}"""
        T = self.T
        lf = [(ph['fire'], pi) for pi, ph in enumerate(T[root]['phases']) if ph['fire']['tama'] >= 0 and ph['fire']['fire_type'] != 0]
        d = dict(root=root, first=None, tip=None, retract=False)
        if not lf:
            raise ValueError('no laser fire in Tama %d' % root)
        f1 = lf[0][0]; l1 = f1['tama']
        lf2 = [ph['fire'] for ph in T[l1]['phases'] if ph['fire']['tama'] >= 0 and ph['fire']['fire_type'] != 0]
        if lf2:                                   # ﾗｲﾝ１本目 fires the rest
            d.update(first=l1, line=lf2[0]['tama'], fire=lf2[0])
        else:
            d.update(line=l1, fire=f1)
            if self._anim(root) == self._anim(l1):
                d['first'] = root                  # wire root draws the first segment at the hand
        rf = [x[0] for x in lf if x[0]['flags2'] & 8]
        d['retract'] = bool(rf); d['retract_frames'] = None; d['retract_count'] = None
        if rf:                      # exe 0x449a7e: kill count_now segments per tick, count_now -> final by step/256
            c0, c1, st = rf[0]['count']; cur = float(max(1, c0)); left = None; ticks = 0
            d['retract_count'] = rf[0]['count']
        tips = [ph['fire']['tama'] for ph in T[root]['phases'] if ph['fire']['tama'] >= 0 and ph['fire']['fire_type'] == 0
                and '先端' in self.name(ph['fire']['tama'])]
        d['tip'] = tips[0] if tips else mech_tip
        d['segments'] = max(1, d['fire']['loops']) + (1 if d['first'] is not None else 0)
        if rf:
            left = d['segments']
            while left > 0 and ticks < 200:
                left -= int(cur); ticks += 1
                cur = min(c1, cur + st / 256.0) if st > 0 else max(c1, cur + st / 256.0)
            d['retract_frames'] = ticks * 2
        d['per_frame'] = max(1, int(math.ceil(max(1, d['fire']['count'][0]) / 2.0)))
        return d

    def _anim(self, ti, pi=None):
        phs = self.T[ti]['phases'] if pi is None else [self.T[ti]['phases'][min(pi, len(self.T[ti]['phases']) - 1)]]
        for ph in phs:
            for e in ph['events']:
                if e['anim'] >= 0 and e['anim'] < len(self.fx.eff['anims']) and self.fx.eff['anims'][e['anim']]:
                    return e['anim']
        return None

    def _zoom(self, ti):
        for ph in self.T[ti]['phases']:
            for e in ph['events']:
                if e['zoom']['type'] == 1 and e['zoom']['init'][0] not in (-32768, 256):
                    return e['zoom']['init'][0]
        return None

    def _se(self, ti):
        for ph in self.T[ti]['phases']:
            for e in ph['events']:
                if e['se_play'] >= 0:
                    s = self.fx.se.get(e['se_play'])
                    if s:
                        return s
        return None

    # ------------------------------------------------------------------ pierce / stop at the target (PIERCE)
    def stops_at_hit(self, d):
        """BFE: a segment phase with go_hit_mech = 99 ends when it hits a mech (ﾗｲﾝﾚｰｻﾞｰ Tama 85/93); the root re-fires up
        to `loops` live segments every tick (exe 0x4498b0: n = min(loops - alive, count, ...)), so the beam ends at the
        enemy and re-grows when it moves. Segments without it (wires 63/68/75, ｳﾈｳﾈ 105) pass through mechs.
        M 2026-10-31 (user 10/29: 「ワイヤー系 2 種は敵で止まるのを優先」): a chain the root pulls back (fire flags2 bit 3,
        引き戻し, exe 0x4498b0 / 0x449a7e: ｸｫｳﾄﾜｲﾔｰ 60-62 ph1, ﾓｰﾆﾝｸﾞｽﾀｰ 72-74 ph1) is a throw-and-reel-in wire -> stops at
        the first target too (vanilla: the reel-in line parents 引き寄せ鞭 / モーニングスター / 甲の腕 / 雅ワッパ = bit 1 clear).
        go_hit_weapon is NOT the criterion: ｽｳｨﾝｸﾞﾜｲﾔｰ 68 and ｳﾈｳﾈ 105 have it too and stay piercing (vanilla bit 1 set),
        and ﾓｰﾆﾝｸﾞｽﾀｰ 75 lacks it.
        2026-11-02 user: 「クォウトワイヤーとモーニングスターは敵を貫通のほうが良かった。弾も貫通して良い」 -> the pulled-back
        clause above is withdrawn; back to the BFE segment rule alone (go_hit_mech 99). Wires pierce mechs and bullets."""
        return any(ph.get('go_hit_mech') == 99 for ph in self.T[d['line']]['phases'])

    def _pierce_hdr(self, o, pierce, what):
        """BSDX: the spawn that creates the ライン親 (CEventEffect int2 エフェクトタイプ2 = 1 -> CLaser, exe 0x64524c/0x645f87)
        copies its フラグ (int3, member +0xc4, writer 0x6394f0) bit 1 into CLaser+0x1860 (ctor 0x615651). Every frame the
        CLaser method vtbl+0xf4 = 0x614ff0 (called from the effect loop 0x5e12f2) walks the children in order: with +0x1860
        == 0 the first child that hits a bullet (slot 42, 0x648b10) or a mech (slot 41, 0x648330/0x649070) and all later
        children are destroyed (vtbl+0x2c), the parent re-spawns them (同時/F) -> the line ends at the target. With bit 1
        it only judges (no cut). Vanilla: bit 1 on 甲レーザー/荷電粒子砲/パルス/火炎放射/スィングワイヤー (41 spawns),
        clear on 甲レーザービット/アキ ラインレーザー/アイビーム/クォウトワイヤー/モーニングスター (372)."""
        if o.get('int2') != 1:
            return False
        old = o.get('int3', 0)
        o['int3'] = (old | 2) if pierce else (old & ~2)
        self.rep.add('PIERCE', '%s: line parent spawn flag int3 %d -> %d (%s; BFE segment %s)' % (
            what, old, o['int3'], 'pierce' if pierce else 'stops at the first hit segment',
            'go_hit_mech 99 / pulled back' if not pierce else 'passes mechs'))
        return True

    def set_pierce(self, o, tgt):
        """external spawn of a chain whose top is the ライン親 (wires, laser bit): apply the chain's PIERCE flag"""
        if tgt in self.pierce:
            self._pierce_hdr(o, self.pierce[tgt], 'spawn -> Laser[%d]' % tgt[1])

    # ------------------------------------------------------------------ template closure (Laser file)
    def closure(self, top):
        LF = self.fx.LF; SH = self.fx.SH[LF]['skillList']
        order, seen, stack = [], set(), [top]
        while stack:
            i = stack.pop(0)
            if i in seen:
                continue
            seen.add(i); order.append(i)
            for o in walk(SH[i]):
                if 'wazFileNo' in o and o['wazFileNo'] == LF:
                    stack.append(o['wazSequenceNo'])
        return order

    # ------------------------------------------------------------------ build
    def build(self, label, root, proj, mech_tip=None, life=None):
        """root: BFE root Tama; proj: template spawn event whose target is the template chain top (Laser file).
        -> (file, idx) of the new chain top"""
        label = label.split('（')[0]
        key = (root, effect_target(proj), mech_tip, life)
        if key in self.cache:
            return self.cache[key]
        fx = self.fx; LF = fx.LF; SH = fx.SH[LF]['skillList']
        top = effect_target(proj)
        if not top or top[0] != LF:
            return None
        d = self.describe(root, mech_tip)
        cl = self.closure(top[1])
        roles = {i: role_of(SH[i]['skillNameJapanese']) for i in cl}
        if roles[top[1]] is None:
            roles[top[1]] = 'parent'
        notes = []
        extra_tip = None
        if 'tip' not in roles.values() and d['tip'] is not None:      # BFE has a tip the 甲 chain lacks (ｳﾈｳﾈﾚｰｻﾞｰ)
            extra_tip = EXTRA_TIP; cl.append(EXTRA_TIP); roles[EXTRA_TIP] = 'tip'
            notes.append('先端: BFE tip Tama %d added (甲 template has none; tip object cloned from Laser[%d]「%s」)'
                         % (d['tip'], EXTRA_TIP, SH[EXTRA_TIP]['skillNameJapanese']))
        newidx = {i: fx._alloc(LF) for i in cl}
        pierce = not self.stops_at_hit(d)
        for i in cl:
            s = copy.deepcopy(SH[i]); base = s['skillNameJapanese']
            r = roles[i]
            s['skillNameJapanese'] = '%s：%s（%s）' % (label, {'root': '根元', 'parent': 'ライン親', 'child': 'ライン子', 'tip': '先端'}.get(r, base), fx.label)
            s['skillNameEnglish'] = 'BFE_LINE%03d_%s' % (root, (r or 'x').upper())
            for o in walk(s):                     # internal refs -> the new copies
                if 'wazFileNo' in o and o['wazFileNo'] == LF and o['wazSequenceNo'] in newidx:
                    o['wazSequenceNo'] = newidx[o['wazSequenceNo']]
                if 'offset' in o:
                    o['offset'] = 0
            if extra_tip is not None and r == 'parent':
                self._add_tip_spawn(s, newidx[extra_tip])
            getattr(self, '_' + (r or 'other'))(s, d, newidx, notes)
            for o in walk(s):                     # root -> ライン親 spawn inside the chain (CLaser creation): PIERCE
                if 'ceventEffectUnitList' in o and (effect_target(o) or (None,))[0] == LF and \
                        effect_target(o)[1] in newidx.values():
                    self._pierce_hdr(o, pierce, '%s %s' % (label, r))
            if life and r == 'root':
                # BFE roots end on 「メカスプライト変化」 (go_mech_spr): when the firing mech leaves the sprite event that
                # fired them (ﾊﾟﾙｽﾚｰｻﾞｰ: end of the 30-tick event, not of the whole move). DiveX 親状態 only sees turn
                # changes -> end the root after the firing event's length (the chain ends with it: parent NULLなら)
                ph0 = s['phasesInfo'][0]; u71 = units(ph0).get(71)
                objs = list(u71['skillInfoObjectList']) if u71 else []
                objs.insert(0, self.lib.change([], 'end', life - 1, life - 1))
                put_slot(ph0, 71, objs, self.lib)
                notes.append('根元: ends %dF after firing (BFE go_mech_spr = end of the firing sprite event)' % life)
            fx.appended[LF][newidx[i] - len(SH)] = s
            self.rep.add('LINEMAP', '%s: Laser[%d]「%s」 -> %s[%d] (%s)' % (label, i, base, fx.names[LF], newidx[i], r))
        msg = ('%s: BFE Tama %d (%s) -> BSDX line chain (甲 template Laser[%d]) with BFE visuals: segment anim %s x%d (+%d/F), '
               'tip %s, hits from BFE' % (label, root, self.name(root), top[1], self._anim(d['line']), d['segments'],
                                          d['per_frame'], ('Tama %d' % d['tip']) if d['tip'] is not None else 'template tip timing'))
        self.rep.add('LINE', msg)
        for n in notes:
            self.rep.add('LINE', '%s: %s' % (label, n))
        self.cache[key] = (LF, newidx[top[1]])
        self.pierce[self.cache[key]] = pierce
        return self.cache[key]

    def _put_zoom(self, ph, z, uniform=False):
        if not z:
            return
        if uniform:
            put_slot(ph, 1, [self.lib.obj(1, 2, 0, 0, int1=0, int2=z, int4=0, int5=z)], self.lib)
        else:       # segments: X (thickness) + Y (length; the link point follows it)
            put_slot(ph, 2, [self.lib.obj(2, 2, 0, 0, int1=0, int2=z, int4=0, int5=z)], self.lib)
            put_slot(ph, 3, [self.lib.obj(3, 2, 0, 0, int1=0, int2=z, int4=0, int5=z)], self.lib)

    def _add_tip_spawn(self, s, tip_idx):
        LF = self.fx.LF
        src = [o for o in walk(self.fx.SH[LF]['skillList'][EXTRA_TIP_PARENT]) if 'ceventEffectUnitList' in o
               and effect_target(o) == (LF, EXTRA_TIP)][0]
        o = copy.deepcopy(src); set_effect_target(o, (LF, tip_idx)); o['startFrame'] = o['endFrame'] = 0
        for x in walk(o):
            if 'offset' in x:
                x['offset'] = 0
        ph = s['phasesInfo'][0]
        old = list(units(ph)[48]['skillInfoObjectList']) if 48 in units(ph) else []
        put_slot(ph, 48, old + [o], self.lib)

    # ---------------- roles
    def _sprite_events(self, a, L, loop=True):
        if a is None:
            return []
        return [self.conv.sprite(a, p, s0, s1) for (p, s0, s1) in self.conv.patterns(a, L, loop and len(self.fx.eff['anims'][a]) > 1)] \
            if len(self.fx.eff['anims'][a]) > 1 else [self.conv.sprite(a, 0, 0, 0)]

    def _phase_sprites(self, bph, L):
        """a BFE phase's sprite events in order (lengths as in the bullet converter); the last one loops to the turn end"""
        evs = [e for e in bph['events'] if 0 <= e['anim'] < len(self.fx.eff['anims']) and self.fx.eff['anims'][e['anim']]]
        out, t = [], 0
        for k, e in enumerate(evs):
            last = k == len(evs) - 1
            n = (L - t) if last else min(L - t, self.conv.ev_len(e, bph))
            if n <= 0:
                break
            if len(self.fx.eff['anims'][e['anim']]) == 1:
                out.append(self.conv.sprite(e['anim'], 0, t, t if last else t + n - 1))
            else:
                out += [self.conv.sprite(e['anim'], p, t + s0, t + s1) for (p, s0, s1) in self.conv.patterns(e['anim'], n, True)]
            t += n
        return out

    def _strip_foreign_spawns(self, ph, keep_files=None):
        LF = self.fx.LF
        u = units(ph).get(48)
        if not u:
            return 0
        keep = [o for o in u['skillInfoObjectList'] if (effect_target(o) or (LF,))[0] == LF]
        n = len(u['skillInfoObjectList']) - len(keep)
        put_slot(ph, 48, keep, self.lib)
        return n

    def _set_se(self, ph, se, at=0):
        if se:
            put_slot(ph, 52, [self.conv.se_obj(se, at)], self.lib)
        else:
            drop_slots(ph, (52,))

    def _hits(self, ph, bph, L, notes, what, add_if_missing=True, segments=1, ti=None):
        """BFE phase hit -> slot 41 (mech) / 42 (bullets) of a template turn.
        segments > 1 (ライン親): in BFE every segment is its own object with HIT数 hits, in DiveX one hit object judges the
        whole line -> hit count = HIT数 x segments, re-hit interval kept from the vanilla line (甲レーザー: -1 / 10F)"""
        hi = bph['hit']; hm, hw = hi['hits_mech'], hi['hits_weapon']
        valid = hm not in (0, 254) and hi['power'] > 0
        u = units(ph)
        objs = list(u[41]['skillInfoObjectList']) if 41 in u else []
        if not valid:
            if objs:
                drop_slots(ph, (41,)); notes.append('%s: 甲 hit removed (BFE does not hit mechs here)' % what)
        else:
            live = [o for o in objs if self._power(o) != 0]
            # T 2026-11-11 (TPLHIT0, user 「スウィングワイヤーが甲のように外へ弾く」 / 「BFE から変換できない値だけテンプレに」):
            # a 威力 0 template hit is a 甲-only push (甲 スィングワイヤーLv3 Laser[95] F21-152: のけぞり 10/30 toward
            # オブジェクト位置 = flings the victim outward along the wire; パルスレーザー根元 Laser[23]: 20/200 forward). The
            # power filter above left it unconverted -> when BFE hits here, every template hit object is replaced by the
            # BFE hit (BFE has one hit definition per phase); none of them survives as a 甲 push.
            dead = [o for o in objs if self._power(o) == 0]
            if dead:
                objs = [o for o in objs if self._power(o) != 0]
                notes.append('%s: %d 甲 威力 0 hit(s) removed (template-only push; BFE hit replaces them)' % (what, len(dead)))
                self.rep.add('TPLHIT0', '%s: %d 甲 威力 0 hit(s) F%s removed' % (
                    what, len(dead), ','.join('%d-%d' % (o['startFrame'], o['endFrame']) for o in dead)))
            # T 2026-11-11 (LINEWIN): BFE line objects judge on every tick of their life (TAMA events 999 ticks, the hit
            # window = the object's life), the template's windows are 甲's timing (スィングワイヤー F0-20 then the push).
            # -> one hit object over the whole turn (the first live one), the other live ones dropped.
            if live:
                w0 = (live[0]['startFrame'], live[0]['endFrame'])
                if len(live) > 1 or w0 != (0, L - 1):
                    for o in live[1:]:
                        objs.remove(o)
                    live = live[:1]
                    live[0]['startFrame'], live[0]['endFrame'] = 0, L - 1
                    self.rep.add('LINEWIN', '%s: hit window F%d-%d -> F0-%d (BFE judges for the whole life)%s' % (
                        what, w0[0], w0[1], L - 1, '' if len(objs) == 1 else ''))
            if not live and add_if_missing:
                o = copy.deepcopy(self.hit_sample); o['startFrame'], o['endFrame'] = 0, L - 1
                objs.append(o); live = [o]; notes.append('%s: hit added (BFE hits here, 甲 template does not)' % what)
            for o in live:
                s, e = o['startFrame'], o['endFrame']
                iv0 = o.get('hitInterval') or 0
                self.conv._set_hit(o, hi, bph['noke_mech'], s, e, hm, cancel=self.fx.hit_cancel(ti), src_ti=ti)   # HITCANCEL (調査記録 20); src_ti: N COMBOCLS
                if segments > 1 and hm < 255 and bph.get('go_hit_mech') == 99:
                    # L 2026-11-01 (PIERCE, 「照射の終わりだけ貫通」): a segment that dies on a mech hit is re-fired by the
                    # root without limit (BFE 0x4498b0), so the beam has no per-target hit cap. DiveX drops a target whose
                    # hit record reached hitCount from the judge (0x64858a) and CLaser 0x614ff0 then no longer cuts the
                    # line there -> the old cap hm x segments (Lv3 11 x 10F) ran out ~104F into the 120F beam and the
                    # beam pierced. Vanilla stopping beams are all unlimited (シルファ / 甲レーザービット / アイビーム /
                    # 勲・ノイレーザー / 甲サンダーボルト / 甲の腕 = -1 with interval) -> -1, interval kept.
                    o['hitCount'] = -1
                    o['hitInterval'] = iv0 if iv0 > 0 else 6
                    self.rep.add('PIERCE', '%s: hit count -1 (was %d x %d segments), interval %dF (BFE segment ends on hit and is '
                                 're-fired: no per-target cap; a DiveX cap stops the cut, 0x64858a)' % (
                                     what, hm, segments, o['hitInterval']))
                elif hm >= 255 and hi['flags'] & 0x10:
                    # T 2026-11-11 (LINEIV, user 「スウィングワイヤーのヒット数がすごく高い」): the template's re-hit interval
                    # (甲 スィングワイヤーLv3 Laser[95] F0-20: 1F) stayed on the BFE hit, and LINEWIN stretched that window to
                    # F0-152 -> a 30-power hit every frame. BFE: after a mech hit the object waits HIT規模 ticks
                    # (0x441482-0x441497, 1 hit per HIT規模+1 ticks = 2*(HIT規模+1) F, the bullet HITIV rule), and flag 0x10
                    # HIT規模を全弾更新 (0x4497e5) copies the wait to every sibling -> the whole line hits once per wait, the
                    # same as DiveX's single line hit object. ｽｳｨﾝｸﾞﾜｲﾔｰ：ﾗｲﾝ HIT規模 2 -> 6F, ｸｫｳﾄﾜｲﾔｰ：ﾗｲﾝ 3 -> 8F.
                    o['hitInterval'] = 2 * (hi['hit_scale'] + 1)
                    self.rep.add('LINEIV', '%s: unlimited hits, interval %sF -> %dF (BFE HIT規模 %d, 全弾更新 = one wait for the whole line)' % (
                        what, iv0, o['hitInterval'], hi['hit_scale']))
                elif segments > 1 and hm < 255:
                    o['hitCount'] = hm * segments
                    o['hitInterval'] = iv0 if iv0 > 0 else 6
                    notes.append('%s: hit count %d x %d segments = %d, interval %dF (BFE hits per segment)' % (
                        what, hm, segments, o['hitCount'], o['hitInterval']))
            put_slot(ph, 41, objs, self.lib)
        wobjs = list(u[42]['skillInfoObjectList']) if 42 in u else []
        if wobjs:
            if hw in (0, 254) or hi['power'] <= 0:
                drop_slots(ph, (42,))
            else:
                for o in wobjs:
                    s, e = o['startFrame'], o['endFrame']
                    self.conv._set_hit(o, hi, bph['noke_shot'], s, e, hw, weapon=True, cancel=False)
                put_slot(ph, 42, wobjs, self.lib)

    @staticmethod
    def _power(o):
        for u in o.get('ceventHitUnitList') or []:
            if u['unitSlotNum'] == 6:
                return u['data']['bsdxInfoCollectionList'][0]['paramList'][0]
        return None

    def _root(self, s, d, newidx, notes):
        a = self._anim(d['root'])
        se = self._se(d['root'])
        rt = self.T[d['root']]
        for t, ph in enumerate(s['phasesInfo']):
            L = turn_len(ph); u = units(ph)
            # T 2026-11-11 (ROOTHIT): the root's hits were never converted (パルスレーザー根元 Laser[198] kept 甲 Laser[23]'s
            # 威力 0 forward push F0-50; BFE ｳﾈｳﾈﾚｰｻﾞｰ Lv3：根元 ph0 HIT 254 = no hit) -> same rule as the parent / tip.
            if 41 in u or 42 in u:
                bph = rt['phases'][min(t, len(rt['phases']) - 1)]
                self._hits(ph, bph, L, notes, '根元 turn %d (BFE Tama %d ph%d)' % (t, d['root'], min(t, len(rt['phases']) - 1)),
                           add_if_missing=False, ti=d['root'])
                u = units(ph)
            if 0 in u:
                put_slot(ph, 0, self._sprite_events(a, L), self.lib)
                drop_slots(ph, (1, 2, 3, 7))
                self._put_zoom(ph, self._zoom(d['root']))
            if 52 in u:
                self._set_se(ph, se)
            self._strip_foreign_spawns(ph)

    def _parent(self, s, d, newidx, notes):
        LF = self.fx.LF
        line = self.T[d['line']]
        child_ids = {v for k, v in newidx.items() if role_of(self.fx.SH[LF]['skillList'][k]['skillNameJapanese']) == 'child'}
        for t, ph in enumerate(s['phasesInfo']):
            L = turn_len(ph); u = units(ph)
            for o in (u[48]['skillInfoObjectList'] if 48 in u else []):
                tg = effect_target(o)
                if tg and tg[0] == LF and tg[1] in child_ids:
                    s4 = effect_sub(o, 4); s5 = effect_sub(o, 5)
                    if s5 is None:
                        continue
                    self._child_spawn_zoom(o, d, t, notes)       # W 2026-11-03 LINEZOOM
                    if s4 is not None and not s4.get('int2') and not s4.get('int5'):
                        # retract (同時 0, 最大 N -> 0 over the event): start from our N, length = BFE retract time
                        s5['int2'] = d['segments']; s5['int5'] = 0
                        if d['retract_frames']:
                            o['endFrame'] = min(L - 1, o['startFrame'] + d['retract_frames'] - 1)
                            # W 2026-11-03: the sub-units carry their own frame range (vanilla: always the object's,
                            # e.g. 引き寄せ鞭 Laser[77] turn 1: object 0-9, subs 0-9); keep them with the object so the
                            # 最大 N -> 0 ramp spans the BFE retract time (was: object 0-17, subs 0-9)
                            for u in o['ceventEffectUnitList']:
                                if isinstance(u.get('data'), dict) and 'endFrame' in u['data']:
                                    u['data']['startFrame'], u['data']['endFrame'] = o['startFrame'], o['endFrame']
                            notes.append('ライン親 turn %d: retract %d segments in %dF (BFE count %s per tick)' % (
                                t, d['segments'], d['retract_frames'], d['retract_count']))
                    else:                   # growth: 同時 per frame, 最大 = segments
                        s5['int2'] = s5['int5'] = d['segments']
                        if s4 is not None:
                            s4['int2'] = s4['int5'] = d['per_frame']
            if 0 in u:            # parent drawn by the template (laser bit glow) = BFE root sprite
                put_slot(ph, 0, self._sprite_events(self._anim(d['root']), L), self.lib)
                drop_slots(ph, (7,))
            bph = line['phases'][min(t, len(line['phases']) - 1)]
            if t < len(line['phases']):
                self._hits(ph, bph, L, notes, 'ライン親 turn %d (BFE Tama %d ph%d)' % (t, d['line'], t), segments=d['segments'], ti=d['line'])
            n = self._strip_foreign_spawns(ph)
            if n:
                notes.append('ライン親 turn %d: %d 甲 effect spawn(s) dropped' % (t, n))

    def _seg_zoom(self, ti):
        """W 2026-11-03: BFE sprite zoom of a segment Tama = its first sprite event's zoom init, WHATEVER the zoom 'type'
        byte: BaldrForce.exe sets it at every event start without reading the type (0x443727 -> 0x440dd0 reads only
        init/final/step at event+0x22.., the result goes to the sprite at 0x44373f/0x443753; per tick 0x440ec0). The
        segments of ｸｫｳﾄﾜｲﾔｰ 63 = 256, ﾓｰﾆﾝｸﾞｽﾀｰ 75 = 192, ｽｳｨﾝｸﾞﾜｲﾔｰ 68 = 228 are type 0 (the vanilla DiveX
        re-creation モーニングスター Laser[88] spawns its child at 192 = the BFE value)."""
        for ph in self.T[ti]['phases']:
            for e in ph['events']:
                if 0 <= e['anim'] < len(self.fx.eff['anims']) and self.fx.eff['anims'][e['anim']]:
                    z = e['zoom']['init']
                    if z[0] == -32768:
                        return 256
                    return int(round((z[0] + z[1]) / 2.0)) if z[1] != -32768 else z[0]
        return 256

    def _child_spawn_zoom(self, o, d, t, notes):
        """W 2026-11-03 (LINEZOOM, 「クォウトワイヤーが原作より細く長い」): the ライン親 -> ライン子 spawn of the template
        carries the template's own sprite zoom (CEventEffect sub 16 拡大縮小 / 17 X / 18 Y / 19 Y(ｽﾛｰ)), tuned for the
        template's sprite: 引き寄せ鞭 Laser[77] -> [81] (Link.spm anim 12) X 64 / Y 384 = x0.25 thick, x1.5 pitch.
        DiveX: a created object starts with base zoom X/Y = the spawn values (0x611966/0x61196f -> +0x16a8/+0x16ac);
        only the child's own slot 1/2/3 events overwrite them (0x60b9e9 / 0x60ba17 / 0x60ba3f); the drawn zoom
        +0x16a0/+0x16a4 follows (0x60babf..0x60bb18) and the next child's link point is the previous child's hitFlag
        bit 5 point scaled by +0x16a0/+0x16a4 (0x664b70 -> 0x607e60, slot 43 unset). The BFE wire segment has no slot
        events here (zoom 256, type 0) -> the template X 64 / Y 384 stayed: thinner and 1.5x longer than BFE (0x414a10
        links with the sprite zoom). Rule: where the template spawn has sprite zoom subs, they become the BFE segment
        zoom (_seg_zoom), uniform (sub 16), X/Y subs dropped. Spawns without zoom subs are left as they are."""
        has = [n for n in (16, 17, 18, 19) if effect_sub(o, n) is not None]
        if not has:
            return
        z = self._seg_zoom(d['line'])
        old = {n: (effect_sub(o, n).get('int2'), effect_sub(o, n).get('int5')) for n in has}
        if 16 not in has:
            src = [u for u in o['ceventEffectUnitList'] if u['unitSlotNum'] == has[0]][0]
            u = copy.deepcopy(src); u['data']['offset'] = 0
            u['unitSlotNum'] = u['ceventEffectUnitQuantity'] = 16; u['description'] = 'ｽﾌﾟﾗｲﾄ：拡大縮小'
            o['ceventEffectUnitList'].append(u); o['ceventEffectUnitList'].sort(key=lambda x: x['unitSlotNum'])
        effect_sub(o, 16).update(int1=0, int2=z, int3=0, int4=0, int5=z)
        o['ceventEffectUnitList'] = [u for u in o['ceventEffectUnitList'] if u['unitSlotNum'] not in (17, 18, 19)]
        self.rep.add('LINEZOOM', 'ライン親 turn %d -> ライン子 spawn: template sprite zoom %s -> uniform %d (BFE Tama %d segment '
                     'zoom; DiveX base zoom from the spawn 0x611966, link point 0x607e60)' % (
                         t, ' '.join('%d:%s' % (n, ('%d' % v[0]) if v[0] == v[1] else '%d..%d' % v) for n, v in sorted(old.items())),
                         z, d['line']))

    def _child(self, s, d, newidx, notes):
        a = self._anim(d['line']); z = self._zoom(d['line'])
        for ph in s['phasesInfo']:
            L = turn_len(ph)
            put_slot(ph, 0, self._sprite_events(a, L), self.lib)
            drop_slots(ph, (1, 2, 3, 7))
            self._put_zoom(ph, z)
            if 43 in units(ph):
                # L 2026-11-01 (HITSCALE for segments, 「つなぎ目が離れすぎ」): the link point (hitFlag bit 5) of the
                # previous child is read by OBJECTPOS2 0x664b70 -> 0x607e60, which scales the rect by slot 43
                # (+0x17d8) when it is >= 0, else by the sprite zoom X/Y (+0x16a0/+0x16a4); 0x765800: rect*s>>8.
                # The 甲 Lv3 child carries 43 = 512 -> pitch 60x2 = 120 px while the BFE segment (anim 24, -9..71,
                # link 59-60) is drawn at Y 1.5 (120 px tall, 66 px bright) -> dark gaps. BFE scales the link point
                # with the sprite zoom (0x414a10), vanilla Y-zoomed children (ガリアンソード) have no 43 -> drop it.
                drop_slots(ph, (43,))
                self.rep.add('HITSCALE', 'line child slot 43 (template) not copied: link point / hit rect follow the sprite '
                             'zoom %s (BFE 0x414a10; DiveX 0x607e60 via OBJECTPOS2 0x664b70)' % z)
            n = self._strip_foreign_spawns(ph)
            if n:
                notes.append('ライン子: 甲 joint effect dropped')
        if z:
            notes.append('segment zoom %d -> slot 2/3 (link point scales with the sprite zoom when slot 43 is unset, DiveX 0x607e60)' % z)

    def _tip(self, s, d, newidx, notes):
        fx = self.fx
        tip = d['tip']
        if tip is None:
            for ph in s['phasesInfo']:
                drop_slots(ph, (0, 1, 2, 3, 7))
                self._strip_foreign_spawns(ph)
            notes.append('先端: BFE has no tip object -> 甲 tip kept invisible (position/timing only)')
            return
        tt = self.T[tip]; nph = len(tt['phases'])
        for t, ph in enumerate(s['phasesInfo']):
            L = turn_len(ph); u = units(ph); pi = min(t, nph - 1); bph = tt['phases'][pi]
            if t < nph and 71 in u and bph['go_hit_mech'] == -99 and bph['go_hit_weapon'] == -99:
                # R 2026-11-18 (TIPHITGO, user 「モーニングスター: ワイヤーに弾が付いている段で相手に当たると、ワイヤーの
                # ダメージだけが入り、爆発等もなくパッと弾が消える」): the 甲 tip turn 0 carries 「攻撃→何かにヒットしていたら
                # => ターンジャンプ→１つ先」 (甲 モーニングスターLv3（先端） T0: the ball comes off the chain at the first hit).
                # BFE ﾓｰﾆﾝｸﾞｽﾀｰ Lv3：先端 ph0 has no go_hit_mech / go_hit_weapon (hits 255, stays on the chain; only
                # go_mech_skill 1 = the move's end lets it go, go_obstacle 2). Our turn 1 is the TIPDETACH release, so a hit
                # released the ball at once (and the tip turn with its hit ended). -> where the BFE tip phase has no
                # hit -> phase change, the template's hit -> jump changes of that turn are dropped.
                o71 = u[71]['skillInfoObjectList']
                keep71 = [o for o in o71 if not any('攻撃→何かにヒットしていたら' in self.lib.tt.text(b) for b in o['bsdxInfoCollectionList1'])]
                if len(keep71) != len(o71):
                    u[71]['skillInfoObjectList'] = keep71
                    m_ = '先端 turn %d: 甲 「何かにヒットしていたら -> 次のターン」 dropped (BFE Tama %d ph%d has no hit -> phase change; TIPHITGO)' % (t, tip, pi)
                    notes.append(m_); self.rep.add('TIPHITGO', m_)
            if 0 < t < nph and tt['phases'][t - 1]['go_mech_skill'] == t and bph['hit']['hits_mech'] not in (0, 254) and                     bph['hit']['power'] > 0 and 71 in u and hasattr(fx, 'tail_bullet'):
                # E 2026-11-15 (TIPDETACH, user 「モーニングスター: 弾が鉄球から離れてから 1 秒ほどは判定がある。そのあと完全に
                # 残留物として残ったあとに判定が消える」): BFE's tip is an ordinary bullet; when the move ends (go_mech_skill)
                # it goes on alone (ﾓｰﾆﾝｸﾞｽﾀｰ：先端 ph1: 101 ticks, 1 hit, then ph2 the blast). The DiveX tip is a part
                # of the line; its hits stop about 50F after the release = when the line parent's retract turn ends
                # (parent T1 F0-49; the ball also stops at F51). -> at the release the tip spawns the BFE phases from
                # here on as their own bullet (fx.tail_bullet) and ends; the tip's own later turns are not used.
                tgt = fx.tail_bullet(tip, t)
                if tgt:
                    drop_slots(ph, (0, 1, 2, 3, 7, 9, 10, 15, 18, 41, 42, 45, 48, 52, 54))
                    sp_ = self.conv.spawn('bullet', tgt, 0, 2)
                    # the bullet goes on along the tip's facing (= the line's direction; the tip turn had slot 15 スプライト方向)
                    d28_ = effect_sub(sp_, 28, fx.sub_samples.get(28))
                    if d28_ is not None and d28_.get('bsdxInfoCollectionList'):
                        b28_ = d28_['bsdxInfoCollectionList'][0]
                        b28_['typeList'] = [3, 0]; b28_['paramList'] = [0, 0]; b28_['intList3'] = [0, 0]; b28_['intList4'] = []
                        d28_['startFrame'] = d28_['endFrame'] = 0
                    put_slot(ph, 48, [sp_], self.lib)
                    ch = [o for o in units(ph)[71]['skillInfoObjectList'] if o['bsdxInfoCollectionList1'][0]['typeList'] == [0]]
                    assert ch, 'TIPDETACH: no unconditional change in tip turn %d' % t
                    e = copy.deepcopy(ch[0]); e['startFrame'] = e['endFrame'] = 1; e['offset'] = 0
                    e['bsdxInfoCollectionList2'][0]['typeList'] = [0, 2]; e['bsdxInfoCollectionList2'][0]['paramList'] = []
                    put_slot(ph, 71, [e], self.lib)
                    notes.append('先端 turn %d: move ended -> BFE Tama %d phases %d- as their own bullet, the tip ends (TIPDETACH)' % (t, tip, t))
                    for ph2 in s['phasesInfo'][t + 1:]:
                        self._strip_foreign_spawns(ph2)
                    break
            had_bomb = any((effect_target(o) or (0,))[0] == 7 for o in (u[48]['skillInfoObjectList'] if 48 in u else []))
            if 0 in u:
                put_slot(ph, 0, self._phase_sprites(tt['phases'][pi], L), self.lib)
                drop_slots(ph, (1, 2, 3, 7))
                zs = [e['zoom']['init'][0] for e in tt['phases'][pi]['events'] if e['zoom']['type'] == 1 and e['zoom']['init'][0] not in (-32768, 256)]
                self._put_zoom(ph, zs[0] if zs else None, uniform=True)
            if 41 in u or 42 in u:
                self._hits(ph, bph, L, notes, '先端 turn %d (BFE Tama %d ph%d)' % (t, tip, pi), add_if_missing=False, ti=tip)
            if 51 in u and t < nph and bph['touch_mech_enemy'] == 0 and bph['hit']['hits_mech'] not in (0, 254) and bph['hit']['power'] > 0:
                # R 2026-11-15 (TIPTOUCH, user 「モーニングスターが、弾が残留したあと、当たり判定がなくなっている」): the tip
                # keeps the 甲 template's slot 51. 甲 モーニングスターLv3（先端） T1 (the ball left behind) has 水平：メカ（敵）
                # 1 = it collides with the enemy's body; BFE ﾓｰﾆﾝｸﾞｽﾀｰ：先端 ph1 has 接触 メカ敵 0 (passes through) and a
                # 1-hit attack. With the body collision the enemy was pushed out of the ball and never reached the BFE
                # attack rect (same as 火炎放射器 10/29, BTOUCH). -> 水平：メカ（敵） 0 where BFE says 0 and the phase hits.
                n51_ = 0
                for o51 in u[51]['skillInfoObjectList']:
                    bd = o51.get('byteData1')
                    if bd and len(bd) == 56 and bd[0] == 1:
                        bd[0] = 0; n51_ += 1
                if n51_:
                    notes.append('先端 turn %d: BFE 接触 メカ敵 0 -> slot 51 水平：メカ（敵） 1 -> 0 (TIPTOUCH)' % t)
            self._strip_foreign_spawns(ph)
            spawns = []
            if had_bomb and t < nph:          # 甲 explosion -> the BFE explosion phase as its own bullet
                tgt = fx.phase_bullet(tip, t)
                if tgt:
                    spawns.append(self.conv.spawn('bullet', tgt, 0, L)); notes.append('先端 turn %d: 甲 Bomb -> BFE Tama %d ph%d as bullet' % (t, tip, t))
            elif t < nph and bph['fire']['tama'] >= 0 and bph['fire']['fire_type'] == 0:
                tgt = fx.tama_target(bph['fire']['tama'])
                if tgt:
                    o = self.conv.spawn('bullet', tgt, 0, L); self.conv._set_fire(o, bph['fire'], fx.tama_speed(bph['fire']['tama']))
                    spawns.append(o)
            if spawns:
                old = list(units(ph)[48]['skillInfoObjectList']) if 48 in units(ph) else []
                put_slot(ph, 48, old + spawns, self.lib)
            se = self._se_phase(bph)
            if 52 in u or se:
                self._set_se(ph, se)

    def _se_phase(self, bph):
        for e in bph['events']:
            if e['se_play'] >= 0:
                s = self.fx.se.get(e['se_play'])
                if s:
                    return s
        return None

    def _other(self, s, d, newidx, notes):
        for ph in s['phasesInfo']:
            self._strip_foreign_spawns(ph)
