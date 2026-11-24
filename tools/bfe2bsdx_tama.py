#!/usr/bin/env python3
"""bfe2bsdx_tama.py - registry that converts BALDR FORCE EXE bullets (Tama.dat) and effects (calc_effect types ->
Effect.spr anims) into skills appended to BALDR SKY DiveX shared waz files, on demand (closure of what the mech moves
really use). Used by mods/phase3b_tooru/build_phase3b.py through bfe2bsdx_waz.Converter(fx=Fx(...)).

  bullets  -> appended to shared waz BULLET_FILE (Tama04 for TOORU), converted with Converter(mode='bullet'),
              template = vanilla Tama01[4]「ハンドガン：甲」 (hit objects, CPU escape, slow-motion boilerplate only)
  effects  -> appended to shared waz EFFECT_FILE (Tama02 for TOORU): one skill per BFE effect type = its Effect.spr
              anim(s) (bfe2bsdx_effmap) played once + the sub-effects the BFE handler spawns
  lasers   -> fire_type 1/2 (ﾚｰｻﾞｰ / ｳﾈｳﾈ wire) and laser roots: bfe2bsdx_line.LineBuilder copies the template move's BSDX
              line chain (ライン親/子/先端, LASER_FILE) and fills it with the BFE segment sprite / count / zoom / hits / SE
              (both engines chain segments the same way: each segment attaches to the previous one's link point)
All sprite refs of converted skills point at the effect spm registered at SpriteGroup <spm_seq> (tooru_eft.spm).
"""
import copy, collections
from bfe2bsdx_waz import Converter, walk, effect_target
import bfe2bsdx_effmap
import bfe2bsdx_line


class Fx:
    def __init__(self, lib, eff_spr, tama, semap, rep, shared, names, spm_seq, bullet_file, effect_file, laser_file,
                 kou_waz, label, combo_v3=None):
        # label: the mech's mark in the converted names ('…（<label>弾303）'); combo_v3: its COMBOV3 tables (Converter)
        self.lib = lib; self.eff = eff_spr; self.tama = tama; self.se = semap; self.rep = rep
        self.SH = shared; self.names = names; self.spm_seq = spm_seq; self.label = label
        self.BF, self.EF, self.LF = bullet_file, effect_file, laser_file
        self.appended = collections.defaultdict(list)
        self.tcache, self.ecache, self.lcache = {}, {}, {}
        self.tama_notes = {}
        self.tama_log = {}      # ti -> Report.log entries of its conversion (調査記録 15)
        self.effmap = bfe2bsdx_effmap.load()
        A = eff_spr['anims']
        self.conv = Converter(lib, A, semap, rep, [len(a) for a in A], fx=self, mode='bullet', spm_seq=spm_seq, combo_v3=combo_v3)
        # ---- templates / samples from vanilla data
        self.tpl_bullet = shared[1]['skillList'][4]                       # Tama01「ハンドガン：甲」
        assert 'ハンドガン' in self.tpl_bullet['skillNameJapanese']
        homing = shared[2]['skillList'][1]                                 # Tama02「ホーミングミサイル：甲Lv1」
        assert 'ホーミング' in homing['skillNameJapanese']
        u = lambda sk, t, s: [o for x in sk['phasesInfo'][t]['skillUnitCollection'] if x['unitQuantity'] == s for o in x['skillInfoObjectList']]
        self.homing_dir = u(homing, 0, 15)[0]
        self.sprite_dir = u(homing, 0, 8)[0]
        # a sprite that keeps the parent's facing (no tilt along the movement) = vanilla Tama04「グラビティボム：甲Lv3」 T0 slot 8
        # 角度指定→スプライト方向 of 親 (intList3 [2, 0]); see FLATCHIP in bfe2bsdx_waz
        gb = shared[4]['skillList'][51]
        assert 'グラビティボム：甲Lv3' in gb['skillNameJapanese']
        self.sprite_flat = u(gb, 0, 8)[0]
        assert self.sprite_flat['bsdxInfoCollectionList'][0]['typeList'] == [3, 0] and self.sprite_flat['bsdxInfoCollectionList'][0]['intList3'] == [2, 0]
        self._bullet_spawn = u(homing, 1, 48)[0]                           # bullet -> Bomb explosion spawn
        # effect spawn = the same plain spawn (position = spawner origin, no speed / direction subs), scale 1.0
        self._effect_spawn = copy.deepcopy(self._bullet_spawn)
        for x in self._effect_spawn['ceventEffectUnitList']:
            if x['unitSlotNum'] == 16:
                x['data']['int5'] = 256; x['data']['int6'] = 0
        self._mech_effect_spawn = self._effect_spawn
        k285 = u(kou_waz['skillList'][285], 1, 48)                         # Kou ホーミングミサイルLv3: missile + smoke spawns
        self.sub_samples = {x['unitSlotNum']: x for x in [o for o in k285 if effect_target(o)[0] == 2][0]['ceventEffectUnitList']}
        sat = [o for o in walk(kou_waz['skillList'][318]) if 'ceventEffectUnitList' in o and (effect_target(o) or (0,))[0] == 4][0]
        self.sub_samples.setdefault(11, [x for x in sat['ceventEffectUnitList'] if x['unitSlotNum'] == 11][0])   # 甲 サテライトレーザーLv3 height
        # ﾍﾞｸﾄﾙ：高さ of a bullet that keeps its position (前指定を維持): 甲 門倉コレダーLv3 -> Tama04[77] sub 32 40
        kc = kou_waz['skillList'][47]
        assert '門倉コレダー' in kc['skillNameJapanese']
        self.sub_samples.setdefault(32, [x for o in walk(kc) if 'ceventEffectUnitList' in o for x in o['ceventEffectUnitList'] if x['unitSlotNum'] == 32][0])
        # spawn 発射位置補正 (sub 8 方向 / 9 方向補正 / 10 距離) = BFE fire 位置補正 (POSCORR): first vanilla spawn that has all three
        for w_ in shared.values() if isinstance(shared, dict) else shared:
            hit_ = [o for o in walk(w_) if isinstance(o, dict) and 'ceventEffectUnitList' in o and
                    {8, 9, 10} <= {x['unitSlotNum'] for x in o['ceventEffectUnitList']}]
            if hit_:
                for x in hit_[0]['ceventEffectUnitList']:
                    if x['unitSlotNum'] in (8, 9, 10):
                        self.sub_samples.setdefault(x['unitSlotNum'], x)
                break
        assert all(k in self.sub_samples for k in (8, 9, 10))
        # bullet that fires a laser (BFE ﾚｰｻﾞｰﾋﾞｯﾄ): the spawn of 甲's laser bit bullet (Tama03「レーザービット：甲Lv3」 -> Laser line)
        bit = shared[3]['skillList'][3]
        assert 'レーザービット' in bit['skillNameJapanese']
        self.bullet_laser_proj = [o for o in walk(bit) if 'ceventEffectUnitList' in o and (effect_target(o) or (0,))[0] == laser_file][0]
        # sprite faces the target = 甲's laser bit slot 8 「オブジェクト位置指定」 (T0 F31-, T1); BFE チップ向き type 1 ﾛｯｸｵﾝした敵方向
        self.sprite_target = [o for o in u(bit, 1, 8) if o['bsdxInfoCollectionList'][0]['typeList'] == [1]][0]
        # body collision off/on = vanilla 甲 Ｉ・Ａ・ＩLv3 slot 51 接触 (T0 frame 0: 水平：メカ(敵) 0 / T1: back to 1)
        iai = kou_waz['skillList'][167]
        assert 'Ｉ・Ａ・Ｉ' in iai['skillNameJapanese']
        t51 = lambda t: [o for u in iai['phasesInfo'][t]['skillUnitCollection'] if u['unitQuantity'] == 51 for o in u['skillInfoObjectList']][0]
        self.touch_off, self.touch_on = t51(0), t51(1)
        assert self.touch_off['byteData1'][0] == 0 and self.touch_on['byteData1'][0] == 1
        # a falling beam that rests on the enemy = vanilla Tama04「サテライトレーザー：甲Lv3」 T0 slot 51 (垂直：メカ（敵） 1,
        # dword 9; everything else 0): the beam stands on the enemy while it hits, T1 (all 0) then pierces to the ground
        sat = shared[4]['skillList'][27]
        assert 'サテライトレーザー：甲Lv3' in sat['skillNameJapanese']
        self.dive_touch = u(sat, 0, 51)[0]
        assert self.dive_touch['byteData1'][36] == 1 and sum(self.dive_touch['byteData1']) == 1
        # 「常に標的位置」 (BFE move_dir 5: ｼｰﾙﾄﾞ follows the mech, 吸着ﾏｲﾝ sticks to the enemy) = vanilla slot 11 位置
        # 「前指定を維持」 over the turn (Tama05「マインナックル：甲Lv1」, Tama04「シールド：甲」): the bullet stays on the object
        # its spawn position names (spawn sub 7 from the 甲 template: self for シールド, hit target 9 for マインナックル)
        mk = shared[5]['skillList'][10]
        assert 'マインナックル' in mk['skillNameJapanese']
        self.keep_pos = u(mk, 0, 11)[0]
        # both vanilla stick/follow bullets also switch 接触 off at frame 0 (slot 51, all 56 bytes 0): the attached
        # object is not pushed back by walls / screen edge / mechs (S 2026-10-28: ｼｰﾙﾄﾞ stopped following, reported)
        self.keep_touch = u(mk, 0, 51)[0]
        assert not any(self.keep_touch['byteData1'])
        self.lines =bfe2bsdx_line.LineBuilder(self)
        self.pcache = {}
        # HITCANCEL (調査記録 20): Tama fired (directly or through other bullets) by a 打撃 (技タイプ 0) mech skill; filled by
        # the mech Converter before it converts that skill's bullets
        self.melee_tamas = set()

    def hit_cancel(self, ti):
        """HITCANCEL: a converted bullet's mech hit enables the owner's cancel (hit +0x64 = 1) when its own BFE 技タイプ
        is 打撃 (BaldrForce.exe 0x44186b-0x441878 reads the HITTING object's skill +0x29) and it is the striking part of a
        打撃 move (BFE also requires the weapon in use, +0x284; DiveX has no such test, so 射撃 skills' bullets -> 0)"""
        return ti is not None and 0 <= ti < len(self.tama) and self.tama[ti]['header'].get('kind') == 0 and ti in self.melee_tamas

    # ------------------------------------------------------------------ registry
    def _alloc(self, f, skill_placeholder=None):
        idx = len(self.SH[f]['skillList']) + len(self.appended[f])
        self.appended[f].append(skill_placeholder)
        return idx

    def spawn_sample(self, kind):
        return {'bullet': self._bullet_spawn, 'effect': self._effect_spawn, 'effect_from_mech': self._mech_effect_spawn}[kind]

    def tama_speed(self, ti):
        sp = self.tama[ti]['phases'][0]['speed']
        r = sp['final'] if (sp['step'][0] == 0 or sp['init'][0] == -32768) else sp['init']   # 増分 0 = final at once
        v = (r[0] + r[1]) // 2
        # S 2026-10-30 (BSPEED): raw BFE px/tick; every converted bullet scales its skill vector by slot 25 50%
        # (bfe2bsdx_waz BSPEED) = v/2 px/F exactly (was round(v/2): 1 -> 1 = 2x)
        return 0 if r[0] == -32768 else v

    def tama_target(self, ti):
        if ti in self.tcache:
            return self.tcache[ti]
        if ti < 0 or ti >= len(self.tama):
            return None
        f = self.BF
        idx = self._alloc(f)
        self.tcache[ti] = (f, idx)
        t = self.tama[ti]
        nm = t['header']['name'].replace('　', ' ').strip()
        before = {k: collections.Counter(v) for k, v in self.rep.items.items()}
        m0 = self.rep.mark()
        sk = self.conv.convert(t, self.tpl_bullet, '%s（%s弾%d）' % (nm, self.label, ti), 'BFE_TAMA%03d' % ti)
        self.tama_log.setdefault(ti, []).extend(self.rep.since(m0))
        self.tama_notes[ti] = {'%s: %s' % (k, m) for k, v in self.rep.items.items() for m in v
                               if v[m] > before.get(k, {}).get(m, 0) and k in ('APPROX', 'DROPPED', 'LASER', 'IGNORED', 'LINE')}
        self.appended[f][idx - len(self.SH[f]['skillList'])] = sk
        self.rep.add('BULLET', '%s[%d] <- BFE Tama %d「%s」 (%d turns)' % (self.names[f], idx, ti, nm, sk['phaseQuantity']))
        return (f, idx)

    def chain_has_laser(self, ti, seen=None):
        """True when Tama <ti> itself spawns a laser / wire segment (fire_type 1/2): ﾗｲﾝ/ｳﾈｳﾈﾚｰｻﾞｰ roots"""
        seen = seen if seen is not None else set()
        if ti < 0 or ti >= len(self.tama) or ti in seen:
            return False
        seen.add(ti)
        for ph in self.tama[ti]['phases']:
            f = ph['fire']
            if f['tama'] >= 0 and f['fire_type'] != 0:      # root level only (a bit that shoots lasers stays a BFE bit)
                return True
        return False

    def effect_anims(self, et):
        e = self.effmap.get(et)
        return [a for a in (e['anims'] if e else []) if 0 <= a < 512 and self.eff['anims'][a]]

    def effect_target(self, et, depth=0):
        if et in self.ecache:
            return self.ecache[et]
        anims = self.effect_anims(et)
        if not anims or depth > 3:
            self.ecache[et] = None
            return None
        f = self.EF
        idx = self._alloc(f)
        self.ecache[et] = (f, idx)
        lib = self.lib; ev = collections.defaultdict(list); t = 0
        a = anims[0]
        L = max(2, sum((p['wait'] + 1) * 2 for p in self.eff['anims'][a]))
        for (p, s0, s1) in self.conv.patterns(a, L, False):
            ev[0].append(self.conv.sprite(a, p, s0, s1))
        for sub in self.effmap[et]['spawns']:
            if sub != et:
                tgt = self.effect_target(sub, depth + 1)
                if tgt:
                    ev[48].append(self.conv.spawn('effect', tgt, 0, L))
        ev[71].append(lib.change([], 'end', L - 1, L - 1))
        units = []
        for slot in sorted(ev):
            for o in ev[slot]:
                o['slotNum'] = slot
            units.append({'unitQuantity': slot, 'unitDescription': lib.desc[slot], 'skillInfoObjectList': ev[slot], 'skillInfoUnknownList': []})
        sk = {'phaseQuantity': 1, 'skillNameJapanese': 'BFEエフェクト%02d（%s）' % (et, self.label), 'skillNameEnglish': 'BFE_EFFECT%02d' % et,
              'phasesInfo': [{'skillUnitCollection': units}], 'skillSuffixList': [{'int1': 0, 'int2': 0}]}
        self.appended[f][idx - len(self.SH[f]['skillList'])] = sk
        self.rep.add('EFFECT', '%s[%d] <- BFE effect type %d -> Effect.spr anim %d (+spawns %s), %dF' % (
            self.names[f], idx, et, a, self.effmap[et]['spawns'], L))
        return (f, idx)

    def line_chain(self, name, ti, proj, mech_tip=None, life=None):
        """laser / wire root Tama <ti> -> BSDX line chain (template = the Laser chain <proj> spawns), BFE data"""
        return self.lines.build(name, ti, proj, mech_tip, life)

    def phase_bullet(self, ti, pi):
        """one phase of a Tama converted as its own bullet (BFE wire tip explosion phase)"""
        key = (ti, pi)
        if key in self.pcache:
            return self.pcache[key]
        t = copy.deepcopy(self.tama[ti]); ph = t['phases'][pi]
        for k in [k for k in ph if k.startswith('go_')]:
            ph[k] = -99
        t['phases'] = [ph]; t['header']['alg_list'] = [0] + [99] * 31; t['header']['loops'] = []
        f = self.BF; idx = self._alloc(f); self.pcache[key] = (f, idx)
        nm = t['header']['name'].replace('　', ' ').strip()
        m0 = self.rep.mark()
        sk = self.conv.convert(t, self.tpl_bullet, '%s ph%d（%s弾%d）' % (nm, pi, self.label, ti), 'BFE_TAMA%03d_P%d' % (ti, pi))
        self.tama_log.setdefault(ti, []).extend(self.rep.since(m0))
        self.appended[f][idx - len(self.SH[f]['skillList'])] = sk
        self.rep.add('BULLET', '%s[%d] <- BFE Tama %d phase %d「%s」' % (self.names[f], idx, ti, pi, nm))
        return (f, idx)

    def tail_bullet(self, ti, pi):
        """the phases pi.. of a Tama converted as their own bullet (a wire tip left behind when its move ends, TIPDETACH):
        phase jumps are renumbered, jumps back before pi are dropped"""
        key = (ti, pi, 'tail')
        if key in self.pcache:
            return self.pcache[key]
        t = copy.deepcopy(self.tama[ti]); phs = t['phases'][pi:]
        for ph in phs:
            for k in [k for k in ph if k.startswith('go_')]:
                v = ph[k]
                if v in (-99, -1, 99):
                    continue
                ph[k] = v - pi if v >= pi else -99
        t['phases'] = phs; t['header']['alg_list'] = list(range(len(phs))) + [99] * (32 - len(phs)); t['header']['loops'] = []
        t['header']['phase_count'] = len(phs)
        f = self.BF; idx = self._alloc(f); self.pcache[key] = (f, idx)
        nm = t['header']['name'].replace('　', ' ').strip()
        m0 = self.rep.mark()
        sk = self.conv.convert(t, self.tpl_bullet, '%s ph%d-（%s弾%d）' % (nm, pi, self.label, ti), 'BFE_TAMA%03d_T%d' % (ti, pi))
        self.tama_log.setdefault(ti, []).extend(self.rep.since(m0))
        self.appended[f][idx - len(self.SH[f]['skillList'])] = sk
        self.rep.add('BULLET', '%s[%d] <- BFE Tama %d phases %d-「%s」' % (self.names[f], idx, ti, pi, nm))
        return (f, idx)

    def legacy_bullet(self, name, ti, fire, proj):
        """laser / wire: copy of the template's BSDX laser skill with the BFE damage"""
        key = (name, ti)
        if key in self.lcache:
            return self.lcache[key]
        src = effect_target(proj) if proj else None
        if not src or src[0] >= len(self.SH):
            return None
        b = copy.deepcopy(self.SH[src[0]]['skillList'][src[1]])
        base = b['skillNameJapanese']
        b['skillNameJapanese'] = '%s（%s）' % (name, self.label)
        pw = self._tama_power(ti)
        hits = [o for o in walk(b) if o.get('typeId') == 16 and 'ceventHitUnitList' in o]
        dmg = None
        if pw and hits:
            dmg = max(1, round(pw / 4))
            for u in hits[0]['ceventHitUnitList']:
                if u['unitSlotNum'] == 6:
                    u['data']['bsdxInfoCollectionList'][0]['typeList'] = [0]
                    u['data']['bsdxInfoCollectionList'][0]['paramList'] = [dmg]
        f = src[0] if src[0] == self.LF else self.LF
        idx = self._alloc(f, b)
        self.lcache[key] = (f, idx)
        self.rep.add('LASER', '%s: %s[%d]「%s」 copied -> %s[%d] damage %s (BFE Tama %d power %s / 4)' % (
            name, self.names[src[0]], src[1], base, self.names[f], idx, dmg if dmg else 'template', ti, pw))
        return (f, idx)

    def _tama_power(self, ti, seen=None):
        seen = seen or set()
        if ti < 0 or ti in seen:
            return None
        seen.add(ti)
        for ph in self.tama[ti]['phases']:
            if ph['hit']['hits_mech'] not in (0, 254) and ph['hit']['power'] > 0:
                return ph['hit']['power']
        for ph in self.tama[ti]['phases']:
            if ph['fire']['tama'] >= 0:
                v = self._tama_power(ph['fire']['tama'], seen)
                if v:
                    return v
        return None

    def hitlock_exempt(self, keep_skills=(), keep_phases=()):
        """HITLOCK (調査記録 36, user 2026-11-09): BSX plugin ヒットロック = on a hit, BaldrSky.exe 0x620080-0x6200d8 switches the
        player's lock-on to the victim when the plugin is on ([0x873e24] & 4), the hit's CEventHit +0x10 (JSON int2) has
        no bit 0x20, and the attacking object's vf 0x124 weapon (mek WeaponInfo) has 攻撃タイプ (+0x7c, weaponType) 0 =
        格闘. Bullets / lines inherit vf 0x124 from their parent at spawn (0x615780-0x61578c, 0x628477-0x628483), so a
        bullet of a 格闘 weapon locks like a punch unless its hit has 0x20. Vanilla 甲: スプレッドパンチ：甲 (int2 34), Ｅフィールド：甲
        (34), Ｇフィールド：甲 (32/48), ギガンテックフィールド (34), アルティメットナックル 衝撃波 carry 0x20; bit 0x20 is tested only
        there (0x620089). Rule: every 対メカ hit (slot 41) of every bullet / line / effect this port appends -> int2 |= 0x20
        (for a 射撃 weapon the plugin never fires, so the bit is inert there). The mech's own hits keep locking.
        keep_skills (user 2026-11-09, hand-picked like 甲's own mix: 門倉コレダー / ケイジブレイド / マインナックル lock, スプレッドパンチ /
        fields do not): mech skills whose bullets / lines (whole WazaSelect chain into the appended skills) keep their
        template int2 minus bit 0x20, i.e. still switch the lock-on.
        keep_phases: {(appended skill name, turn index)} whose hits also keep locking although the weapon is not in
        keep_skills (user 2026-11-09: モーニングスター like 甲 = only the tip's first turn locks, 0x620089)."""
        keep_phases = set(keep_phases)
        found_ = set()
        keep, todo = set(), [s_ for s_ in keep_skills]
        while todo:
            for d in walk(todo.pop()):
                if isinstance(d, dict) and 'wazFileNo' in d and 'wazSequenceNo' in d:
                    f_, i_ = d['wazFileNo'], d['wazSequenceNo']
                    L_ = self.appended.get(f_)
                    if L_ is not None and (f_, i_) not in keep:
                        j_ = i_ - len(self.SH[f_]['skillList'])
                        if 0 <= j_ < len(L_):
                            keep.add((f_, i_)); todo.append(L_[j_])
        for f_, i_ in sorted(keep):
            self.rep.add('HITLOCK', '%s[%d] %s: kept (ヒットロック反応、ユーザー指定)' % (
                self.names[f_], i_, self.appended[f_][i_ - len(self.SH[f_]['skillList'])].get('skillNameJapanese')))
        rev = {}
        for d_, keyf in ((self.tcache, lambda k: k), (self.pcache, lambda k: k[0]), (self.lcache, lambda k: k[1])):
            for k, v in d_.items():
                if v:
                    rev.setdefault(v, keyf(k))
        n = 0
        for f, L in self.appended.items():
            v0 = len(self.SH[f]['skillList'])
            for j, sk in enumerate(L):
                c = 0
                if (f, v0 + j) in keep:
                    # kept: also clear a 0x20 the template brought (モーニングスター：先端 from 甲's tip had int2 32)
                    for ph in sk['phasesInfo']:
                        for u in ph['skillUnitCollection']:
                            if u['unitQuantity'] == 41:
                                for o in u['skillInfoObjectList']:
                                    if o.get('int2', 0) & 0x20:
                                        o['int2'] &= ~0x20
                                        self.rep.add('HITLOCK', '%s[%d] %s: template int2 0x20 cleared (ヒットロック反応、ユーザー指定)' % (
                                            self.names[f], v0 + j, sk.get('skillNameJapanese')))
                    continue
                for pi_, ph in enumerate(sk['phasesInfo']):
                    if (sk.get('skillNameJapanese'), pi_) in keep_phases:
                        found_.add((sk.get('skillNameJapanese'), pi_))
                        for u in ph['skillUnitCollection']:
                            if u['unitQuantity'] == 41:
                                for o in u['skillInfoObjectList']:
                                    o['int2'] = o.get('int2', 0) & ~0x20
                        self.rep.add('HITLOCK', '%s[%d] %s turn %d: kept (ヒットロック反応、ユーザー指定・甲と同じ)' % (
                            self.names[f], v0 + j, sk.get('skillNameJapanese'), pi_))
                        continue
                    for u in ph['skillUnitCollection']:
                        if u['unitQuantity'] == 41:
                            for o in u['skillInfoObjectList']:
                                if not o.get('int2', 0) & 0x20:
                                    o['int2'] = o.get('int2', 0) | 0x20; c += 1
                if c:
                    n += c
                    m = '%s[%d] %s: %d 対メカ hit(s) int2 |= 0x20 (ヒットロック対象外)' % (self.names[f], v0 + j, sk.get('skillNameJapanese'), c)
                    self.rep.add('HITLOCK', m)
                    ti = rev.get((f, v0 + j))
                    if isinstance(ti, int):
                        self.tama_log.setdefault(ti, []).append(('HITLOCK', m))
        assert found_ == keep_phases, ('HITLOCK keep_phases not found', keep_phases - found_)
        return n

    def chain(self, ti, seen=None):
        seen = seen if seen is not None else set()
        if 0 <= ti < len(self.tama) and ti not in seen:
            seen.add(ti)
            for ph in self.tama[ti]['phases']:
                self.chain(ph['fire']['tama'], seen)
        return seen

    def log_for(self, skill):
        """full provenance log (Report.log entries) of the bullets fired by <skill>, per Tama (調査記録 15)"""
        out = {}
        for ph in skill['phases']:
            for t in self.chain(ph['fire']['tama']):
                if t in self.tama_log:
                    out[t] = self.tama_log[t]
        return out

    def notes_for(self, skill):
        out = set()
        for ph in skill['phases']:
            for t in self.chain(ph['fire']['tama']):
                out |= self.tama_notes.get(t, set())
        return out

    def eft_anims_used(self):
        out = set()
        for f, L in self.appended.items():
            for sk in L:
                for d in walk(sk):
                    if 'actionGroupNumber' in d and d.get('spmFileSequence') == self.spm_seq:
                        out.add(d['actionGroupNumber'])
        return out
