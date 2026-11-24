#!/usr/bin/env python3
"""Phase 3A: BALDR HEART EXE ツクヨミ (桜火 / 月詠) -> BALDR SKY DiveX, registered as mech ID 10 (Update3.pac).

Usage: build_phase3a.py [--variant enemy]      (cloud container; ~2 min)
  default        -> mods/phase3a_tsukuyomi/files + Update3.pac
  --variant enemy -> mods/phase3a_tsukuyomi/variantB_enemy/{files,Update3.pac}: same + ツクヨミ appears as an enemy in
                     究極サバイバル from an early wave (SurvivalMekaMain.dat row)
Prereq: tools/build_nexas_dx.sh (with the hit-area fix) has been run.
Inputs: NeXAS_DX BHE data (mek/waz/spm/grp), work/bhe_tsukuyomi(+_deps) assets, work/bhe_tsukuyomi_fx (BHE shared-effect
        png + tama/bomb/mark/pic.spm), work/extracted (BSDX originals, Update wins), NeXAS_DX bsdx/spm (Bmp/System.pac
        spm originals), mods/phase0_test/files.
Intermediate: /path/to/workspace/work/phase3a/ (raw Java conversions, JSON, report.txt)
Decisions and approximations: notes/08_tsukuyomi_port.md
"""
import os, sys, json, copy, shutil, subprocess, collections, filecmp
sys.path.insert(0, '/path/to/workspace/tools'); sys.path.insert(0, '/path/to/workspace/tools/port')
import bsdx_dat
from bhe2bsdx import Report, TermMap, RefMap, porttool, jload, jsave, glist, walk, ai_event, shared_closure, sprite_refs, jump_refs
import spm_append, material_images

VARIANT = sys.argv[sys.argv.index('--variant') + 1] if '--variant' in sys.argv else None
P = '/path/to/workspace'
T = P + '/tools'
BHE = '/path/to/ext/NeXAS_DX/src/main/resources/game/bhe'
DXSPM = '/path/to/ext/NeXAS_DX/src/main/resources/game/bsdx/spm'
EX = P + '/work/extracted'
ASSET = P + '/work/bhe_tsukuyomi'
DEPS = P + '/work/bhe_tsukuyomi_deps'
FX = P + '/work/bhe_tsukuyomi_fx'
P0 = P + '/mods/phase0_test/files'
W = P + '/work/phase3a'
MOD = P + '/mods/phase3a_tsukuyomi'
OUT = MOD + ('/variantB_enemy' if VARIANT == 'enemy' else '')
FILES = OUT + '/files'

MECH = 'tsukuyomi'              # BHE names (mek/waz/spm)
NEW_ID = 10                     # MekaGroup slot (unused Sora2)
MEKA_NAME, MEKA_CODE = 'Tsukuyomi', 'TSUKUYOMI'
WAZ_NAME = 'Tsukuyomi'          # WazaGroup display/file name -> Tsukuyomi.waz
SPR_SLOT = 133                  # free SpriteGroup slot (133-136 empty in BSDX)
VOICE_CHAR = 6                  # BatVoice[6] 空 (SORA): 64 entries appended (offset = old count). Sora2 (old ID 10) is gone
SE_CAT = 11                     # empty SeGroup category -> new "port SE" category for SE files BSDX lacks
VICTIM_ROW = 27                 # SelectMekaMenu row lent by 晴嵐 (ID 97), same as phase 1
VICTIM_ID = 97
COIN = 150                      # Meka.dat c1 (player coin multiplier; Sora 140 / Mohawk 150)
# initial loadout (WeaponEquip row 10): slots 0-8 melee, 9-11 ranged, 12-13 FC (BHE ツクヨミ has no initializer)
LOADOUT = [2, 3, 4, 5, 6, 7, 8, 0, 9, 10, 11, 12, 13, 14]  # 袈裟 薙払 打突 唐竹 逆風 切返 一威 抜刀 回避 銃撃 銀鈴 疾風 | 穿心 煉撃
HIDDEN_WEAPONS = [15, 16, 17]   # SCRIPT:納刀/唐竹/切返 -> weaponIdentifier 2 (hidden), like BSDX "SCRIPT:" weapons
# BHE shared-sprite animations that the BSDX shared spm lack (BSDX tama/bomb/mark/pic.spm are shorter than BHE's).
# They are APPENDED (with their pages and BHE png) to the end of the BSDX spm of the same name by tools/port/spm_append.py
# (original bytes kept; Tama.spm's tail = anim-table copy gets the same anims) and the refs are remapped to the new
# indices. BHE group -> BHE anim numbers. Groups: 0 Tama, 1 bomb, 4 Mark, 5 Pic. (Until 2026-10-23 these 21 anims were
# substituted by similar BSDX anims, table ANIM_SUB; see 調査記録 08 §4.)
FX_ANIMS = {
    0: [195, 231],                      # 弾108（発射01）, 月詠_鈴弾
    1: [97],                            # 爆発63
    4: [218, 225, 226, 227, 228, 229, 230, 231, 232, 237, 250, 251, 252, 253],   # 回復01, B6ヒットエフェクト×8, 花火, 線火花01-04
    5: [207, 217],                      # 絵奈の世界・岩, 桜
}
MARKER_OLD, MARKER_NEW = '【MODテスト】', '【MODテストTSUKU】'

rep = Report()
for d in (W + '/raw/pipe', W + '/json/bhe/grp', W + '/json/bhe/waz', W + '/json/bhe/mek', W + '/json/bhe/spm', W + '/json/dx', W + '/json/raw',
          W + '/check/grp', W + '/check/waz', W + '/check/mek', W + '/check/spm'):
    os.makedirs(d, exist_ok=True)
if os.path.isdir(FILES):
    shutil.rmtree(FILES)
os.makedirs(FILES)

# =============================================================================================== A. Java conversions
L = '/opt/gradle-8.14.3/lib'
B = T + '/nexas_build'
CP = ':'.join([B + '/harness', B + '/testclasses', B + '/classes', T + '/libs/hutool-core-json-5.8.17-src-build.jar',
               L + '/jackson-databind-2.16.1.jar', L + '/jackson-core-2.16.1.jar', L + '/jackson-annotations-2.16.1.jar', L + '/slf4j-api-1.7.36.jar'])
ENV = dict(os.environ, LC_ALL='C.UTF-8', JAVA_TOOL_OPTIONS='')
SHARED_BHE = ['effect', 'tama01', 'tama02', 'tama03', 'tama04', 'tama05', 'laser', 'bomb']   # BHE WazaGroup 0..7
def java(*a):
    r = subprocess.run(['java', '-Xmx6g', '-cp', CP] + list(a), capture_output=True, text=True, env=ENV)
    if r.returncode or 'FAIL' in r.stdout:
        raise SystemExit(r.stdout[-3000:] + r.stderr[-3000:])
    return r.stdout
print('A. Java conversions ...')
for m in [MECH, 'effect', 'tama03', 'tama05', 'bomb']:
    o = java('JsonTransWaz', BHE, W + '/raw', m)
    rep.add('JAVA', 'JsonTransWaz %s: %s' % (m, [l for l in o.splitlines() if l.startswith('DROPPED')]))
r = subprocess.run(['java', '-Xmx6g', '-DfixAi=true', '-cp', CP, 'RunTsukuyomiPipeline', BHE, W + '/raw/pipe', MECH], capture_output=True, text=True, env=ENV)
assert 'OK   transMeka' in r.stdout, r.stdout   # (its transWaza step is the known-broken upstream one; we use JsonTransWaz)
jobs = [['spm', BHE + '/spm/%s.spm' % n, W + '/raw/%s.spm' % n] for n in (MECH, 'c_' + MECH, 'g_' + MECH, 'm_' + MECH)]
jobs += [['b2j', 'bsdx', W + '/raw/%s.waz' % m, W + '/json/raw/%s.waz.json' % m] for m in [MECH, 'effect', 'tama03', 'tama05', 'bomb']]
jobs += [['b2j', 'bsdx', W + '/raw/pipe/%s.mek' % MECH, W + '/json/raw/%s.mek.json' % MECH],
         ['b2j', 'bsdx', W + '/raw/%s.spm' % MECH, W + '/json/raw/%s.spm.json' % MECH]]
for g in ['WazaGroup', 'SpriteGroup', 'SeGroup', 'BatVoice', 'MekaGroup', 'Term']:
    jobs.append(['b2j', 'bsdx', EX + '/Dat/%s.grp' % g, W + '/json/dx/%s.grp.json' % g])
DX_SHARED_SRC = {'Effect': EX + '/Dat/Effect.waz', 'Tama03': EX + '/Dat/Tama03.waz', 'Tama05': EX + '/Update/Tama05.waz', 'Bomb': EX + '/Update/Bomb.waz'}
for n, f in DX_SHARED_SRC.items():
    jobs.append(['b2j', 'bsdx', f, W + '/json/dx/%s.waz.json' % n])
for n in ['Tama', 'bomb', 'Elec', 'Smoke', 'Mark', 'Pic', 'Link', 'Fire', 'Wind', 'SelectMekaMenuMeka']:
    jobs.append(['b2j', 'bsdx', DXSPM + '/%s.spm' % n, W + '/json/dx/%s.spm.json' % n])
for g in ['wazagroup', 'spritegroup', 'segroup', 'batvoice', 'term']:
    jobs.append(['b2j', 'bhe', BHE + '/grp/%s.grp' % g, W + '/json/bhe/grp/%s.grp.json' % g])
FX_BHE_NAME = {0: 'tama', 1: 'bomb', 4: 'mark', 5: 'pic'}     # work/bhe_tsukuyomi_fx/<name>.spm (BHE Update.pac versions)
jobs += [['spm', FX + '/%s.spm' % FX_BHE_NAME[g], W + '/raw/fx_%s.spm' % FX_BHE_NAME[g]] for g in FX_ANIMS]   # BHE -> BSDX format
for m in [MECH] + SHARED_BHE:
    jobs.append(['b2j', 'bhe', BHE + '/waz/%s.waz' % m, W + '/json/bhe/waz/%s.waz.json' % m])
jobs.append(['b2j', 'bhe', BHE + '/mek/%s.mek' % MECH, W + '/json/bhe/mek/%s.mek.json' % MECH])
for n in ['tama', 'bomb', 'smoke', 'mark', 'pic', 'link', 'wind', 's_' + MECH]:
    jobs.append(['b2j', 'bhe', BHE + '/spm/%s.spm' % n, W + '/json/bhe/spm/%s.spm.json' % n])
porttool(*jobs)

# =============================================================================================== B. registries
print('B. remap tables ...')
bj = lambda k, n: jload(W + '/json/bhe/%s/%s.%s.json' % (k, n, k))
dj = lambda n, k: jload(W + '/json/dx/%s.%s.json' % (n, k))
BWG, BSG, BSE = glist(bj('grp', 'wazagroup')), glist(bj('grp', 'spritegroup')), glist(bj('grp', 'segroup'))
BBV = bj('grp', 'batvoice')['voiceList']
BTERM = bj('grp', 'term')['termList']
WGj, SGj, SEj, BVj, MGj = dj('WazaGroup', 'grp'), dj('SpriteGroup', 'grp'), dj('SeGroup', 'grp'), dj('BatVoice', 'grp'), dj('MekaGroup', 'grp')
WG, SG, SE, BV, MG = glist(WGj), glist(SGj), glist(SEj), BVj['voiceList'], glist(MGj)
DTERM = dj('Term', 'grp')['termList']
assert len(WG) == 110 and len(SG) == 138 and len(SE) == 38 and len(BV) == 30 and len(MG) == 103
DIMS = (len(SG), len(SE), len(BV))
termmap = TermMap(BTERM, DTERM, rep)
rm = RefMap(rep)

BSELF = [i for i, x in enumerate(BWG) if (x.get('wazaDisplayName') or '').lower() == MECH][0]   # 11
WAZ_IDX = len(WG)                                                                              # 110
rm.wazfile[BSELF] = WAZ_IDX
BSPR_SELF = [i for i, x in enumerate(BSG) if (x.get('spriteFileName') or '').lower() == MECH + '.spm'][0]   # 13
dxspr = {(x.get('spriteFileName') or '').lower(): i for i, x in enumerate(SG) if x.get('existFlag')}
for i, x in enumerate(BSG):
    if x.get('existFlag') and (x.get('spriteFileName') or '').lower() in dxspr:
        rm.sprgroup[i] = dxspr[x['spriteFileName'].lower()]
rm.sprgroup[BSPR_SELF] = SPR_SLOT
# ---- real BHE shared effects: append the needed anims (+ pages, png) to the BSDX shared spm, remap to the new indices
os.makedirs(W + '/fx', exist_ok=True); os.makedirs(W + '/json/fx', exist_ok=True)
FX_OUT = {}         # BSDX group -> {'file', 'info'}
for bg, ids in FX_ANIMS.items():
    dg = rm.sprgroup[bg]; fn = SG[dg]['spriteFileName']
    assert fn.lower() == BSG[bg]['spriteFileName'].lower() == FX_BHE_NAME[bg] + '.spm'
    base = open(DXSPM + '/' + fn, 'rb').read()
    donor = open(W + '/raw/fx_%s.spm' % FX_BHE_NAME[bg], 'rb').read()
    out, info = spm_append.append(base, donor, ids)
    spm_append.verify_append(base, out, info)     # original bytes recoverable exactly; tail kept (Tama: anim-table copy)
    open(W + '/fx/' + fn, 'wb').write(out)
    FX_OUT[dg] = {'file': fn, 'info': info}
    for a in ids:
        rm.anim_sub[(bg, a)] = (dg, info['anim_map'][a])
        rep.add('FX_APPEND', '%s: BHE anim %d「%s」-> new anim %d' % (fn, a, info['anim_names'][a], info['anim_map'][a]))
    rep.add('FX_APPEND', '%s: %d -> %d B, +%d pages +%d images %s, tail %s %d B' % (fn, len(base), len(out), info['n_pages'],
            len(info['images']), info['images'], info['tail_kind'] or 'none', info['tail_len']))
porttool(*[['b2j', 'bsdx', W + '/fx/' + x['file'], W + '/json/fx/%s.json' % x['file']] for x in FX_OUT.values()])
FX_PNG = sorted({nm for x in FX_OUT.values() for nm in x['info']['images']})
assert all(os.path.exists(FX + '/' + nm) for nm in FX_PNG), 'missing BHE effect png'
print('   real BHE effects appended: %s (%d png)' % (', '.join('%s +%d' % (x['file'], len(x['info']['anim_map'])) for x in FX_OUT.values()), len(FX_PNG)))

# ---- shared waz closure + reuse-by-name / append
BW = {i: bj('waz', SHARED_BHE[i]) for i in range(8)}
DXW = {0: 'Effect', 1: 'Tama01', 2: 'Tama02', 3: 'Tama03', 4: 'Tama04', 5: 'Tama05', 6: 'Laser', 7: 'Bomb'}
dxname = {}
def dx_names(f):
    if f not in dxname:
        w = jload(P + '/work/nexas_rt/json/waz/%s.waz.json' % DXW[f]) if DXW[f] not in ('Effect', 'Tama03', 'Tama05', 'Bomb') else dj(DXW[f], 'waz')
        dxname[f] = {}
        for j, s in enumerate(w['skillList']):
            if s and s.get('skillNameJapanese') is not None:
                dxname[f].setdefault(s['skillNameJapanese'], j)
    return dxname[f]
bname = lambda f, q: BW[f]['skillList'][q].get('skillNameJapanese')
root_bhe = bj('waz', MECH)
need = shared_closure(root_bhe, BW, 8, BSELF, rep, follow=lambda f, q: bname(f, q) not in dx_names(f))
append = collections.defaultdict(list)
for f, q in sorted(need):
    j = dx_names(f).get(bname(f, q))
    if j is not None:
        rm.waz[(f, q)] = (f, j); rep.add('SHARED_REUSE', '%s[%d]「%s」-> BSDX[%d]' % (DXW[f], q, bname(f, q), j))
    else:
        append[f].append(q)
DXSH = {f: dj(DXW[f], 'waz') for f in append}
for f, qs in append.items():
    base = len(DXSH[f]['skillList']); assert base == WG[f]['param'], (f, base, WG[f]['param'])
    for k, q in enumerate(qs):
        rm.waz[(f, q)] = (f, base + k); rep.add('SHARED_APPEND', '%s[%d]「%s」-> BSDX[%d]' % (DXW[f], q, bname(f, q), base + k))
print('   shared skills: %d needed, append %s' % (len(need), {DXW[f]: len(q) for f, q in append.items()}))

# ---- converted (BSDX-typed, BHE-valued) waz JSON
raw_root = jload(W + '/json/raw/%s.waz.json' % MECH)
raw_sh = {f: jload(W + '/json/raw/%s.waz.json' % SHARED_BHE[f]) for f in append}
app_skills = {f: [copy.deepcopy(raw_sh[f]['skillList'][q]) for q in qs] for f, qs in append.items()}
for f, qs in append.items():
    for q, s in zip(qs, app_skills[f]):
        assert s['skillNameJapanese'] == bname(f, q)

# ---- SE: by file name (case-insensitive) against BSDX SeGroup; missing -> new category SE_CAT
dxse = {}
for c, cat in enumerate(SE):
    for i, it in enumerate(cat.get('seItems') or []):
        if it.get('existFlag'):
            dxse.setdefault((it.get('seFileName') or '').lower(), (c, i))
def bse_item(c, i):
    return BSE[c]['seItems'][i]
assert not SE[SE_CAT].get('existFlag')
newse = []
def need_se(c, i):
    if (c, i) in rm.se:
        return
    it = bse_item(c, i)
    fn = it.get('seFileName')
    if fn and fn.lower() in dxse:
        rm.se[(c, i)] = dxse[fn.lower()]
    else:
        rm.se[(c, i)] = (SE_CAT, len(newse)); newse.append((c, i, it))
from bhe2bsdx import i32
for obj in [raw_root] + [s for L_ in app_skills.values() for s in L_]:
    for d in walk(obj):
        if d.get('typeId') == 23 and 'byteDataList' in d:
            for raw in d['byteDataList']:
                need_se(i32(raw, 0), i32(raw, 1))
bmek = bj('mek', MECH)
for e in bmek['mekMaterialBlock']['entries']:
    for c, ids in enumerate(e['seGroups']):
        for it in ids:
            need_se(c, it)
SE_ASSETS = {f.lower(): DEPS + '/' + f for f in os.listdir(DEPS) if f.endswith('.ogg')}
for c, i, it in newse:
    rep.add('SE_NEW', '(%d,%d) %s -> SeGroup[%d][%d]%s' % (c, i, it['seFileName'], SE_CAT, rm.se[(c, i)][1],
            '' if it['seFileName'].lower() + '.ogg' in SE_ASSETS else '  ** ogg MISSING **'))
assert all(it['seFileName'].lower() + '.ogg' in SE_ASSETS for c, i, it in newse), 'missing SE ogg'

# ---- voice: BHE BatVoice[1] TSUKUYOMI (64 entries) appended to BSDX char VOICE_CHAR
BV_SELF = bmek['mekVoiceInfo']['version']
assert BBV[BV_SELF]['characterCodeName'] == 'TSUKUYOMI'
VOFF = len(BV[VOICE_CHAR]['voices'])
rm.voice_char[BV_SELF] = (VOICE_CHAR, VOFF)

# =============================================================================================== C. apply to waz
print('C. waz ...')
def fix_waz(obj):
    rm.apply_waz(obj)
    termmap.remap_all(obj)
    for d in walk(obj):
        # CEventBlink (残像, BSDX slot 49): upstream mapper puts BHE int9 (=512 here) into BSDX short1, whose vanilla values
        # are only 0/2/3 (435/2/1) -> 0 (plain afterimage). The misaki MOD changed the same 512 to 3.
        if d.get('typeId') == 20 and d.get('slotNum') == 49 and d.get('short1') not in (0, 2, 3):
            rep.add('VALUE_FIX', 'CEventBlink.short1 %s -> 0' % d['short1']); d['short1'] = 0
fix_waz(raw_root)
for f in app_skills:
    for s in app_skills[f]:
        fix_waz(s)
raw_root['fileName'] = WAZ_NAME
final_waz = {WAZ_NAME: raw_root}
for f, L_ in app_skills.items():
    w = DXSH[f]; w['skillList'] += L_; final_waz[DXW[f]] = w

# ---- sprite validation (every waz + material ref): anim/pattern in range, name equal to BHE unless substituted
dxspm = {}
def dx_spm(g):
    if g not in dxspm:
        dxspm[g] = (jload(W + '/json/raw/%s.spm.json' % MECH) if g == SPR_SLOT else
                    jload(W + '/json/fx/%s.json' % FX_OUT[g]['file']) if g in FX_OUT else dj(SG[g]['spriteFileName'][:-4], 'spm'))
    return dxspm[g]
bhespm = {}
def bhe_spm(g):
    if g not in bhespm:
        bhespm[g] = bj('spm', BSG[g]['spriteFileName'][:-4].lower())
    return bhespm[g]
def check_sprite_pairs(pairs, where):
    for (bg, ba, bp) in pairs:
        if bg == -1:
            bg = BSPR_SELF
        dg, da, dp = rm.map_sprite(bg, ba, bp)
        s = dx_spm(dg)
        if not (0 <= da < len(s['animData'])) or not (0 <= dp < max(1, s['animData'][da]['numPat'])):
            rep.add('SPRITE_BAD', '%s BHE(%d,%d,%d)->(%d,%d,%d) out of range' % (where, bg, ba, bp, dg, da, dp)); continue
        if bg != BSPR_SELF:       # shared sprites: same anim name as BHE (also for the appended real effects)
            bn = bhe_spm(bg)['animData'][ba]['animName'].strip(); dn = s['animData'][da]['animName'].strip()
            if bn != dn:
                rep.add('SPRITE_BAD', '%s BHE g%d anim %d「%s」!= BSDX「%s」' % (where, bg, ba, bn, dn))
rawpairs = []
for obj in [jload(W + '/json/raw/%s.waz.json' % MECH)] + [raw_sh[f]['skillList'][q] for f, qs in append.items() for q in qs]:
    rawpairs += list(sprite_refs(obj))
check_sprite_pairs(rawpairs, 'waz')
mpairs = [(g, ids[k], ids[k + 1]) for e in bmek['mekMaterialBlock']['entries'] for g, ids in enumerate(e['spriteGroups']) for k in range(0, len(ids), 2)]
# material preload pairs: a pair whose anim does not exist in the BSDX spm is dropped (it is BHE-common smoke etc. used
# only by BHE versions of shared skills that the port maps onto the BSDX versions); it must not be used by the port waz.
used_final = set()
for w in [raw_root] + [s for L_ in app_skills.values() for s in L_]:
    for g, a, p_ in sprite_refs(w):
        used_final.add((SPR_SLOT if g == -1 else g, a, p_))
def valid_sprite(g, a, p_):
    s = dx_spm(g)
    ok = 0 <= a < len(s['animData']) and 0 <= p_ < max(1, s['animData'][a]['numPat'])
    assert ok or (g, a, p_) not in used_final
    return ok
rm.valid_sprite = valid_sprite

# =============================================================================================== D. mek
print('D. mek ...')
mek = jload(W + '/json/raw/%s.mek.json' % MECH)
bi = mek['mekBasicInfo']
bi['wazFileSequence'], bi['spmFileSequence'] = WAZ_IDX, SPR_SLOT
W_ = mek['mekWeaponInfoMap']
assert len(W_) == 18 and [W_[str(i)]['weaponName'] for i in (0, 13, 14)] == ['抜刀', '穿心', '煉撃']
for k, w in W_.items():
    bw = bmek['mekWeaponInfoMap'][k]
    assert w['wazSequence'] == bw['wazSequence'] and w['weaponName'] == bw['weaponName']
for i in HIDDEN_WEAPONS:
    assert W_[str(i)]['weaponName'].startswith('SCRIPT:'); W_[str(i)]['weaponIdentifier'] = 2
# AI: rebuilt from the BHE events with the corrected field alignment (not the name-based fixAi copy)
mek['mekAiInfoList'] = [{'aiTypeJapanese': a['aiTypeJapanese'], 'aiTypeEnglish': a['aiTypeEnglish'],
                         'cpuEventList': [ai_event(e, termmap, rep) for e in a['cpuEventList']]} for a in bmek['mekAiInfoList']]
for a in mek['mekAiInfoList']:
    for e in a['cpuEventList']:
        if e['type'] == 2:
            assert 0 <= e['mekWeaponInfoMapNo'] < len(W_), e   # 調査記録 06 §4.1 (1): the SOU crash cause
# VoiceInfo: version = BatVoice char; groupId += offset
v = copy.deepcopy(bmek['mekVoiceInfo'])
v['version'] = VOICE_CHAR
for row in v['table']:
    for col in row:
        for c in col:
            assert c['voiceType'] == -1
            c['groupId'] += VOFF
mek['mekVoiceInfo'] = {k: v[k] for k in ('version', 'emotions', 'voiceSlots', 'table', 'builtinEmotionCount') if k in v}
mek['mekMaterialBlock'] = rm.material(bmek['mekMaterialBlock'], DIMS, rep)
# BSDX MaterialBlock sprite lists are sorted IMAGE indices (BHE: anim/pattern pairs) -> convert (material_images.py)
mek['mekMaterialBlock'] = material_images.pairs_to_images(mek['mekMaterialBlock'], dx_spm, rep)
assert not material_images.check_images(mek['mekMaterialBlock'], dx_spm)
FX_IMG_IDX = {g: set(range(x['info']['image_base'], x['info']['image_base'] + len(x['info']['images']))) for g, x in FX_OUT.items()}
preloaded = {g: set() for g in FX_OUT}
for e in mek['mekMaterialBlock']['entries']:
    for g in FX_OUT:
        preloaded[g] |= set(e['spriteGroups'][g]) & FX_IMG_IDX[g]
assert preloaded == FX_IMG_IDX, ('new effect png not all preloaded', preloaded, FX_IMG_IDX)
rep.add('CHECK', 'MaterialBlock preloads every appended effect png (%s)' % {FX_OUT[g]['file']: sorted(v) for g, v in preloaded.items()})
mek['fileName'] = MEKA_NAME

# =============================================================================================== E. registries
print('E. grp ...')
for f, w in final_waz.items():
    if f != WAZ_NAME:
        WG[[i for i, x in enumerate(WG) if x.get('wazaDisplayName') == f][0]]['param'] = len(w['skillList'])
WG.append({'existFlag': 1, 'wazaName': '◆月詠', 'wazaCodeName': MEKA_CODE, 'wazaDisplayName': WAZ_NAME, 'param': len(raw_root['skillList'])})
assert not SG[SPR_SLOT].get('existFlag')
SG[SPR_SLOT] = {'existFlag': 1, 'spriteFileName': MECH + '.spm', 'spriteCodeName': MEKA_CODE, 'param': 0}
SE[SE_CAT] = {'existFlag': 1, 'seType': 'MOD:BHE移植SE（ツクヨミ）', 'seTypeCodeName': 'PORT_TSUKUYOMI',
              'seItems': [{'existFlag': 1, 'seItemName': it.get('seItemName') or it['seFileName'], 'seItemCodeName': '%04d' % k,
                           'seFileName': it['seFileName']} for k, (c, i, it) in enumerate(newse)]}
for x in BBV[BV_SELF]['voices']:
    BV[VOICE_CHAR]['voices'].append({k: x[k] for k in ('existFlag', 'voice', 'voiceCodeName', 'voiceFileName') if k in x} if x.get('existFlag') else {'existFlag': 0})
assert MG[NEW_ID] == {'existFlag': 1, 'mekaName': 'Sora2', 'mekaCodeName': 'SORA2'}
MG[NEW_ID] = {'existFlag': 1, 'mekaName': MEKA_NAME, 'mekaCodeName': MEKA_CODE}

# =============================================================================================== F. spm
print('F. spm ...')
smm = dj('SelectMekaMenuMeka', 'spm')
bs = bj('spm', 's_' + MECH)
assert len(smm['animData']) == 98
tpl_anim = smm['animData'][41]
img = len(smm['imageData']); smm['imageData'].append({'imageName': 's_%s.png' % MECH})
pages = []
for bp in bs['pageData'][:2]:      # BHE s_tsukuyomi pages 0,1 (two poses), same 1-chip layout as BSDX thumbnails
    p = copy.deepcopy(smm['pageData'][tpl_anim['patData'][0]['pageNo'][0]])
    c = p['chipData'][0]; bc = bp['chipData'][0]
    w_, h_ = bp['pageWidth'], bp['pageHeight']
    p['pageWidth'], p['pageHeight'] = w_, h_
    rect = {'left': -(w_ // 2), 'top': -(h_ // 2), 'right': w_ - w_ // 2, 'bottom': h_ - h_ // 2}
    p['pageRect'] = dict(rect)
    c.update({'imageNo': img, 'dstRect': dict(rect), 'chipWidth': w_, 'chipHeight': h_, 'srcRect': dict(bc['srcRect'])})
    pages.append(len(smm['pageData'])); smm['pageData'].append(p)
na = copy.deepcopy(tpl_anim)
na['animName'] = '月詠：TSUKUYOMI' + (tpl_anim['animName'][len(tpl_anim['animName'].rstrip('\r\n')):])
for k, pt in enumerate(na['patData']):
    pt['pageNo'] = [pages[k]]
smm['animData'].append(na)
THUMB = len(smm['animData']) - 1      # 98
for k in ('numPageData', 'numImageData', 'numAnimData'):
    smm[k] = len(smm[{'numPageData': 'pageData', 'numImageData': 'imageData', 'numAnimData': 'animData'}[k]])

# =============================================================================================== G. write + verify
print('G. generate ...')
CK = W + '/check'
gen = {  # out file name -> (json obj, check subdir)
    MEKA_NAME + '.mek': (mek, 'mek'),
    'WazaGroup.grp': (WGj, 'grp'), 'SpriteGroup.grp': (SGj, 'grp'), 'SeGroup.grp': (SEj, 'grp'), 'BatVoice.grp': (BVj, 'grp'),
    'MekaGroup.grp': (MGj, 'grp'), 'SelectMekaMenuMeka.spm': (smm, 'spm'),
}
for n, w in final_waz.items():
    gen[n + '.waz'] = (w, 'waz')
jobs = []
for n, (o, sub) in gen.items():
    jp = CK + '/%s/%s.json' % (sub, n)
    jsave(o, jp)
    jobs.append(['j2b', jp, FILES + '/' + n])
    jobs.append(['b2j', 'bsdx', FILES + '/' + n, W + '/json/back_%s.json' % n])
porttool(*jobs)
def norm(o):
    if isinstance(o, dict):
        return {k: norm(v) for k, v in o.items() if k not in ('offset', 'length', 'fileName', 'extensionName')}
    if isinstance(o, list):
        return [norm(x) for x in o]
    return o
for n, (o, sub) in gen.items():
    back = jload(W + '/json/back_%s.json' % n)
    mine = jload(CK + '/%s/%s.json' % (sub, n))
    if n.endswith('.mek'):   # MaterialBlock: parser fills regular/trailing from entries; compare entries only
        for x in (back, mine):
            x['mekMaterialBlock'] = norm(x['mekMaterialBlock']['entries'])
    if norm(back) != norm(mine):
        raise SystemExit('re-parse mismatch: ' + n)
    # also make the check dir hold the parser's view (what mek_check should see)
    jsave(back, CK + '/%s/%s.json' % (sub, n))
print('   %d generated files re-parse identically' % len(gen))
# appended shared waz: the vanilla file must be an exact byte prefix (skills are stored back to back, no count/header)
for n, src in DX_SHARED_SRC.items():
    if n in final_waz:
        a_ = open(src, 'rb').read(); b_ = open(FILES + '/%s.waz' % n, 'rb').read()
        assert b_[:len(a_)] == a_ and len(b_) > len(a_), n
print('   shared waz: vanilla bytes kept as exact prefix (%s)' % ', '.join(n for n in DX_SHARED_SRC if n in final_waz))
# shared spm with the appended real BHE effects (append-preserving writer, never regenerated by NeXAS_DX) + their png
for g, x in FX_OUT.items():
    shutil.copyfile(W + '/fx/' + x['file'], FILES + '/' + x['file'])
    orig = open(DXSPM + '/' + x['file'], 'rb').read(); new = open(FILES + '/' + x['file'], 'rb').read()
    spm_append.verify_append(orig, new, x['info'])
    shutil.copyfile(W + '/json/fx/%s.json' % x['file'], CK + '/spm/%s.json' % x['file'])   # NeXAS view, for mek_check --spm
for nm in FX_PNG:
    shutil.copyfile(FX + '/' + nm, FILES + '/' + nm)
print('   shared spm %s: original bytes preserved, NeXAS_DX parses them; %d BHE effect png' % (
    ', '.join(x['file'] for x in FX_OUT.values()), len(FX_PNG)))
# byte-converted spm (from BHE, via PortTool spm with the hit-area fix)
for src, dst in ((MECH, MECH + '.spm'), ('c_' + MECH, 'C_%s.spm' % MECH), ('g_' + MECH, 'G_%s.spm' % MECH), ('m_' + MECH, 'M_%s.spm' % MECH)):
    shutil.copyfile(W + '/raw/%s.spm' % src, FILES + '/' + dst)

# dat tables (Config.pac originals; AkisRoomItem / SelectGameMode from phase 0)
def dat_rw(src, fn, dst):
    t, r = bsdx_dat.read(open(src, 'rb').read()); fn(t, r)
    out = bsdx_dat.write(t, r); open(dst, 'wb').write(out)
    assert bsdx_dat.write(*bsdx_dat.read(out)) == out
def we(t, r):
    assert len(r) == 103 and all(x == -1 for x in r[NEW_ID]); r[NEW_ID] = list(LOADOUT)
dat_rw(EX + '/Config/WeaponEquip.dat', we, FILES + '/WeaponEquip.dat')
def smmd(t, r):
    victim = list(r[VICTIM_ROW]); assert victim[0] == VICTIM_ID and len(r) == 99
    r[VICTIM_ROW] = [NEW_ID, THUMB, -1]; r.append(victim)
dat_rw(EX + '/Config/SelectMekaMenu.dat', smmd, FILES + '/SelectMekaMenu.dat')
def mp(t, r):
    assert len(r) == 70 and r[30] == [VICTIM_ID]; r[30] = [NEW_ID]
dat_rw(EX + '/Config/MekaPilot.dat', mp, FILES + '/MekaPilot.dat')
def mk(t, r):
    assert len(r) == 99 and NEW_ID not in [x[0] for x in r]; r.append([NEW_ID, COIN])
dat_rw(EX + '/Config/Meka.dat', mk, FILES + '/Meka.dat')
def tmd(t, r):
    assert NEW_ID not in [x[0] for x in r]; sora = [x for x in r if x[0] == 9][0]; r.append([NEW_ID] + sora[1:])
dat_rw(EX + '/Config/TournamentMekaData.dat', tmd, FILES + '/TournamentMekaData.dat')
if VARIANT == 'enemy':
    def smain(t, r):
        assert r[0][0] == 4 and NEW_ID not in [x[0] for x in r]; r.insert(1, [NEW_ID, 0, 0, 1, 2, 8])
    dat_rw(EX + '/Config/SurvivalMekaMain.dat', smain, FILES + '/SurvivalMekaMain.dat')
shutil.copyfile(P0 + '/AkisRoomItem.dat', FILES + '/AkisRoomItem.dat')
def sgm(t, r):
    for x in r:
        assert x[1].startswith(MARKER_OLD); x[1] = x[1].replace(MARKER_OLD, MARKER_NEW + ('[敵]' if VARIANT == 'enemy' else ''), 1)
dat_rw(P0 + '/SelectGameMode.dat', sgm, FILES + '/SelectGameMode.dat')

# assets: names exactly as referenced (pac lookup is case-insensitive anyway)
spm_imgs = [x['imageName'] for x in jload(W + '/json/raw/%s.spm.json' % MECH)['imageData']]
have = {f.lower(): d + '/' + f for d in (ASSET, DEPS) for f in os.listdir(d)}
for n in spm_imgs + ['C_TSUKUYOMI.png', 'MG_Tsukuyomi.png', 'SG_Tsukuyomi.png', 'M_Tsukuyomi.png', 's_%s.png' % MECH]:
    assert n.lower() in have, 'missing asset ' + n
    shutil.copyfile(have[n.lower()], FILES + '/' + n)
for x in BBV[BV_SELF]['voices']:
    if x.get('existFlag'):
        shutil.copyfile(have[x['voiceFileName'].lower() + '.ogg'], FILES + '/' + x['voiceFileName'] + '.ogg')
for c, i, it in newse:
    shutil.copyfile(SE_ASSETS[it['seFileName'].lower() + '.ogg'], FILES + '/' + it['seFileName'] + '.ogg')

# =============================================================================================== H. checks
print('H. checks ...')
jsave(jload(W + '/json/back_%s.mek.json' % MEKA_NAME), CK + '/mek/%s.mek.json' % MEKA_NAME)
r = subprocess.run(['python3', T + '/mek_check.py', CK + '/mek/%s.mek.json' % MEKA_NAME, '--json-dir', CK, P + '/work/nexas_rt/json'], capture_output=True, text=True)
print(r.stdout.strip()); open(W + '/mek_check.txt', 'w').write(r.stdout + r.stderr)
assert 'OK (no violations)' in r.stdout, 'mek_check failed'
# shared waz with appended skills: R1/R2/R4/R8/R9 over the whole files; allowed = exactly the vanilla baseline set
shutil.copyfile(W + '/json/raw/%s.spm.json' % MECH, CK + '/spm/%s.spm.json' % MECH)
ALSO = ','.join(DXW[f] for f in append)
def full(mekjson, roots, keep):
    o = subprocess.run(['python3', T + '/mek_check.py', mekjson, '--spm', '--full', '--also-waz', ALSO, '--json-dir'] + roots,
                       capture_output=True, text=True).stdout
    assert '== ' in o, o
    return o, {l.strip() for l in o.splitlines() if l.strip().startswith('FULL ') and any((' %s ' % w) in l for w in keep)}
o_ours, v_ours = full(CK + '/mek/%s.mek.json' % MEKA_NAME, [CK, P + '/work/nexas_rt/json'], ALSO.split(',') + ['skill'])
# baseline: a vanilla mech with the vanilla registries -> the vanilla shared-waz issues the game already tolerates
o_van, v_van = full(P + '/work/nexas_rt/json/mek/Sora.mek.json', [P + '/work/nexas_rt/json'], ALSO.split(','))
extra = sorted(x for x in v_ours - v_van)
open(W + '/mek_check_shared.txt', 'w').write(o_ours + '\n--- not in vanilla baseline:\n' + '\n'.join(extra))
print('   shared waz (%s) + R8/R9: %d violations, all in vanilla baseline: %s' % (ALSO, len(v_ours), not extra))
assert not extra, extra[:20]
# port_remap_check needs BHE grp/waz and ported grp/waz in NeXAS_DX JSON layout
r2 = subprocess.run(['python3', T + '/port_remap_check.py', W + '/json/bhe', CK, MECH, WAZ_NAME, '--orig', P + '/work/nexas_rt/json'], capture_output=True, text=True)
open(W + '/port_remap_check.txt', 'w').write(r2.stdout + r2.stderr)
stats = [l for l in r2.stdout.splitlines() if l.startswith('## stats') or l.startswith('## COUNT')]
print('   ' + '\n   '.join(stats))
assert r2.returncode == 0 and "COUNT mismatches: []" in r2.stdout
st = eval([l for l in stats if l.startswith('## stats')][0].split('stats', 1)[1])
assert st.get('se_diff_file', 0) == 0 and st.get('waz_name_diff', 0) == 0 and st.get('voice_diff_file', 0) == 0, st
# every shared-waz ref inside the appended skills also checked by name (port_remap_check covers the mech waz only)
bad = []
for f, qs in append.items():
    for q in qs:
        bsk = BW[f]['skillList'][q]; dsk = final_waz[DXW[f]]['skillList'][rm.waz[(f, q)][1]]
        xb = [(d['wazFileNo'], d['wazSequenceNo']) for d in walk(bsk) if 'wazFileNo' in d and 'wazSequenceNo' in d]
        xd = [(d['wazFileNo'], d['wazSequenceNo']) for d in walk(dsk) if 'wazFileNo' in d and 'wazSequenceNo' in d]
        xb += [tuple(t['paramList'][:2]) for t in jump_refs(bsk)]; xd += [tuple(t['paramList'][:2]) for t in jump_refs(dsk)]
        for (bf, bq), (df, dq) in zip(xb, xd):
            if bf < 0 or bf == BSELF:
                continue
            bn_ = BW[bf]['skillList'][bq].get('skillNameJapanese'); dn_ = final_waz.get(DXW[df], None)
            dn_ = (dn_ or (dj(DXW[df], 'waz') if DXW[df] in DX_SHARED_SRC else jload(P + '/work/nexas_rt/json/waz/%s.waz.json' % DXW[df])))['skillList'][dq].get('skillNameJapanese')
            if bn_ != dn_:
                bad.append((DXW[f], q, bn_, dn_))
        if len(xb) != len(xd):
            bad.append(('count', f, q))
assert not bad, bad
rep.add('CHECK', 'appended shared skills: internal refs name-checked OK')
assert not rep.items.get('SPRITE_BAD') and not rep.items.get('REF_UNMAPPED'), rep.dump()

# =============================================================================================== I. pac
print('I. pac ...')
pac = OUT + '/Update3.pac'
subprocess.run(['python3', T + '/nexaspac.py', 'create', FILES, pac], check=True, capture_output=True)
tmp = W + '/pac_verify'
shutil.rmtree(tmp, ignore_errors=True)
subprocess.run(['python3', T + '/nexaspac.py', 'extract', pac, tmp], check=True, capture_output=True)
for f in os.listdir(FILES):
    assert filecmp.cmp(FILES + '/' + f, tmp + '/' + f, shallow=False), f
print('   %s: %d files, %d bytes (extract-verified)' % (pac, len(os.listdir(FILES)), os.path.getsize(pac)))
if 'SPRITE_SUBST' in rep.items:      # RefMap's generic label; here these are remaps to the appended REAL anims
    rep.items['SPRITE_REMAP_TO_APPENDED_FX'] = rep.items.pop('SPRITE_SUBST')
rep.dump(W + '/report%s.txt' % ('_enemy' if VARIANT else ''))
print('report:', W + '/report%s.txt' % ('_enemy' if VARIANT else ''))
