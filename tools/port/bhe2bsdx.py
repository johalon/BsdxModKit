#!/usr/bin/env python3
"""Generic BHE -> BSDX mech-port helpers (operate on NeXAS_DX JSON; see notes/08_tsukuyomi_port.md).

Used by mods/phase3a_tsukuyomi/build_phase3a.py. Everything here is mech-independent:
  * Term remap   : BHE Term.grp (34 groups) -> BSDX Term.grp (30 groups), by group code + item name, following the
                   Term grammar (item.param2 >= 0 -> next group). Hit attack term (Hit unit 6) PARAM -> ATTACK2.
  * AI remap     : BHE CCpuEvent field layout -> BSDX layout (NeXAS_DX's BHE DTO names are shifted, see ai_event()).
  * closure      : shared-waz skills needed by a mech waz (WazaSelect refs + Term JUMP '技ジャンプ' params).
  * ref remap    : WazaSelect (file,seq), JUMP params, sprite (group,anim,pattern), SE blobs, voice blobs.
  * material     : MaterialBlock rebuilt for BSDX registry sizes.
All functions collect problems in a Report instead of silently guessing.
"""
import json, os, struct, subprocess, collections

T = '/path/to/workspace/tools'


class Report:
    def __init__(self):
        self.items = collections.defaultdict(collections.Counter)

    def add(self, kind, msg, n=1):
        self.items[kind][msg] += n

    def dump(self, out=None):
        lines = []
        for k in sorted(self.items):
            c = self.items[k]
            lines.append('## %s (%d)' % (k, sum(c.values())))
            for m, n in sorted(c.items(), key=lambda x: (-x[1], x[0])):
                lines.append('  %s x%d' % (m, n))
        s = '\n'.join(lines)
        if out:
            open(out, 'w', encoding='utf-8').write(s + '\n')
        return s


def porttool(*args):
    """run tools/porttool.sh with jobs separated by ';' (list of lists)"""
    flat = []
    for job in args:
        if flat:
            flat.append(';')
        flat += list(job)
    r = subprocess.run([T + '/porttool.sh'] + flat, capture_output=True, text=True)
    if r.returncode != 0 or 'FAIL' in r.stdout:
        raise RuntimeError(r.stdout[-4000:] + r.stderr[-2000:])
    return r.stdout


def jload(p):
    return json.load(open(p, encoding='utf-8'))


def jsave(o, p):
    json.dump(o, open(p, 'w', encoding='utf-8'), ensure_ascii=False)


def glist(g):
    return [v for k, v in g.items() if isinstance(v, list) and k != 'voiceTypeList'][0]


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def i32(raw, k):
    return struct.unpack_from('<i', bytes((x + 256) % 256 for x in raw[4 * k:4 * k + 4]))[0]


def set_i32(raw, k, v):
    b = struct.pack('<i', v)
    for j in range(4):
        x = b[j]
        raw[4 * k + j] = x - 256 if x > 127 else x


# ------------------------------------------------------------------------------------------------ Term
class TermMap:
    """BHE Term (group,item-chain) -> BSDX, by names. termList JSON from Term.grp of each game."""
    ALIAS = {  # (group code, BHE item name) -> BSDX item name, for renamed items
        ('OBJECT4', '汎用カウンタ1'): '汎用カウンタ',
    }

    def __init__(self, bhe_terms, dx_terms, rep):
        self.B, self.D, self.rep = bhe_terms, dx_terms, rep
        self.dcode = {g['termGroupCodeName']: i for i, g in enumerate(dx_terms)}

    def group(self, bg):
        code = self.B[bg]['termGroupCodeName']
        if code not in self.dcode:
            self.rep.add('TERM_UNMAPPED', 'group %s' % code)
            return None
        return self.dcode[code]

    def item(self, bg, dg, idx):
        bi = self.B[bg]['termItemList']
        if not (0 <= idx < len(bi)):
            self.rep.add('TERM_UNMAPPED', 'BHE %s item %d out of range' % (self.B[bg]['termGroupCodeName'], idx))
            return 0
        name = bi[idx]['termItemName']
        occ = sum(1 for x in bi[:idx] if x['termItemName'] == name)
        name = self.ALIAS.get((self.B[bg]['termGroupCodeName'], name), name)
        cand = [j for j, x in enumerate(self.D[dg]['termItemList']) if x['termItemName'] == name]
        if len(cand) > occ:
            return cand[occ]
        if cand:
            return cand[0]
        self.rep.add('TERM_UNMAPPED', '%s「%s」 (no BSDX item; -> 0)' % (self.B[bg]['termGroupCodeName'], bi[idx]['termItemName']))
        return 0

    def objpos(self, idx, which):
        """intList3/4 pairs: (OBJECTPOS idx, OBJECTPOS2 idx)"""
        code = ('OBJECTPOS', 'OBJECTPOS2')[which]
        bg = [i for i, g in enumerate(self.B) if g['termGroupCodeName'] == code][0]
        return self.item(bg, self.dcode[code], idx)

    def remap(self, t, hit_attack=False):
        """t: one BheInfoCollection dict (already renamed to bsdx keys). In-place."""
        bg = t['int1']
        if hit_attack and self.B[bg]['termGroupCodeName'] == 'PARAM':
            # BHE Hit[6] attack term uses PARAM(22) '直値'; BSDX uses ATTACK2(21) '直値指定' (2792/2792 original hits)
            dg = self.dcode['ATTACK2']
            tl = t.get('typeList') or []
            if tl and tl[0] != 0:
                self.rep.add('TERM_UNMAPPED', 'hit attack term PARAM item %d (only 直値 supported) -> 0' % tl[0])
            t['int1'] = dg
            if tl:
                tl[0] = 0
            self.rep.add('TERM_INFO', 'hit attack term PARAM(22)->ATTACK2(21)')
            return
        dg = self.group(bg)
        if dg is None:
            return
        t['int1'] = dg
        tl = t.get('typeList') or []
        cb, cd = bg, dg
        for k in range(len(tl)):
            if cb is None or cb < 0:
                self.rep.add('TERM_UNMAPPED', 'typeList longer than grammar %s' % tl)
                break
            j = self.item(cb, cd, tl[k])
            nb = self.B[cb]['termItemList'][tl[k]]['param2'] if 0 <= tl[k] < len(self.B[cb]['termItemList']) else -3
            nd = self.D[cd]['termItemList'][j]['param2']
            tl[k] = j
            if nb >= 0:
                if nd < 0 or self.B[nb]['termGroupCodeName'] != self.D[nd]['termGroupCodeName']:
                    self.rep.add('TERM_UNMAPPED', 'grammar mismatch after %s' % self.B[cb]['termGroupCodeName'])
                    break
                cb, cd = nb, nd
            else:
                cb = cd = None
        for key in ('intList3', 'intList4'):
            L = t.get(key) or []
            if len(L) >= 1:
                L[0] = self.objpos(L[0], 0)
            if len(L) >= 2:
                L[1] = self.objpos(L[1], 1)

    def remap_all(self, obj):
        """remap every info collection below obj; Hit unit 6 terms get the attack special-case"""
        for d in walk(obj):
            for hu in d.get('ceventHitUnitList') or []:
                if hu.get('unitSlotNum') == 6 and hu.get('data'):
                    for t in hu['data'].get('bsdxInfoCollectionList') or []:
                        t['_hit'] = 1
        for d in walk(obj):
            for k in ('bsdxInfoCollectionList', 'bsdxInfoCollectionList1', 'bsdxInfoCollectionList2'):
                for t in d.get(k) or []:
                    if isinstance(t, dict) and 'int1' in t and '_done' not in t:
                        self.remap(t, hit_attack=bool(t.pop('_hit', 0)))
                        t['_done'] = 1
        for d in walk(obj):
            for k in ('bsdxInfoCollectionList', 'bsdxInfoCollectionList1', 'bsdxInfoCollectionList2'):
                for t in d.get(k) or []:
                    if isinstance(t, dict):
                        t.pop('_done', None)


def jump_refs(obj, term_root_group_jump=16):
    """yield the info-collection dicts that are Term JUMP '技ジャンプ' (paramList = [wazFileNo, skillNo]).
    Works on BHE (bhe keys) and BSDX JSON (JUMP is group 16 in both)."""
    for d in walk(obj):
        for k, v in d.items():
            if 'InfoCollectionList' in k and isinstance(v, list):
                for t in v:
                    if isinstance(t, dict) and t.get('int1') == term_root_group_jump and (t.get('typeList') or [None])[0] == 1 \
                            and len(t.get('paramList') or []) >= 2:
                        yield t


# ------------------------------------------------------------------------------------------------ AI
# NeXAS_DX's BHE CCpuEvent DTO reuses BSDX field names, but the real BHE layout has one BHE-only int first and a
# BHE-only short in the middle (verified on tsukuyomi: BHE int27/int28/int29 carry the BSDX int25/int26/int27 bit masks
# 8255/255/133056-style values; BHE rangeMin is the constant 100 = BSDX int5, etc.). Mapping (BSDX <- BHE DTO name):
_AI_SEQ_DX = ['activationProbability', 'activationProbabilityWhenCounter', 'int5', 'activationRangeMin', 'activationRangeMax',
              'activationAngleRangeMin', 'activationAngleRangeMax', 'activationAltitudeMin', 'activationAltitudeMax',
              'activationDurabilityMinPercentage', 'activationDurabilityMaxPercentage', 'int14', 'int15', 'activationHeatMin',
              'activationHeatMax', 'int18', 'int19', 'int20', 'int21', 'int22', 'int23', 'int24']
_AI_SEQ_BHE = _AI_SEQ_DX[1:] + ['int25']
AI_MAP = dict(zip(_AI_SEQ_DX, _AI_SEQ_BHE))
AI_MAP.update({'int25': 'int27', 'int26': 'int28', 'short2': 'short3', 'int27': 'int29', 'int28': 'int30',
               'short3': 'short4', 'short4': 'short5'})
AI_BHE_ONLY = ['activationProbability(BHE 1st int)', 'short2(BHE)', 'byte1', 'positionX', 'positionY']
MOVE_KEYS = ['moveType', 'moveSpeed', 'moveInertia', 'moveTargetType', 'moveTargetAngleCorrection', 'viewpointType',
             'viewpointAngleCorrection', 'jumpType', 'ascentVar1', 'ascentVar2', 'genericFlag', 'attackProbabilityCorrection']


def ai_event(bhe_ev, termmap, rep):
    """BHE CCpuEvent JSON (bhe_rt / BHE parser) -> BSDX CCpuEvent JSON dict"""
    e = {'type': bhe_ev['type'], 'short1': bhe_ev['short1'], 'int1': bhe_ev['int1'], 'int2': bhe_ev['int2']}
    if bhe_ev['type'] == 1:
        for k in MOVE_KEYS:
            e[k] = bhe_ev[k]
        if bhe_ev.get('positionX') or bhe_ev.get('positionY'):
            rep.add('AI_DROPPED', 'move positionX/Y non-zero (%s,%s)' % (bhe_ev.get('positionX'), bhe_ev.get('positionY')))
    elif bhe_ev['type'] == 2:
        e['mekWeaponInfoMapNo'] = bhe_ev['mekWeaponInfoMapNo']
    for dk, bk in AI_MAP.items():
        e[dk] = bhe_ev[bk]
    for bk, nm in (('activationProbability', 'BHE first int'), ('short2', 'BHE middle short'), ('byte1', 'BHE byte1')):
        rep.add('AI_DROPPED', '%s=%s' % (nm, bhe_ev.get(bk)))
    terms = json.loads(json.dumps(bhe_ev.get('bheInfoCollectionList') or []))
    for t in terms:
        termmap.remap(t)
    e['bsdxInfoCollectionList'] = terms
    return e


# ------------------------------------------------------------------------------------------------ closure
def shared_closure(root_waz, bhe_shared, n_shared=8, self_file=None, rep=None, follow=None):
    """BHE shared skills (file,seq) reachable from root_waz via WazaSelect and JUMP-技ジャンプ.
    follow(f,q) -> bool decides whether refs inside that shared skill are followed (False when it will be mapped onto
    an existing BSDX skill of the same name, whose own internals are already BSDX-consistent)."""
    need, todo = set(), [s for s in root_waz['skillList'] if s]

    def refs(s):
        for d in walk(s):
            if 'wazFileNo' in d and 'wazSequenceNo' in d:
                yield d['wazFileNo'], d['wazSequenceNo']
        for t in jump_refs(s):
            yield t['paramList'][0], t['paramList'][1]

    while todo:
        s = todo.pop()
        for f, q in refs(s):
            if 0 <= f < n_shared:
                if (f, q) not in need:
                    need.add((f, q))
                    sk = bhe_shared[f]['skillList'][q] if q < len(bhe_shared[f]['skillList']) else None
                    if sk is None:
                        rep.add('CLOSURE', 'missing BHE shared skill %s' % ((f, q),))
                    elif follow is None or follow(f, q):
                        todo.append(sk)
            elif f != self_file and f != -1:
                rep.add('CLOSURE', 'ref to other BHE waz file %d (not shared, not self)' % f)
    return need


# ------------------------------------------------------------------------------------------------ refs
class RefMap:
    """holds all BHE->BSDX index maps and applies them to (converted) waz JSON"""

    def __init__(self, rep):
        self.rep = rep
        self.waz = {}       # (bheFile, bheSeq) -> (dxFile, dxSeq)
        self.wazfile = {}   # bheFile -> dxFile (whole-file, e.g. self waz)
        self.sprgroup = {}  # bheGroup -> dxGroup
        self.anim_sub = {}  # (bheGroup, anim) -> (dxGroup, dxAnim)
        self.se = {}        # (bheCat, item) -> (dxCat, item)
        self.voice_char = {}  # bheChar -> (dxChar, offset)
        self.valid_sprite = None  # callback(dxGroup, anim, pattern) -> bool, used to drop impossible preload pairs

    def map_waz(self, f, q):
        if (f, q) in self.waz:
            return self.waz[(f, q)]
        if f in self.wazfile:
            return self.wazfile[f], q
        if f == -1:
            return f, q
        self.rep.add('REF_UNMAPPED', 'waz %s' % ((f, q),))
        return f, q

    def map_sprite(self, g, a, p):
        if g == -1:
            return g, a, p
        if (g, a) in self.anim_sub:
            dg, da = self.anim_sub[(g, a)]
            self.rep.add('SPRITE_SUBST', 'BHE g%d anim %d -> BSDX g%d anim %d' % (g, a, dg, da))
            return dg, da, p
        if g in self.sprgroup:
            return self.sprgroup[g], a, p
        self.rep.add('REF_UNMAPPED', 'sprite group %d' % g)
        return g, a, p

    def map_se(self, c, i):
        if (c, i) in self.se:
            return self.se[(c, i)]
        self.rep.add('REF_UNMAPPED', 'SE %s' % ((c, i),))
        return c, i

    def apply_waz(self, obj, se_t=23, vo_t=24):
        """in-place on BSDX-typed JSON (after JsonTransWaz): WazaSelect, JUMP params, sprite, SE, voice"""
        for d in walk(obj):
            if 'wazFileNo' in d and 'wazSequenceNo' in d:
                d['wazFileNo'], d['wazSequenceNo'] = self.map_waz(d['wazFileNo'], d['wazSequenceNo'])
            elif 'spmFileSequence' in d and 'actionGroupNumber' in d:
                d['spmFileSequence'], d['actionGroupNumber'], d['actionNumber'] = self.map_sprite(
                    d['spmFileSequence'], d['actionGroupNumber'], d['actionNumber'])
            elif d.get('typeId') == se_t and 'byteDataList' in d:
                for raw in d['byteDataList']:
                    c, i = self.map_se(i32(raw, 0), i32(raw, 1))
                    set_i32(raw, 0, c); set_i32(raw, 1, i)
            elif d.get('typeId') == vo_t and 'byteDataList' in d:
                for raw in d['byteDataList']:
                    ch = i32(raw, 0)
                    if ch in self.voice_char:
                        dc, off = self.voice_char[ch]
                        set_i32(raw, 0, dc); set_i32(raw, 1, i32(raw, 1) + off)
                    else:
                        self.rep.add('REF_UNMAPPED', 'voice char %d' % ch)
        for t in jump_refs(obj):
            t['paramList'][0], t['paramList'][1] = self.map_waz(t['paramList'][0], t['paramList'][1])

    def material(self, bhe_mb, dims, rep):
        """BHE MaterialBlock JSON -> BSDX one with dims (nSprite, nSe, nVoice)"""
        out = []
        for e in bhe_mb['entries']:
            spr = [[] for _ in range(dims[0])]
            se = [[] for _ in range(dims[1])]
            vo = [[] for _ in range(dims[2])]
            for g, ids in enumerate(e['spriteGroups']):
                for k in range(0, len(ids), 2):
                    dg, da, dp = self.map_sprite(g, ids[k], ids[k + 1])
                    if self.valid_sprite and not self.valid_sprite(dg, da, dp):
                        rep.add('MATERIAL_DROPPED', 'preload BHE(%d,%d,%d) -> (%d,%d,%d) not in the BSDX spm (unused by the port waz)' % (g, ids[k], ids[k + 1], dg, da, dp))
                        continue
                    if (da, dp) not in zip(spr[dg][0::2], spr[dg][1::2]):
                        spr[dg] += [da, dp]
            for c, ids in enumerate(e['seGroups']):
                for it in ids:
                    dc, di = self.map_se(c, it)
                    if di not in se[dc]:
                        se[dc].append(di)
            for c, ids in enumerate(e['voiceGroups']):
                for it in ids:
                    if c not in self.voice_char:
                        rep.add('REF_UNMAPPED', 'material voice char %d' % c); continue
                    dc, off = self.voice_char[c]
                    vo[dc].append(it + off)
            out.append({'offset': 0, 'length': 0, 'spriteGroups': spr, 'seGroups': se, 'voiceGroups': vo})
        reg = bhe_mb['regularCount']
        return {'extraRegularCount': reg - 7, 'regularCount': reg, 'entries': out,
                'regularEntries': out[:reg], 'trailingEntries': out[reg:]}


def sprite_refs(obj):
    for d in walk(obj):
        if 'spmFileSequence' in d and 'actionGroupNumber' in d:
            yield d['spmFileSequence'], d['actionGroupNumber'], d['actionNumber']
