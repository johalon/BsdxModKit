#!/usr/bin/env python3
"""Phase 3B: BALDR FORCE EXE 透 (TOORU) -> BALDR SKY DiveX player mech, registered as mech ID 10 (Update3.pac).
ALL weapons (user decision 2026-10-23): the 63 normal weapons at Lv3, the 21 super moves (必殺) and the 3 hidden
■マーカーミサイル skills, with REAL BFE visuals: Bmp/Effect (Effect.spr) -> tooru_eft.spm (SpriteGroup 135), Tama.dat
bullets/explosions -> converted bullet skills (shared Tama04), BFE effects -> effect skills (shared Tama02), all
needed BFE SE -> ogg (SeGroup category 37 after the vanilla items).

Usage: python tools/build_packs.py   (4 パックをビルド・照合・配置。単発なら python mods/phase3b_tooru/build_phase3b.py [--waz110])
  --waz110 -> variantB_waz110/: TOORU at WazaGroup 110 without the placeholder entry (fallback if [110]=empty crashes)
Output: mods/phase3b_tooru/files/ + Update3.pac (原作再現) and modified/files/ + modified/Update3.pac (改善版: 最低値と
  技終了時のみ, tools/bfe2bsdx_balance.py) ; intermediate + report: work/tooru_port/
Built on VANILLA data only (work/extracted, Update wins) - independent of the Tsukuyomi pack (phase 3A). Registry
slots chosen so both packs merge (mods/phase3c_merged): SpriteGroup 135 (effects) + 136 (mech), WazaGroup 111
(110 = placeholder for Tsukuyomi), SE appended to SeGroup category 37 (Tsukuyomi uses category 11), shared waz
appends only to Tama02 / Tama04 / Laser (Tsukuyomi: Effect / Tama03 / Tama05 / Bomb).
Tools: tools/bfe2bsdx_spm.py (SPR->spm), bfe2bsdx_waz.py (WAZ/Tama->waz), bfe2bsdx_tama.py (bullet/effect registry),
bfe2bsdx_eft.py + bfe2bsdx_effspr.py + bfe2bsdx_effmap.py (Effect.spr -> spm, effect type -> anim), bfe2bsdx_common.py.
Decisions / approximations: notes/09_tooru_port.md
"""
import os, sys, copy, json, shutil, subprocess, unicodedata, collections, filecmp
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'tools'))
import bsdx_dat
from bfe2bsdx_common import P, T, EXT, VAN, porttool, jload, jsave, walk, glist, norm, Report
from bfe2bsdx_common import SHARED_WAZ, BULLET_FILE, EFFECT_FILE, LASER_FILE, BASIC_ANIM_SLOT   # BFE-wide conventions
import bfe2bsdx_spm, bfe2bsdx_waz, bfe2bsdx_eft, bfe2bsdx_effspr, bfe2bsdx_tama
from bfe2bsdx_waz import Lib, Converter, SeMap, remap_template_sprites, i32list, SKILL_BASE, effect_target

import mech_config as C       # 機体ごとの値（ID・スロット・名前・技の対応表・mek 基本値など）は mods/phase3b_tooru/mech_config.py

EX = P + '/work/extracted'
W = P + '/' + C.WORK_DIR
MOD = P + '/' + C.MOD_DIR
OUT = MOD + ('/variantB_waz110' if '--waz110' in sys.argv else '')
DIAG = os.environ.get('TOORU_DIAG', '')       # one-off diagnostic packs (not the release): OUT -> MOD/diag_<name>
if DIAG:
    OUT = MOD + '/diag_' + DIAG
FILES = OUT + '/files'
P0 = P + '/mods/phase0_test/files'
DXSPM = EXT + '/NeXAS_DX/src/main/resources/game/bsdx/spm'
BFE_SPR = P + '/' + C.BFE_SPR
BFE_PNG = P + '/' + C.BFE_PNG
BFE_WAZ = P + '/' + C.BFE_WAZ
BFE_TAMA = P + '/' + C.BFE_TAMA
BFE_SE = P + '/' + C.BFE_SE
BFE_EQUIP = P + '/' + C.BFE_EQUIP
BFE_EFFECT = P + '/' + C.BFE_EFFECT

NEW_ID = C.NEW_ID
MEKA_NAME, MEKA_CODE = C.MEKA_NAME, C.MEKA_CODE
SPM_NAME = C.SPM_NAME
SPR_SLOT = C.SPR_SLOT
EFT_NAME, EFT_SLOT = C.EFT_NAME, C.EFT_SLOT
WAZ_SLOT = C.WAZ_SLOT
VARIANT110 = '--waz110' in sys.argv   # fallback variant: the mech directly at WazaGroup 110 (no placeholder entry)
if VARIANT110:
    WAZ_SLOT = C.WAZ_SLOT_WAZ110
SE_CAT = C.SE_CAT
VICTIM_ROW, VICTIM_ID = C.VICTIM_ROW, C.VICTIM_ID
COIN = C.COIN
SKILLS, HIDDEN, MARKER_DESC = C.SKILLS, C.HIDDEN, C.MARKER_DESC
KOU_INIT = C.KOU_INIT
LOADOUT_BFE, LOADOUT_FC = C.LOADOUT_BFE, C.LOADOUT_FC
BASIC_ANIM_MAP = {k: SKILL_BASE + v for k, v in BASIC_ANIM_SLOT.items()}

rep = Report()
shutil.rmtree(W + '/check', ignore_errors=True)
for d in (W + '/json', W + '/check/mek', W + '/check/waz', W + '/check/grp', W + '/check/spm', W + '/se'):
    os.makedirs(d, exist_ok=True)
shutil.rmtree(FILES, ignore_errors=True); os.makedirs(FILES)


def src(name):
    for d in ('Update2', 'Update', 'Dat'):
        if os.path.exists('%s/%s/%s' % (EX, d, name)):
            return '%s/%s/%s' % (EX, d, name)
    raise FileNotFoundError(name)


# ============================================================================== A. vanilla inputs -> JSON
print('A. vanilla JSON ...')
SHARED = list(SHARED_WAZ)
jobs = [['b2j', 'bsdx', src(g + '.grp'), W + '/json/%s.grp.json' % g] for g in ('WazaGroup', 'SpriteGroup', 'SeGroup', 'BatVoice', 'MekaGroup', 'Term')]
jobs += [['b2j', 'bsdx', src(n + '.waz'), W + '/json/%s.waz.json' % n] for n in SHARED + ['Kou']]
jobs += [['b2j', 'bsdx', src('Kou.mek'), W + '/json/Kou.mek.json'], ['b2j', 'bsdx', DXSPM + '/SelectMekaMenuMeka.spm', W + '/json/SelectMekaMenuMeka.spm.json']]
porttool(*jobs)
J = lambda n: jload(W + '/json/' + n)
WGj, SGj, SEj, MGj = J('WazaGroup.grp.json'), J('SpriteGroup.grp.json'), J('SeGroup.grp.json'), J('MekaGroup.grp.json')
WG, SG, SE, MG = glist(WGj), glist(SGj), glist(SEj), glist(MGj)
BV = J('BatVoice.grp.json')['voiceList']
TERM = J('Term.grp.json')['termList']
assert len(WG) == 110 and len(SG) == 138 and len(SE) == 38 and len(BV) == 30 and len(MG) == 103
assert not SG[SPR_SLOT].get('existFlag') and not SG[EFT_SLOT].get('existFlag') and SE[SE_CAT].get('existFlag')
KW, KM = J('Kou.waz.json'), J('Kou.mek.json')
SHW = {i: J('%s.waz.json' % n) for i, n in enumerate(SHARED)}
for i, n in enumerate(SHARED):
    assert WG[i]['wazaDisplayName'] == n and WG[i]['param'] == len(SHW[i]['skillList']), (n, WG[i]['param'])
KSPR = [i for i, x in enumerate(SG) if (x.get('spriteFileName') or '').lower() == 'kou.spm'][0]   # 9

# ============================================================================== B. sprite (SPR -> spm, PNG)
print('B. spm ...')
spr = jload(BFE_SPR); bw = jload(BFE_WAZ)
spm, srep = bfe2bsdx_spm.convert(spr, BFE_PNG, bw, W + '/spm', SPM_NAME)
for k, v in srep.items():
    rep.add('SPM', k, v)
NUMPAT = [a['numPat'] for a in spm['animData']]
anim_imgs = [sorted({c['imageNo'] for p in a['patData'] for d in range(8) for c in spm['pageData'][p['pageNo'][0] + d]['chipData']})
             for a in spm['animData']]

# thumbnail for the select screen: two 1-chip pages (stand dir 1 / dir 0), same layout as vanilla thumbnails (~80x95)
from PIL import Image
def page_png(pg, fn):
    l, t, r, b = (pg['pageRect'][k] for k in ('left', 'top', 'right', 'bottom'))
    im = Image.new('RGBA', (r - l, b - t), (0, 0, 0, 0))
    for ch in pg['chipData']:
        s = ch['srcRect']; d = ch['dstRect']
        sheet = Image.open(W + '/spm/png/' + spm['imageData'][ch['imageNo']]['imageName']).convert('RGBA')
        im.alpha_composite(sheet.crop((s['left'], s['top'], s['right'], s['bottom'])), (d['left'] - l, d['top'] - t))
    im.save(fn); return im.size
smm = J('SelectMekaMenuMeka.spm.json')
assert len(smm['animData']) == 98
tpl_anim = smm['animData'][41]
thumb_pages = []
for k, d in enumerate((1, 0)):
    fn = 's_%s_%d.png' % (SPM_NAME, k + 1)
    w_, h_ = page_png(spm['pageData'][d], W + '/spm/png/' + fn)
    img = len(smm['imageData']); smm['imageData'].append({'imageName': fn})
    p = copy.deepcopy(smm['pageData'][tpl_anim['patData'][0]['pageNo'][0]])
    rect = {'left': -(w_ // 2), 'top': -(h_ // 2), 'right': w_ - w_ // 2, 'bottom': h_ - h_ // 2}
    p.update(pageWidth=w_, pageHeight=h_, pageRect=dict(rect))
    p['chipData'][0].update(imageNo=img, dstRect=dict(rect), chipWidth=w_, chipHeight=h_, srcRect={'left': 0, 'top': 0, 'right': w_, 'bottom': h_})
    thumb_pages.append(len(smm['pageData'])); smm['pageData'].append(p)
na = copy.deepcopy(tpl_anim); na['animName'] = C.THUMB_ANIM_NAME
for k, pt in enumerate(na['patData']):
    pt['pageNo'] = [thumb_pages[k]]
smm['animData'].append(na); THUMB = len(smm['animData']) - 1
smm['numPageData'], smm['numImageData'], smm['numAnimData'] = len(smm['pageData']), len(smm['imageData']), len(smm['animData'])

# ============================================================================== C. waz
print('C. waz ...')
lib = Lib(KW, TERM, extra=[SHW[i] for i in range(len(SHARED))])   # Kou first (same samples as before), then shared waz
bse_names = jload(T + '/bfe_waz_fields.json')['enums']['se']['names']
semap = SeMap(bse_names, SE_CAT, len(SE[SE_CAT]['seItems']))
tama = jload(BFE_TAMA)
effspr = bfe2bsdx_effspr.parse(BFE_EFFECT + '/Effect.spr')
import importlib
CV3 = importlib.import_module(C.COMBO_V3_MODULE) if C.COMBO_V3_MODULE else None   # the mech's COMBOV3 tables (mech_config)
fx = bfe2bsdx_tama.Fx(lib, effspr, tama, semap, rep, SHW, SHARED, EFT_SLOT, BULLET_FILE, EFFECT_FILE, LASER_FILE, KW, label=C.LABEL, combo_v3=CV3)
conv = Converter(lib, spr['anims'], semap, rep, NUMPAT, fx=fx, mode='mech', sink_skills=C.SINK_SKILLS, combo_v3=CV3)
conv.default_hit = [o for ph in KW['skillList'][14]['phasesInfo'] for u in ph['skillUnitCollection'] if u['unitQuantity'] == 41
                    for o in u['skillInfoObjectList']][0]     # Kou ボディブローLv3
KWEP = KM['mekWeaponInfoMap']
def kou_skill_of(k):
    w = KWEP[str(k)]
    return w['wazSequence'] + (2 if w['upgradeExp'] > 0 else 0)
waz_skills = []
# -- 0..10 basic motions = Kou's, sprites remapped (anims 0..47 have the same meaning in tooru.spm), voices removed
for i in range(11):
    s = copy.deepcopy(KW['skillList'][i])
    remap_template_sprites(s, BASIC_ANIM_MAP, (-1, KSPR), rep, NUMPAT)
    for ph in s['phasesInfo']:
        ph['skillUnitCollection'] = [u for u in ph['skillUnitCollection'] if u['unitQuantity'] != 53]
    waz_skills.append(s)
# -- dash basics: skills 3-5 = Muramasa SD, 6-8 = Noi BD (user request 2026-10-26; tools/bfe2bsdx_basic.py, 調査記録 14 §B)
import bfe2bsdx_basic
porttool(*bfe2bsdx_basic.jobs(src, W + '/json'))
basic_new = bfe2bsdx_basic.apply_waz(waz_skills, KW, {n: (J(n + '.waz.json'), J(n + '.mek.json')) for n in bfe2bsdx_basic.SOURCES},
                                     rep, NUMPAT, remap_template_sprites)
bfe2bsdx_basic.add_sd_extras(waz_skills, KW, conv.se_obj, semap.get, rep, bfe2bsdx_basic.SPEEDS['searchDashSpeed'])   # SD 残像 + 原作 SE (user 2026-11-06)
waz_skills.append(copy.deepcopy(KW['skillList'][11]))   # separator (same as Kou)
assert waz_skills[-1]['phaseQuantity'] == 0
equip = open(BFE_EQUIP, 'rb').read()
def bfe_desc(eq):
    r = equip[eq * 240:(eq + 1) * 240]
    return r.split(b'\0')[0].decode('cp932')
# fallback projectile spawn (template move without one, e.g. キャノンブレイカー's barrage): Kou ハンドガン's bullet spawn
FALLBACK_PROJ = [o for o in walk(KW['skillList'][kou_skill_of(60)]) if 'ceventEffectUnitList' in o and (effect_target(o) or (0,))[0] != 0][0]
weapons = []
for n, (bi, kw, code) in enumerate(SKILLS):
    bs = bw[bi]; assert bs['index'] == bi
    nm = unicodedata.normalize('NFKC', bs['header']['name']).replace('(Lv3)', '').replace(' Lv3', '').replace('Lv3', '').strip()
    nm = nm.replace('･', '・').replace('■', '')
    nm = C.RENAME.get(bi, nm)
    tpl = KW['skillList'][kou_skill_of(kw)]
    fc = bs['header']['group'] == 1
    before = {k: collections.Counter(v) for k, v in rep.items.items()}
    m0 = rep.mark()
    sk = conv.convert(bs, tpl, nm, code, fc=fc, fallback_proj=FALLBACK_PROJ)
    own_log = rep.since(m0)            # provenance (調査記録 15)
    notes_ = sorted({'%s: %s' % (k, m) for k, v in rep.items.items() for m in v if v[m] > before.get(k, {}).get(m, 0)
                     and k in ('APPROX', 'DROPPED', 'LASER', 'IGNORED', 'AIR', 'LOOP', 'LINE')} | fx.notes_for(bs))
    rep.add('SKILL', '%2d %s <- BFE %d / template Kou「%s」' % (len(waz_skills), nm, bi, tpl['skillNameJapanese']))
    eq = C.equip_index(bi)
    weapons.append(dict(name=nm, code=code, waz=len(waz_skills), kou=kw, heat=bs['header']['heat'], fc=fc, bfe=bi,
                        desc=bfe_desc(eq) if eq is not None else MARKER_DESC, hidden=bi in HIDDEN, notes=notes_,
                        prov_own=own_log, prov_bul=fx.log_for(bs), tpl_name=tpl['skillNameJapanese']))
    waz_skills.append(sk)
# -- initializer
ini = copy.deepcopy(KW['skillList'][kou_skill_of(KOU_INIT)])
remap_template_sprites(ini, {107: SKILL_BASE + C.INIT_SPR_SLOT}, (-1, KSPR), rep, NUMPAT)
for ph in ini['phasesInfo']:
    ph['skillUnitCollection'] = [u for u in ph['skillUnitCollection'] if u['unitQuantity'] != 53]
weapons.append(dict(name=KWEP[str(KOU_INIT)]['weaponName'], code=None, waz=len(waz_skills), kou=KOU_INIT, heat=None, fc=False, desc=None,
                    bfe=None, hidden=False, notes=['甲のイニシャライザを複製']))
waz_skills.append(ini)
tooru_waz = {'fileName': MEKA_NAME, 'skillList': waz_skills, 'extensionName': 'waz'}
appended = {f: L_ for f, L_ in fx.appended.items() if L_}
assert all(x is not None for L_ in appended.values() for x in L_)
# HITLOCK (調査記録 36): bullets / lines do not switch the lock-on, except those of the weapons in C.HITLOCK_KEEP (mech_config)
HITLOCK_KEEP = C.HITLOCK_KEEP
_hk = [s_ for s_ in waz_skills if s_ and s_.get('skillNameJapanese') in HITLOCK_KEEP]
assert sorted(s_['skillNameJapanese'] for s_ in _hk) == sorted(HITLOCK_KEEP), [s_['skillNameJapanese'] for s_ in _hk]
HITLOCK_KEEP_TURNS = C.HITLOCK_KEEP_TURNS   # (bullet name, turn) that still lock (mech_config)
fx.hitlock_exempt(_hk, HITLOCK_KEEP_TURNS)
# -- effect spm: only the Effect.spr anims the converted bullets / effects use
print('C2. effect spm ...')
eft_anims = fx.eft_anims_used()
eft, erep = bfe2bsdx_eft.build_effect_spm(effspr, bfe2bsdx_eft.decode_sheets(BFE_EFFECT, W + '/eft_sheets'), eft_anims, W + '/eft', EFT_NAME)
for k, v in erep.items():
    rep.add('EFT_SPM', k, v)
EFT_NUMPAT = [a['numPat'] for a in eft['animData']]
# every sprite ref must resolve
for o in walk(tooru_waz):
    if 'actionGroupNumber' in o and o['spmFileSequence'] in (-1, SPR_SLOT):
        assert 0 <= o['actionGroupNumber'] < len(NUMPAT) and 0 <= o['actionNumber'] < NUMPAT[o['actionGroupNumber']], o
    if 'actionGroupNumber' in o and o['spmFileSequence'] == KSPR:
        raise SystemExit('kou.spm ref left: %s' % o)
for o in walk(list(appended.values())):
    if 'actionGroupNumber' in o and o['spmFileSequence'] == EFT_SLOT:
        assert 0 <= o['actionGroupNumber'] < len(EFT_NUMPAT) and 0 <= o['actionNumber'] < EFT_NUMPAT[o['actionGroupNumber']], o
for o in walk([tooru_waz] + list(appended.values())):      # every WazaSelect into a shared file must exist
    if 'wazFileNo' in o and 0 <= o['wazFileNo'] < len(SHARED):
        f = o['wazFileNo']
        assert o['wazSequenceNo'] < len(SHW[f]['skillList']) + len(appended.get(f, [])), o
for f, L_ in appended.items():
    SHW[f]['skillList'] += L_
rep.add('SUMMARY', 'shared waz appends: %s ; effect spm anims %d' % (', '.join('%s +%d' % (SHARED[f], len(L_)) for f, L_ in sorted(appended.items())), len(eft_anims)))
# -- armor-related values x2 (user 2026-10-27; tools/bfe2bsdx_basic.double_armor, 調査記録 16 §N): every skill this build writes
w_of = {w['waz']: w for w in weapons}
n_arm = 0
for i, s in enumerate(waz_skills):
    w = w_of.get(i)
    n_arm += bfe2bsdx_basic.double_armor([(i, s)], rep, MEKA_NAME + ' skill ', log=w.setdefault('prov_own', []) if w else None)
src_ti = {v: t for t, v in fx.tcache.items() if v} ; src_ti.update({v: k[0] for k, v in fx.pcache.items() if v}); src_ti.update({v: k[1] for k, v in fx.lcache.items() if v})
for f, L_ in sorted(appended.items()):
    v0 = len(SHW[f]['skillList']) - len(L_)
    for j, s in enumerate(L_):
        ti = src_ti.get((f, v0 + j))
        n_arm += bfe2bsdx_basic.double_armor([(v0 + j, s)], rep, '%s skill ' % SHARED[f], log=fx.tama_log.setdefault(ti, []) if ti is not None else None)
rep.add('SUMMARY', 'armor-related values x2: %d values' % n_arm)

# ============================================================================== D. SE (BFE wav -> ogg, new items in SE_CAT)
print('D. SE (%d) ...' % len(semap.items))
for nm, idx in semap.items.items():
    wav = BFE_SE + '/%s.wav' % nm
    if not os.path.exists(wav):
        cand = [x for x in os.listdir(BFE_SE) if x.lower() == (nm + '.wav').lower()]
        assert cand, 'missing wav ' + nm
        wav = BFE_SE + '/' + cand[0]
    out = FILES + '/BFE_%s.ogg' % nm
    if os.environ.get('OGG_CACHE'):      # ffmpeg の無い環境（PC）: 以前に作った ogg をそのまま使う（tools/build_packs.py が設定）
        shutil.copyfile(os.environ['OGG_CACHE'] + '/BFE_%s.ogg' % nm, out)
    else:
        r = subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-fflags', '+bitexact', '-i', wav, '-map_metadata', '-1', '-c:a', 'libvorbis',
                            '-q:a', '5', '-fflags', '+bitexact', '-flags:a', '+bitexact', out], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    SE[SE_CAT]['seItems'].append({'existFlag': 1, 'seItemName': 'BFE:' + nm, 'seItemCodeName': 'BFE_%s' % nm.upper(), 'seFileName': 'BFE_' + nm})
    rep.add('SE_NEW', 'SeGroup[%d][%d] BFE_%s.ogg' % (SE_CAT, idx, nm))
assert len(SE[SE_CAT]['seItems']) == semap.base + len(semap.items)

# ============================================================================== E. mek
print('E. mek ...')
mek = copy.deepcopy(KM)
mek['fileName'] = MEKA_NAME
bi_ = mek['mekBasicInfo']
bi_.update(C.MEK_BASIC)
bi_.update(wazFileSequence=WAZ_SLOT, spmFileSequence=SPR_SLOT)
bfe2bsdx_basic.apply_mek(bi_, rep)     # ND 8 / SD 26 / BD 18 (user requests 2026-10-26 / 10-27 / 11-12, 調査記録 14 §B, 調査記録 16 §N)
wmap = {}
for n, w in enumerate(weapons):
    kwp = copy.deepcopy(KWEP[str(w['kou'])])
    kwp['offset'] = 0
    if w['code']:
        kwp.update(weaponName=w['name'], weaponSequence=w['code'], weaponDescription=w['desc'], switchToMekNo=-1)
        kwp['heatMinConsumption'] = 0
        if not w['fc']:
            # HEAT (2026-10-31, 調査記録 22): match "fully grown cost / gauge" of BFE and DiveX.
            # BFE 0x41ad50: cost = max(OH - 使い込み軽減, OH//3), heat max 130 (0x41af2f) -> fully grown = OH//3 per 130.
            # DiveX 0x61cd95 -> 0x65bdb0 (player, MekaGroup != 0): normal weapon cost = heatMin if != 0, else heatMax/2
            # (heatMax if HC flag); no growth for non-Kou mechs. 1 gauge = 8000/100 = 80 (0x617bb4), overheat at >= 1 gauge.
            # -> heatMin = round(OH//3 * 80/130), >= 1 (0 would fall back to heatMax/2). heatMax = BFE OH (ungrown)
            # * 80/130, used only when TOORU is a CPU mech (0x61cdbc).
            kwp['heatMaxConsumption'] = max(2, round(w['heat'] * 80 / 130))
            kwp['heatMinConsumption'] = max(1, round(w['heat'] // 3 * 80 / 130))
            m_ = 'heatMin %d = round(BFE 消費OH %d//3=%d x80/130) [自機の実効消費]; heatMax %d = round(%d x80/130) [CPU 時]; old 実効 %d (=heatMax/2)' % (
                kwp['heatMinConsumption'], w['heat'], w['heat'] // 3, kwp['heatMaxConsumption'], w['heat'], kwp['heatMaxConsumption'] // 2)
            rep.add('HEAT', m_); w.setdefault('prov_own', []).append(('HEAT', m_))
    kwp['wazSequence'] = w['waz']; kwp['upgradeExp'] = 0
    kwp['weaponIdentifier'] = 2 if w['hidden'] else 0     # Kou's entries carry 1 (HC) on some weapons; 2 = not listed
    wmap[str(n)] = kwp
mek['mekWeaponInfoMap'] = wmap
NW = len(wmap)
# PairBlock (basic motions -> skills 0..10) is Kou's as is (same skill numbers)
# AI: Kou's tables, weapon refs remapped (template weapon -> our weapon; otherwise by category / attack type)
inv = {}
for n, w in enumerate(weapons):
    if not w['hidden']:
        inv.setdefault(w['kou'], n)
pools = {('n', 0): [n for n, w in enumerate(weapons) if w['code'] and not w['fc'] and not w['hidden'] and wmap[str(n)]['weaponType'] == 0],
         ('n', 1): [n for n, w in enumerate(weapons) if w['code'] and not w['fc'] and not w['hidden'] and wmap[str(n)]['weaponType'] != 0],
         ('fc', 0): [n for n, w in enumerate(weapons) if w['fc']], ('init', 0): [NW - 1]}
rr = collections.Counter()
def ai_weapon(k):
    if k in inv:
        return inv[k]
    kw_ = KWEP[str(k)]
    key = ('fc', 0) if kw_['weaponCategory'] == 1 else ('init', 0) if kw_['weaponCategory'] == 2 else ('n', 0 if kw_['weaponType'] == 0 else 1)
    pool = pools[key]; v = pool[rr[key] % len(pool)]; rr[key] += 1
    return v
for a in mek['mekAiInfoList']:
    for e in a['cpuEventList']:
        if e['type'] == 2:
            e['mekWeaponInfoMapNo'] = ai_weapon(e['mekWeaponInfoMapNo'])
            assert 0 <= e['mekWeaponInfoMapNo'] < NW
# VoiceInfo: none (user request 2026-10-23: 透 is silent like the original). Same form as voiceless vanilla mechs (e.g. Zako029a, verified as player)
mek['mekVoiceInfo'] = {'version': -1, 'emotions': [], 'voiceSlots': [], 'table': [], 'builtinEmotionCount': 0}
# MaterialBlock: Kou's 10 regular entries (sprite group 9 -> 136 = images of anims 0..47) + 1 entry per weapon (closure)
SPMCACHE = {}
def spm_json(g):
    if g == SPR_SLOT:
        return spm
    if g == EFT_SLOT:
        return eft
    if g not in SPMCACHE:
        fn = SG[g]['spriteFileName'][:-4]
        p = [x for x in os.listdir(VAN + '/spm') if x.lower() == (fn + '.spm.json').lower()]
        SPMCACHE[g] = jload(VAN + '/spm/' + p[0]) if p else None
    return SPMCACHE[g]
def material_for(skill_objs, self_group):
    spr_ = collections.defaultdict(set); se_ = collections.defaultdict(set)
    seen = set(); stack = [(o, self_group) for o in skill_objs]
    while stack:
        o, sg = stack.pop()
        for d in walk(o):
            if 'actionGroupNumber' in d:
                g = sg if d['spmFileSequence'] == -1 else d['spmFileSequence']
                if g is None or g < 0:
                    continue
                s = spm_json(g)
                if s and 0 <= d['actionGroupNumber'] < len(s['animData']):
                    for p in s['animData'][d['actionGroupNumber']]['patData']:
                        for dd in range(8 if g == SPR_SLOT else 1):
                            pg = p['pageNo'][0] + dd
                            if pg < len(s['pageData']):
                                for c in s['pageData'][pg]['chipData']:
                                    spr_[g].add(c['imageNo'])
            if d.get('typeId') == 23 and 'byteDataList' in d:
                for raw in d['byteDataList']:
                    b = bytes((x + 256) % 256 for x in raw)
                    c, i = int.from_bytes(b[0:4], 'little', signed=True), int.from_bytes(b[4:8], 'little', signed=True)
                    if 0 <= c < len(SE):
                        se_[c].add(i)
            if 'wazFileNo' in d and 0 <= d['wazFileNo'] < 8:
                key = (d['wazFileNo'], d['wazSequenceNo'])
                if key not in seen and d['wazSequenceNo'] < len(SHW[d['wazFileNo']]['skillList']):
                    seen.add(key); sk = SHW[d['wazFileNo']]['skillList'][d['wazSequenceNo']]
                    if sk:
                        stack.append((sk, None))
    return ({'offset': 0, 'length': 0,
             'spriteGroups': [sorted(spr_[g]) for g in range(len(SG))],
             'seGroups': [sorted(se_[c]) for c in range(len(SE))],
             'voiceGroups': [[] for _ in range(len(BV))]})
mb = KM['mekMaterialBlock']
reg = copy.deepcopy(mb['entries'][:mb['regularCount']])
basic_imgs = sorted({i for a in range(48) for i in anim_imgs[a]})
for e in reg:
    e['offset'] = e['length'] = 0
    if e['spriteGroups'][KSPR]:
        e['spriteGroups'][KSPR] = []
        e['spriteGroups'][SPR_SLOT] = list(basic_imgs)
bfe2bsdx_basic.merge_material(reg, material_for(basic_new, SPR_SLOT), SPR_SLOT)   # SE / effect images of the copied SD/BD
trail = [material_for([waz_skills[w['waz']]], SPR_SLOT) for w in weapons]
mek['mekMaterialBlock'] = {'extraRegularCount': mb['regularCount'] - 7, 'regularCount': mb['regularCount'], 'entries': reg + trail,
                           'regularEntries': reg, 'trailingEntries': trail}

# self-test of the material rule on a vanilla non-Kou player mech (Rain: 1 entry per weapon)
rain_m = jload(VAN + '/mek/Rain.mek.json'); rain_w = jload(VAN + '/waz/Rain.waz.json')
rg = rain_m['mekBasicInfo']['spmFileSequence']; ok = tot = 0
for k, wp in rain_m['mekWeaponInfoMap'].items():
    e = rain_m['mekMaterialBlock']['trailingEntries'][int(k)]
    got = material_for([rain_w['skillList'][wp['wazSequence']]], rg)
    tot += 1; ok += (got['spriteGroups'][rg] == sorted(e['spriteGroups'][rg]))
rep.add('MATERIAL_SELFTEST', 'Rain weapon entries: self-sprite image lists reproduced %d/%d' % (ok, tot))

# ============================================================================== F. registries
print('F. grp ...')
for f in appended:
    WG[f]['param'] = len(SHW[f]['skillList'])
if not VARIANT110:
    WG.append({'existFlag': 0})             # [110] reserved for Tsukuyomi (phase 3A) so that the packs can be merged
WG.append({'existFlag': 1, 'wazaName': C.WAZA_NAME, 'wazaCodeName': MEKA_CODE, 'wazaDisplayName': MEKA_NAME, 'param': len(waz_skills)})
assert len(WG) - 1 == WAZ_SLOT
SG[SPR_SLOT] = {'existFlag': 1, 'spriteFileName': SPM_NAME + '.spm', 'spriteCodeName': MEKA_CODE, 'param': 0}
SG[EFT_SLOT] = {'existFlag': 1, 'spriteFileName': EFT_NAME + '.spm', 'spriteCodeName': MEKA_CODE + '_EFT', 'param': 0}
assert MG[NEW_ID] == {'existFlag': 1, 'mekaName': 'Sora2', 'mekaCodeName': 'SORA2'}
MG[NEW_ID] = {'existFlag': 1, 'mekaName': MEKA_NAME, 'mekaCodeName': MEKA_CODE}

# ============================================================================== G0. diagnostic tweaks (TOORU_DIAG only)
if DIAG == 'mbu':
    # 2026-11-04 メガBU 3 HIT 診断: (1) ph3 の透の上昇を 1F 遅らせる（ヒット F0 のヒットストップ中に上昇しないか）
    # (2) ph2 ヒットの のけぞり 停止時間 (int2, 甲テンプレ 5) -> 0（敵だけ長く止まらないか）
    sk_ = [s_ for s_ in tooru_waz['skillList'] if s_ and s_.get('skillNameJapanese') == 'メガ・ブーストアッパー'][0]
    for pi_, ph_ in enumerate(sk_['phasesInfo']):
        for u_ in ph_['skillUnitCollection']:
            if pi_ == 3 and u_['unitQuantity'] == 19:
                for o_ in u_['skillInfoObjectList']:
                    if o_['startFrame'] == 0 and o_.get('int2', 0) > 0:
                        o_['startFrame'] = 1; o_['endFrame'] = max(1, o_['endFrame'])
                        print('DIAG mbu: ph3 jump start F0 -> F1')
            if pi_ == 2 and u_['unitQuantity'] == 41:
                for o_ in u_['skillInfoObjectList']:
                    for c_ in o_['ceventHitUnitList']:
                        if c_['unitSlotNum'] in (17, 18, 19, 20) and c_.get('data'):
                            c_['data']['int2'] = 0
                print('DIAG mbu: ph2 のけぞり 停止時間 -> 0')

# ============================================================================== G1. engine-difference patches (both packs)
# 2026-11-10 (user, BU hitstop patch): BaldrSky runs F0 of a turn entered on a hit inside the hitstop, BFE starts the whole
# phase after it. HITDELAY moved only the hit window to F1, so 透 already moved 1F (TOUCHCARRY ~12px up) before the 2nd hit
# could check -> short enemies were missed. Patch (user's hand fix, verified in game): the turn's first slot 18 (speed),
# slot 19 (vertical) and slot 21 objects at F0 start at F1. Named per skill on purpose (not a general converter rule).
# MBU (provisional, user OK 11/10): turn 3 (BFE ph3, rise 12 + hit at F0 right after the ph2 hit) gets the same shift, and
# the ph2 hit's のけぞり 停止時間 (int2 of slots 17-20, 甲 template 5, no BFE counterpart) -> 0 (11/04 diag_mbu candidates).
def _hitstop_move_f1(name, turn):
    sk_ = [s_ for s_ in tooru_waz['skillList'] if s_ and s_.get('skillNameJapanese') == name][0]
    n_ = 0
    for u_ in sk_['phasesInfo'][turn]['skillUnitCollection']:
        if u_['unitQuantity'] in (18, 19, 21):
            for o_ in u_['skillInfoObjectList']:
                if o_['startFrame'] == 0:
                    o_['startFrame'] = 1; o_['endFrame'] = max(1, o_['endFrame']); n_ += 1
    assert n_, (name, turn)
    rep.add('HITSTOPMOVE', '%s turn %d: slot 18/19/21 F0 objects -> F1 (%d; BaldrSky runs F0 inside the hitstop)' % (name, turn, n_))
    return sk_
_g1 = {nm_: _hitstop_move_f1(nm_, t_) for nm_, t_ in C.HITSTOP_MOVE_F1}   # mech_config (透: ブーストアッパー 2, メガ・ブーストアッパー 3)
_mbu = _g1[C.NOKEZORI_ZERO[0]]
_n = 0
for o_ in [o_ for u_ in _mbu['phasesInfo'][C.NOKEZORI_ZERO[1]]['skillUnitCollection'] if u_['unitQuantity'] == 41 for o_ in u_['skillInfoObjectList']]:
    for c_ in o_['ceventHitUnitList']:
        if c_['unitSlotNum'] in (17, 18, 19, 20) and c_.get('data') and c_['data'].get('int2'):
            c_['data']['int2'] = 0; _n += 1
assert _n
rep.add('HITSTOPMOVE', '%s turn %d: のけぞり 停止時間 -> 0 (%d columns; provisional)' % (C.NOKEZORI_ZERO + (_n,)))

# ============================================================================== G1b. FIRELOCK (both packs, 調査記録 57)
# R/E 2026-11-15 (FIRELOCK, user 「グラビティフィールド・エネルギーフィールド・ギガンテックフィールドが、スプライトの発射点が変更
# されても自機に追従しているせいで、弾が一瞬で飛んで見える」): BFE fires these from a sprite event with 「弾発射位置ﾛｯｸ」
# (BaldrForce.exe 0x4437a8: the fire position is taken once at the event start) and the bullet then stays at its target
# (移動方向 5). The port's follow bullet (slot 11 前指定を維持) re-read spawn sub 25 「オブジェクト位置指定 自分 FIRERECT n」
# every frame (BaldrSky.exe 0x60bd70 -> anchor +0x16dc, 0x610e70 position = anchor + offset + this frame's move), so it
# jumped with 透's fire point whenever the sprite pattern changed. -> sub 25 = 自分 NONE (the body, Term OBJECTPOS2 0) and
# the fire point's horizontal offset at the spawn frame as the follow offset: slot 15 スプライト方向 + slot 18 (with slot 11
# the slot 18 vector is the offset itself, STICKALPHAPOS; raw = px x 100 / ﾍﾞｸﾄﾙ補正率). Sprites face -x (attack rects:
# 透 533 / 甲 4620 of 609 / 5402 at x <= 0) -> forward = -centre x. FIRERECT n = hitFlag bit 17 + n (SPR 14/15 -> 18/19,
# bfe2bsdx_spm). The vertical part of the fire point (a few px) is not carried (E: no exe-checked height convention).
# 2026-11-15 night: the pass is gone (user: エネルギーフィールドも甲と同じ組み方で、構えの間だけ透に付ける). The follow bullets keep
# slot 11 in their follow turn (bfe2bsdx_waz STICK / STICKALPHA / STICKTARGET); only the converter's marker is removed here.
for o_ in walk(tooru_waz):
    if isinstance(o_, dict):
        o_.pop('_firelock', None)

# E 2026-11-15 night (FOLLOWCUT, user 「エネルギーフィールド: 手を引き戻す途中の絵（ほんの一瞬）でもまだ追従しているので、そこで弾が
# ずれて見える」): BFE ends the follow phase when the shooter's sprite (anim) changes (go_mech_spr). The DiveX bullet has
# that as 親状態：グループ, but in game it still follows through the next anim of the same turn (ｴﾈﾙｷﾞｰﾌｨｰﾙﾄﾞ: anim 250 -> 251,
# the arm coming back). The frame of that change is known from the shooter's turn, so the bullet's follow (slot 11) and
# what rides on it (slot 15 / 18 offset, slot 19 held height) stop at that frame; the bullet then stays where it is until
# its own turn change. Only when the anim changes inside the firing turn (ｸﾞﾗﾋﾞﾃｨﾌｨｰﾙﾄﾞ: the change is the turn end -> untouched).
def _followcut():
    out = []; done = {}
    for sk_ in tooru_waz['skillList']:
        if not sk_:
            continue
        for ti_, ph_ in enumerate(sk_['phasesInfo']):
            us_ = {u_['unitQuantity']: u_['skillInfoObjectList'] for u_ in ph_['skillUnitCollection']}
            for o_ in us_.get(48, []):
                subs_ = {x['unitSlotNum']: x['data'] for x in o_['ceventEffectUnitList']}
                f_, q_ = subs_[3].get('wazFileNo'), subs_[3].get('wazSequenceNo')
                if f_ not in appended or (f_, q_) in done:
                    continue
                bsk_ = SHW[f_]['skillList'][q_]
                if not bsk_ or fx.label + '弾' not in bsk_.get('skillNameJapanese', ''):   # this mech's converted bullets
                    continue
                t0_ = {u_['unitQuantity']: u_ for u_ in bsk_['phasesInfo'][0]['skillUnitCollection']}
                if not (11 in t0_ and t0_[11]['skillInfoObjectList'][0]['bsdxInfoCollectionList'][0]['typeList'] == [0]):
                    continue
                if not any(c_['bsdxInfoCollectionList1'][0]['typeList'] == [2, 8, 5] and c_['bsdxInfoCollectionList2'][0]['typeList'] == [0, 1]
                           for c_ in (t0_[71]['skillInfoObjectList'] if 71 in t0_ else [])):
                    continue           # only a 親状態：グループ change that leads to another turn (BFE go_mech_spr -> next phase); a
                                       # bullet that simply ends there (ｽﾌﾟﾚｯﾄﾞﾊﾟﾝﾁ用, go_mech_spr 99) is left alone
                at_ = o_['startFrame']
                spr_ = sorted(us_.get(0, []), key=lambda s_: s_['startFrame'])
                cur_ = [s_ for s_ in spr_ if s_['startFrame'] <= at_ <= s_['endFrame']]
                if not cur_:
                    continue
                nxt_ = [s_['startFrame'] for s_ in spr_ if s_['startFrame'] > at_ and s_['actionGroupNumber'] != cur_[0]['actionGroupNumber']]
                if not nxt_:
                    continue
                cut_ = min(nxt_) - at_          # bullet frame at which the shooter shows the next anim
                done[(f_, q_)] = cut_
                if cut_ < 1:
                    continue
                o11_ = t0_[11]['skillInfoObjectList'][0]
                if o11_['endFrame'] < cut_:
                    continue
                o11_['endFrame'] = cut_ - 1
                how_ = ['slot 11 F0-%d' % (cut_ - 1)]
                for sl_ in (15, 18, 19):
                    if sl_ not in t0_:
                        continue
                    lst_ = [e_ for e_ in t0_[sl_]['skillInfoObjectList'] if e_['startFrame'] < cut_]
                    if len(lst_) == len(t0_[sl_]['skillInfoObjectList']) and all(e_['endFrame'] < cut_ for e_ in lst_) and sl_ == 15:
                        continue
                    moved_ = any((e_.get('int2') or 0) or (e_.get('int5') or 0) for e_ in lst_) if sl_ != 15 else False
                    for e_ in lst_:
                        e_['endFrame'] = min(e_['endFrame'], cut_ - 1)
                    if sl_ != 15 and moved_:
                        lst_.append(dict(copy.deepcopy(lst_[-1]), int1=0, int2=0, int3=0, int4=0, int5=0, int6=0, startFrame=cut_, endFrame=cut_, offset=0))
                    t0_[sl_]['skillInfoObjectList'] = lst_
                    how_.append('slot %d cut' % sl_)
                out.append('%s T%d F%d -> %s: shooter anim changes %dF after the shot -> %s' % (
                    sk_['skillNameJapanese'], ti_, at_, bsk_['skillNameJapanese'], cut_, ', '.join(how_)))
    return out
for l_ in _followcut():
    rep.add('FOLLOWCUT', l_)


# ============================================================================== G. generate + re-parse
# B 2026-11-04 (ROLEMIN): the converter leaves the balanced 最低値 on each converted vs-mech hit as '_bal'; take it off
# before writing the faithful files (applied to copies in I2).
import bfe2bsdx_balance
BAL_SRC = {MEKA_NAME + '.waz': tooru_waz}
BAL_SRC.update({SHARED[f] + '.waz': SHW[f] for f in appended})
BAL_RECS = bfe2bsdx_balance.pop_bal(BAL_SRC)
print('G. generate ... (%d balanced hit records taken aside)' % len(BAL_RECS))
CK = W + '/check'
gen = {MEKA_NAME + '.mek': (mek, 'mek'), MEKA_NAME + '.waz': (tooru_waz, 'waz'), 'WazaGroup.grp': (WGj, 'grp'),
       'SpriteGroup.grp': (SGj, 'grp'), 'SeGroup.grp': (SEj, 'grp'), 'MekaGroup.grp': (MGj, 'grp'),
       SPM_NAME + '.spm': (spm, 'spm'), EFT_NAME + '.spm': (eft, 'spm'), 'SelectMekaMenuMeka.spm': (smm, 'spm')}
for f in appended:
    gen[SHARED[f] + '.waz'] = (SHW[f], 'waz')
jobs = []
for n, (o, sub) in gen.items():
    jp = CK + '/%s/%s.json' % (sub, n); jsave(o, jp)
    jobs.append(['j2b', jp, FILES + '/' + n]); jobs.append(['b2j', 'bsdx', FILES + '/' + n, W + '/json/back_%s.json' % n])
print(porttool(*jobs).count('identical'), 'files regenerated identically')
for n, (o, sub) in gen.items():
    back = jload(W + '/json/back_%s.json' % n); mine = jload(CK + '/%s/%s.json' % (sub, n))
    if n.endswith('.mek'):
        for x in (back, mine):
            x['mekMaterialBlock'] = norm(x['mekMaterialBlock']['entries'])
        for x in (back, mine):
            for wv in x['mekWeaponInfoMap'].values():
                wv.pop('offset', None)
            x.pop('mekBlocks', None); x.pop('mekHead', None)   # sizes/offsets recomputed by the generator
    if norm(back) != norm(mine):
        for k in mine:
            if k != 'fileName' and norm(mine[k]) != norm(back.get(k)):
                print('  mismatch key', k)
        raise SystemExit('re-parse mismatch: ' + n)
    jsave(jload(W + '/json/back_%s.json' % n), CK + '/%s/%s.json' % (sub, n))   # parser's view for mek_check
print('   %d generated files re-parse identically' % len(gen))
for f in appended:   # vanilla shared waz must be an exact byte prefix
    a_ = open(src(SHARED[f] + '.waz'), 'rb').read(); b_ = open(FILES + '/%s.waz' % SHARED[f], 'rb').read()
    assert b_[:len(a_)] == a_ and len(b_) > len(a_), SHARED[f]
# png
for d_ in (W + '/spm/png', W + '/eft/png'):
    for fn in os.listdir(d_):
        if fn in {x['imageName'] for x in spm['imageData'] + eft['imageData'] + smm['imageData'][-2:]}:
            shutil.copyfile(d_ + '/' + fn, FILES + '/' + fn)
need = {x['imageName'] for x in spm['imageData']} | {x['imageName'] for x in eft['imageData']} | {x['imageName'] for x in smm['imageData'][-2:]}
assert need <= set(os.listdir(FILES)), need - set(os.listdir(FILES))

# dat tables
def dat_rw(srcf, fn, dst):
    t, r = bsdx_dat.read(open(srcf, 'rb').read()); fn(t, r)
    out = bsdx_dat.write(t, r); open(dst, 'wb').write(out)
    assert bsdx_dat.write(*bsdx_dat.read(out)) == out
def we(t, r):
    assert len(r) == 103 and all(x == -1 for x in r[NEW_ID]); assert len(LOADOUT) == 14 and all(0 <= x < NW for x in LOADOUT)
    assert not any(weapons[x]['hidden'] for x in LOADOUT)
    r[NEW_ID] = list(LOADOUT)
bfe_pos = {w['bfe']: n for n, w in enumerate(weapons) if w['bfe'] is not None}
LOADOUT = [bfe_pos[b] for b in LOADOUT_BFE] + [bfe_pos[LOADOUT_FC], NW - 1]
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
# 2026-11-06 (user): Phase 0 test leftovers removed — AkisRoomItem.dat (69 mechs at 1 coin) and SelectGameMode.dat
# (【MODテストTOORU】 marker) are no longer written; the game uses its vanilla files.

# ============================================================================== H. checks
print('H. checks ...')
shutil.copyfile(W + '/spm/%s.spm.json' % SPM_NAME, CK + '/spm/%s.spm.json' % SPM_NAME)
r = subprocess.run([sys.executable, T + '/mek_check.py', CK + '/mek/%s.mek.json' % MEKA_NAME, '--json-dir', CK, VAN], capture_output=True, text=True)
open(W + '/mek_check.txt', 'w').write(r.stdout + r.stderr)
print('   ' + '\n   '.join(r.stdout.strip().splitlines()[-6:]))
assert 'OK (no violations)' in r.stdout, 'mek_check failed (see work/tooru_port/mek_check.txt)'
also = ','.join(SHARED[f] for f in appended)
if also:
    def full(mekjson, roots):
        o = subprocess.run([sys.executable, T + '/mek_check.py', mekjson, '--spm', '--full', '--also-waz', also, '--json-dir'] + roots, capture_output=True, text=True).stdout
        return o, {l.strip() for l in o.splitlines() if l.strip().startswith('FULL ') and any((' %s ' % w_) in l for w_ in also.split(',') + ['skill'])}
    o1, v1 = full(CK + '/mek/%s.mek.json' % MEKA_NAME, [CK, VAN])
    o2, v2 = full(VAN + '/mek/Sora.mek.json', [VAN])
    extra = sorted(v1 - v2)
    open(W + '/mek_check_full.txt', 'w').write(o1 + '\n--- not in vanilla baseline:\n' + '\n'.join(extra))
    print('   full check (%s, --spm): %d violations, %d not in vanilla baseline' % (also, len(v1), len(extra)))
    assert not extra, extra[:10]

# waz_summary view: vanilla JSON (symlinks) overridden by this build's files -> python3 tools/waz_summary.py Tooru --json-dir work/tooru_port/view
_link = shutil.copyfile if os.name == 'nt' else os.symlink    # Windows の symlink は権限が要るのでコピーで代用
VIEW = W + '/view'; shutil.rmtree(VIEW, ignore_errors=True)
for sub in ('bin', 'dat', 'grp', 'mek', 'spm', 'waz'):
    os.makedirs(VIEW + '/' + sub)
    for f in os.listdir(VAN + '/' + sub) if os.path.isdir(VAN + '/' + sub) else []:
        _link(VAN + '/%s/%s' % (sub, f), VIEW + '/%s/%s' % (sub, f))
    if os.path.isdir(CK + '/' + sub):
        for f in os.listdir(CK + '/' + sub):
            if os.path.lexists(VIEW + '/%s/%s' % (sub, f)):
                os.remove(VIEW + '/%s/%s' % (sub, f))
            _link(CK + '/%s/%s' % (sub, f), VIEW + '/%s/%s' % (sub, f))

# ============================================================================== I. pac
print('I. pac ...')
pac = OUT + '/Update3.pac'
subprocess.run([sys.executable, T + '/nexaspac.py', 'create', FILES, pac], check=True, capture_output=True)
tmp = W + '/pac_verify'; shutil.rmtree(tmp, ignore_errors=True)
subprocess.run([sys.executable, T + '/nexaspac.py', 'extract', pac, tmp], check=True, capture_output=True)
for f in os.listdir(FILES):
    assert filecmp.cmp(FILES + '/' + f, tmp + '/' + f, shallow=False), f
print('   %s: %d files, %d bytes (extract-verified)' % (pac, len(os.listdir(FILES)), os.path.getsize(pac)))

# ============================================================================== I2. balanced variant (modified/)
# User 2026-11-04: the build also outputs a balanced pack next to the faithful one: OUT/modified/Update3.pac.
# Damage parameters only: 最低値 (minDamage, ROLEMIN 係数 ROLE_G_MOD) and 技終了時 (endCorrection x END_MUL_MOD) of the converted vs-mech
# hits (tools/bfe2bsdx_balance.py, notes/B4_role_preserving_20261104.md §7/§8; 11/05: 1.25 / x1.0). The faithful files above are not touched;
# everything else is copied.
if not DIAG:
    print('I2. balanced variant (modified/) ...')
    BOUT = OUT + '/modified'; BFILES = BOUT + '/files'; BCK = W + '/check_modified' + ('_waz110' if VARIANT110 else '')
    for d_ in (BOUT, BCK):
        shutil.rmtree(d_, ignore_errors=True)
    shutil.copytree(FILES, BFILES); os.makedirs(BCK)
    bgen, b_rows = bfe2bsdx_balance.apply(BAL_SRC, BAL_RECS, cat={v['weaponName']: v['weaponCategory'] for v in mek['mekWeaponInfoMap'].values()})
    # 2026-11-10 (user): 改善版だけの技の挙動の調整（一覧・切り替えは tools/modified_tweaks.py、実装は bfe2bsdx_modified_behavior.py）
    import modified_tweaks, bfe2bsdx_modified_behavior
    # 11/12 (IF_RECT): 挙動の調整は spm のページ（判定矩形）も触る -> 透の 2 つの spm も渡す（触らなければ同じバイト列に戻る）
    B_SPM = (SPM_NAME + '.spm', EFT_NAME + '.spm')
    for n in B_SPM:
        bgen[n] = jload(W + '/json/back_%s.json' % n)
    # 11/19 (STUNROD_DOT): 挙動の調整が共有のエフェクト waz（Tama02）に改善版だけの技を足すことがある -> 写しを渡す（触らなければ外す）
    B_EFF = SHARED[EFFECT_FILE] + '.waz'
    b_eff_added = B_EFF not in bgen
    if b_eff_added:
        bgen[B_EFF] = copy.deepcopy(SHW[EFFECT_FILE])
    # 11/21 (ND_SPEED): 改善版だけ mek（ノーマルダッシュの速度）を変えることがある -> 原作再現版の mek を渡す（変えなければ外す）
    B_MEK = MEKA_NAME + '.mek'
    bgen[B_MEK] = jload(W + '/json/back_%s.json' % B_MEK)
    b_blog, b_touched = bfe2bsdx_modified_behavior.apply(bgen, self_waz=MEKA_NAME + '.waz', bullet_waz=SHARED[BULLET_FILE] + '.waz',
                                                         spm_file=SPM_NAME + '.spm', eft_file=EFT_NAME + '.spm', eft_slot=EFT_SLOT,
                                                         effect_waz=B_EFF)
    if norm(bgen[B_MEK]) == norm(jload(W + '/json/back_%s.json' % B_MEK)):
        del bgen[B_MEK]
    if b_eff_added and not b_touched.get(B_EFF):
        del bgen[B_EFF]
    # 改善版だけ共有 waz に技を足したら、WazaGroup.grp の技の数（param）も改善版だけ合わせる（原作再現版の WazaGroup は不変）
    b_grown = {f: len(bgen[SHARED[f] + '.waz']['skillList']) for f in appended
               if SHARED[f] + '.waz' in bgen and len(bgen[SHARED[f] + '.waz']['skillList']) != len(SHW[f]['skillList'])}
    if b_grown:
        wg_ = copy.deepcopy(WGj)
        for f, n_ in b_grown.items():
            assert n_ > len(SHW[f]['skillList']), 'modified: %s shrank' % SHARED[f]
            glist(wg_)[f]['param'] = n_
        bgen['WazaGroup.grp'] = wg_
        print('   modified/: shared waz grown %s -> WazaGroup.grp param' % ', '.join('%s %d' % (SHARED[f], n_) for f, n_ in b_grown.items()))
    for l_ in b_blog:
        rep.add('BEHAVIOR', 'modified/: ' + l_)
        print('   ' + l_)
    jobs = []
    for n, o in bgen.items():
        jp = BCK + '/%s.json' % n; jsave(o, jp)
        jobs += [['j2b', jp, BFILES + '/' + n], ['b2j', 'bsdx', BFILES + '/' + n, BCK + '/back_%s.json' % n]]
    porttool(*jobs)
    for n in bgen:
        back = jload(BCK + '/back_%s.json' % n)
        if norm(back) != norm(jload(BCK + '/%s.json' % n)):
            raise SystemExit('modified: re-parse mismatch: ' + n)
        fa_ = jload(W + '/json/back_%s.json' % n); k_ = bfe2bsdx_balance.KEYS
        if n == 'WazaGroup.grp':
            # 改善版で技を足した共有 waz の param だけが違う
            for f, n_ in b_grown.items():
                glist(fa_)[f]['param'] = n_
            assert norm(fa_) == norm(back), 'modified: WazaGroup.grp differs outside the grown param'
            continue
        if n == B_MEK:
            # mek: ノーマルダッシュの速度（ND_SPEED）だけが違う
            fa_['mekBasicInfo']['normalDashSpeed'] = back['mekBasicInfo']['normalDashSpeed']
            assert norm(fa_) == norm(back), 'modified: %s differs outside normalDashSpeed' % n
            continue
        if n in B_SPM:
            # spm: 変えた anim / ページ（b_touched = ('a', n) / ('p', n)、末尾に足したページも含む）以外は原作再現版と同じ。
            # 触っていなければファイルごと同じ。
            for kind_, i_ in b_touched.get(n, ()):
                L_ = back['animData' if kind_ == 'a' else 'pageData']; F_ = fa_['animData' if kind_ == 'a' else 'pageData']
                L_[i_] = None
                if i_ < len(F_):
                    F_[i_] = None
            assert all(p_ is None for p_ in back['pageData'][len(fa_['pageData']):]), n   # 足したページは全部 touched
            back['pageData'] = back['pageData'][:len(fa_['pageData'])]
            for x_ in (fa_, back):
                x_.pop('numPageData', None)
            assert norm(fa_) == norm(back), 'modified: %s differs outside the touched pages' % n
            if not b_touched.get(n):
                assert filecmp.cmp(FILES + '/' + n, BFILES + '/' + n, shallow=False), n
            continue
        if b_touched.get(n):
            # 挙動の調整をした技は構造ごと変わるので、ここでは除外（中身は bfe2bsdx_modified_behavior の assert で確認済み）。
            # 技の長さが変わると後ろの技のファイル内 offset がずれるので offset も比べない。
            # 11/12: Tooru.waz 以外（スウィングワイヤーの弾 Laser.waz）も対象になったので、ファイルごとの集合。
            n0_ = len(fa_['skillList'])
            for si_ in b_touched[n]:
                back['skillList'][si_] = None
                if si_ < n0_:
                    fa_['skillList'][si_] = None
            assert all(x_ is None for x_ in back['skillList'][n0_:]), 'modified: %s appended skills not all touched' % n   # 足した技は全部 touched
            back['skillList'] = back['skillList'][:n0_]
            k_ = k_ + ('offset',)
        assert bfe2bsdx_balance.only_keys_changed(fa_, back, k_), 'modified: not only 最低値/技終了時: ' + n
    for f in appended:   # vanilla shared waz must still be an exact byte prefix
        a_ = open(src(SHARED[f] + '.waz'), 'rb').read(); b_ = open(BFILES + '/%s.waz' % SHARED[f], 'rb').read()
        assert b_[:len(a_)] == a_ and len(b_) > len(a_), SHARED[f]
    for f in os.listdir(FILES):   # every other file is the faithful one
        if f not in bgen:
            assert filecmp.cmp(FILES + '/' + f, BFILES + '/' + f, shallow=False), f
    bpac = BOUT + '/Update3.pac'
    subprocess.run([sys.executable, T + '/nexaspac.py', 'create', BFILES, bpac], check=True, capture_output=True)
    tmp = W + '/pac_verify_modified'; shutil.rmtree(tmp, ignore_errors=True)
    subprocess.run([sys.executable, T + '/nexaspac.py', 'extract', bpac, tmp], check=True, capture_output=True)
    for f in os.listdir(BFILES):
        assert filecmp.cmp(BFILES + '/' + f, tmp + '/' + f, shallow=False), f
    n_ = sum(1 for r_ in b_rows if r_[4] != r_[5])
    e_ = sum(1 for r_ in b_rows if r_[6] != r_[7])
    cat_ = {v['weaponName'] for v in mek['mekWeaponInfoMap'].values()}
    rep.add('BALANCE', 'modified/: hit owners not found among the mek weapon names (no per-weapon adjustment possible): %s' % (
        ', '.join(sorted({r_[8] for r_ in b_rows if r_[8] not in cat_})) or 'none'))
    for why_ in ('OVERRIDES', 'FC_MIN', 'power'):
        rep.add('BALANCE', 'modified/: %s %s on %d hit objects: %s' % (why_, '威力 x' if why_ == 'power' else 'set/raised 最低値',
                sum(1 for r_ in b_rows if why_ in r_[9]), ', '.join(sorted({r_[8] for r_ in b_rows if why_ in r_[9]}))))
    rep.add('BALANCE', 'modified/: ROLEMIN 係数 %g + 技終了時 x%g: %d hit objects, 最低値 differs on %d, 技終了時 on %d '
            '(only these two keys differ, re-parse identical)' % (bfe2bsdx_balance.ROLE_G_MOD, bfe2bsdx_balance.END_MUL_MOD, len(b_rows), n_, e_))
    open(W + '/balance_table%s.md' % ('_waz110' if VARIANT110 else ''), 'w', encoding='utf-8').write(bfe2bsdx_balance.table_md(b_rows))
    if not VARIANT110:
        open(P + '/' + C.NOTES_BALANCE, 'w', encoding='utf-8').write(bfe2bsdx_balance.table_md(b_rows))
        open(P + '/' + C.NOTES_TWEAKS, 'w', encoding='utf-8').write(
            modified_tweaks.table(md=True) + '\n## このビルドで当てた挙動の調整\n\n' + '\n'.join('* ' + l_ for l_ in b_blog) + '\n')
    print('   %s: %d files, %d bytes (extract-verified; %d hits: 最低値 %d / 技終了時 %d differ, nothing else)' % (
        bpac, len(os.listdir(BFILES)), os.path.getsize(bpac), len(b_rows), n_, e_))
json.dump(weapons, open(W + '/weapons.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
# ---- weapon status table (調査記録 09 §9, README)
MAJOR = ('laser/wire', 'LASER', 'DROPPED')                                   # -> 近似 (BSDX laser chain / Kou visuals, or dropped)
GUESS = ('no direct hit', 'fallback projectile', 'go_counter', 'has no anim', 'BSDX line chain')   # -> 変換（推定あり）
def powers(sk):
    return [str(u['data']['bsdxInfoCollectionList'][0]['paramList'][0]) for o in walk(sk) if o.get('slotNum') == 41 and 'ceventHitUnitList' in o
            for u in o['ceventHitUnitList'] if u['unitSlotNum'] == 6]
def first_power(f, i):
    pw = powers(SHW[f]['skillList'][i]); return pw[0] if pw else '-'
lines = ['| # | 武装 | BFE | 種別 | 熱（実効/最大） | 直接ヒット威力 | 弾（共通 waz） | 甲テンプレ | 状態 | 近似・推定・未対応 |', '|---|---|---|---|---|---|---|---|---|---|']
for n, w in enumerate(weapons):
    sk = waz_skills[w['waz']]; kw_ = wmap[str(n)]
    shots = collections.OrderedDict()
    for o in walk(sk):
        if o.get('slotNum') == 48:
            tg = effect_target(o)
            if tg and tg[0] in (BULLET_FILE, LASER_FILE):
                shots['%s[%d] %s' % (SHARED[tg[0]], tg[1], first_power(*tg))] = 1
    major = [x for x in w['notes'] if any(k in x for k in MAJOR)]
    guess = [x for x in w['notes'] if any(k in x for k in GUESS)]
    st = '—' if w['bfe'] is None else ('近似' if major else '変換（推定あり）' if guess else '変換')
    kind = {0: '通常', 1: 'FC', 2: 'INIT'}[kw_['weaponCategory']] + ('格' if kw_['weaponType'] == 0 else '射') + ('（非表示）' if w['hidden'] else '')
    pw = powers(sk)
    lines.append('| %d | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
        n, w['name'], w['bfe'] if w['bfe'] is not None else '-', kind,
        '%d/%d' % (kw_['heatMinConsumption'] or kw_['heatMaxConsumption'], kw_['heatMaxConsumption']), '+'.join(pw) if pw else '-',
        ', '.join(list(shots)[:3]) + (' …' if len(shots) > 3 else '') if shots else '-', KWEP[str(w['kou'])]['weaponName'], st,
        '<br>'.join(x.replace('|', '/') for x in w['notes'])[:600] or '-'))
open(W + '/weapons_table.md', 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print('   weapons: %d (%d visible, %d hidden) ; status 変換 %d / 近似 %d' % (len(weapons), sum(1 for w in weapons if not w['hidden']),
      sum(1 for w in weapons if w['hidden']), sum(1 for l in lines[2:] if '| 変換 |' in l) + sum(1 for l in lines[2:] if '| 変換（推定あり） |' in l),
    sum(1 for l in lines[2:] if '| 近似 |' in l)))
print('   approximated:', ', '.join(l.split(' | ')[1] for l in lines[2:] if '| 近似 |' in l))
# -- provenance (調査記録 15): how each value was obtained, per weapon
import provenance
if not VARIANT110:
    prov_rows = [dict(no=i, name=w['name'], bfe=w['bfe'], kou=w.get('tpl_name', KWEP[str(w['kou'])]['weaponName']),
                      own=w.get('prov_own', []), bullets=w.get('prov_bul', {}),
                      extra=[] if w['bfe'] is not None else [('M', '甲のイニシャライザを複製（BFE に該当なし）')]) for i, w in enumerate(weapons)]
    prov_rows.insert(0, dict(no='-', name='基本性能・基本技', bfe=None, kou=C.PROV_BASIC_KOU, own=[e for e in rep.log if e[0] in ('BASIC', 'BASIC_ANIM')],
                             extra=list(C.PROV_BASIC_EXTRA)))
    provenance.write(P + '/' + C.NOTES_PROVENANCE, C.PROV_TITLE, prov_rows, list(C.PROV_HEADER))
    print('provenance:', P + '/' + C.NOTES_PROVENANCE)
rep.dump(W + '/report%s.txt' % ('_waz110' if VARIANT110 else '')); print('report:', W + '/report.txt')
