#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""weapon_table.py - 機体の武装一覧（威力・補正・属性・早期廃熱・EX キャンセル）を、置いてある pac から Markdown で出す。読み取りのみ。

  python tools/weapon_table.py                      # 透: 改善版と原作再現版（通常版のパック）を 1 つの表に → 画面
  python tools/weapon_table.py -o out.md            # ファイルに書く（フォルダを渡すと <機体>_weapon_table_<日付>.md）
  python tools/weapon_table.py --variant modified   # 片方だけ（modified / 3b / both。既定 both）
  python tools/weapon_table.py --waz110             # waz110 版のパックから
  python tools/weapon_table.py --mech <機体>        # 別の機体（mods/*/mech_config.py の MEKA_NAME かフォルダ名）。既定 Tooru
  python tools/weapon_table.py --pac <path>         # 任意の pac 1 つ（--variant の代わり）

入力は pac そのもの（ビルドの中間ファイルに頼らない）: pac を展開し、WazaGroup.grp・<MEKA_NAME>.mek・*.waz を NeXAS_DX の PortTool で
JSON に戻して読む。pac に無い共通 waz（Effect・Tama01 など）はバニラの JSON。展開結果は pac の sha256 ごとに
<PROJECT>/_ws/table_cache/ にキャッシュ（同じ pac なら 2 回目からは数秒）。Java 17 と PortTool のスナップショット（ビルドと同じ）が要る。

機体の情報は mods/<機体>/mech_config.py から: MEKA_NAME（自分の waz・mek の名前）、MOD_DIR（パックの置き場）、MEK_BASIC['mekName']（表題）。
新しい機体は mech_config.py があれば --mech で指定できる（パックの置き場所が違えば --pac）。

列（ユーザー指定 2026-11-09、11-16 に属性・早期廃熱・EX キャンセルを追加）:
  威力       = 画面に出るダメージ = 内部の威力（slot 41 ヒットの slot 6 攻撃力）x1.5（補正・溜め・防御補正なし）
  最低補正   = 最低ダメージ（minDamage）÷ 威力
  初段補正   = startComboCorrection、補正 = endCorrection（技終了時）、ヒット毎補正 = midComboCorrection（0 でないものがあれば列を出す）
  属性       = ヒットのフラグ int2: 2 = 感電、4 = 燃焼（時間 = int22 F）
  早期廃熱   = int2 の 8 / 16
  EX キャンセル = 自分の技の slot 47（ｷｬﾝｾﾙﾌﾗｸﾞ）の値 3 の区間。ターンごとに「T番号〈そのターンに入る条件〉F開始–終了（ターンの最後 F）」
対メカ（attackTargetType 1）で威力 > 0 のヒットだけ（弾・ライン・エフェクトも辿る。ヒットエフェクトは除く）。値の違うヒットは 1 行ずつ。
"""
import argparse, csv, datetime, glob, hashlib, importlib.util, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WS = os.path.join(ROOT, '_ws', 'proj')
BUILD = WS if os.path.isdir(WS) else ROOT          # PC はビルド用の写し（PortTool のスナップショット・バニラ JSON がある）
os.environ.setdefault('BSDX_PROJ', BUILD)
sys.path.insert(0, HERE)
import bfe2bsdx_common as BC                       # noqa: E402  porttool / VAN（BSDX_PROJ を見る）
import nexaspac                                    # noqa: E402

CACHE = os.path.join(ROOT, '_ws', 'table_cache')


# ------------------------------------------------------------------ 機体
def find_mech(name):
    cands = sorted(glob.glob(os.path.join(ROOT, 'mods', '*', 'mech_config.py')))
    for p in cands:
        spec = importlib.util.spec_from_file_location('mech_config_%d' % abs(hash(p)), p)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        folder = os.path.basename(os.path.dirname(p))
        if name.lower() in (getattr(m, 'MEKA_NAME', '').lower(), folder.lower(), folder.lower().split('_')[-1]):
            return m
    sys.exit('機体 %s の mech_config.py が見つからない（候補: %s）' % (name, ', '.join(os.path.relpath(p, ROOT) for p in cands)))


# ------------------------------------------------------------------ pac -> JSON（sha256 ごとにキャッシュ）
def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest().upper()


def pac_json(pac, meka, refresh=False):
    sha = sha256(pac)
    d = os.path.join(CACHE, sha[:16])
    done = os.path.join(d, 'done.txt')
    if refresh and os.path.isdir(d):
        shutil.rmtree(d)
    if not os.path.isfile(done):
        raw = os.path.join(d, 'raw')
        nexaspac.extract(pac, raw)
        files = {os.path.basename(p): p for p in glob.glob(os.path.join(raw, '**', '*'), recursive=True) if os.path.isfile(p)}
        want = [n for n in files if n.lower().endswith('.waz') or n.lower() in ('wazagroup.grp', (meka + '.mek').lower())]
        jobs = [['b2j', 'bsdx', files[n], os.path.join(d, 'json', n + '.json')] for n in sorted(want)]
        os.makedirs(os.path.join(d, 'json'), exist_ok=True)
        print('pac %s… を JSON に戻しています（%d ファイル、初回だけ）' % (sha[:8], len(jobs)), file=sys.stderr)
        BC.porttool(*jobs)
        shutil.rmtree(raw, ignore_errors=True)
        open(done, 'w', encoding='utf-8').write(pac + '\n')
    return sha, os.path.join(d, 'json')


class Data:
    def __init__(self, pac, meka, refresh):
        self.sha, j = pac_json(pac, meka, refresh)
        self.j = j
        low = {n.lower(): n for n in os.listdir(j)}
        g = BC.jload(os.path.join(j, low['wazagroup.grp.json']))
        self.groups = [(w.get('wazaDisplayName') if w.get('existFlag') else None) for w in BC.glist(g)]
        self.low = low
        self._w = {}
        mek = low.get((meka + '.mek.json').lower())
        if not mek:
            sys.exit('pac に %s.mek が無い' % meka)
        self.mek = BC.jload(os.path.join(j, mek))
        self.self_file = self.groups.index(meka)

    def waz(self, f):
        """WazaGroup 番号 f の skillList（pac にあれば pac の、無ければバニラ）。"""
        if f in self._w:
            return self._w[f]
        name = self.groups[f] if 0 <= f < len(self.groups) else None
        sl = None
        if name:
            n = self.low.get((name + '.waz.json').lower())
            p = os.path.join(self.j, n) if n else os.path.join(BC.VAN, 'waz', name + '.waz.json')
            if os.path.isfile(p):
                sl = BC.jload(p)['skillList']
        self._w[f] = sl
        return sl


# ------------------------------------------------------------------ ヒット
def walk(o, acc, refs, slot=None):
    if isinstance(o, dict):
        if 'unitDescription' in o:
            slot = o.get('unitQuantity')
        if 'minDamage' in o:
            pw = 0
            for u in o.get('ceventHitUnitList') or []:
                if u.get('unitSlotNum') == 6:
                    pw = sum(u['data']['bsdxInfoCollectionList'][0]['paramList'])
            fl = o.get('int2', 0) or 0
            el = '感電 %dF' % o.get('int22', 0) if fl & 2 else '燃焼 %dF' % o.get('int22', 0) if fl & 4 else '-'
            acc.append(dict(slot=slot, tgt=o.get('attackTargetType'), hc=o.get('hitCount'), mn=o['minDamage'], pw=pw,
                            st=o.get('startComboCorrection', 0), md=o.get('midComboCorrection', 0),
                            en=o.get('endCorrection', 0), el=el, eh='○' if fl & 0x18 else '-'))
            return
        if 'wazFileNo' in o and 'wazSequenceNo' in o and o.get('description') != 'ヒットエフェクト':
            refs.append((o['wazFileNo'], o['wazSequenceNo']))
        for v in o.values():
            walk(v, acc, refs, slot)
    elif isinstance(o, list):
        for v in o:
            walk(v, acc, refs, slot)


def trace(D, f, s, seen):
    """技 (f, s) と、そこから辿れる弾・ライン・エフェクト（ヒットエフェクトは除く）のヒット。"""
    sl = D.waz(f)
    if (f, s) in seen or sl is None or not 0 <= s < len(sl) or not sl[s]:
        return []
    seen.add((f, s))
    acc, refs = [], []
    walk(sl[s], acc, refs)
    for r in refs:
        if r[0]:
            acc += trace(D, r[0], r[1], seen)
    return acc


# ------------------------------------------------------------------ EX キャンセル（slot 47 = 3）とターンの入り方
COND = {(0,): '', (2, 7, 16): '着地', (2, 6, 0, 0): '命中', (2, 0, 0, 2): 'ループ', (2, 3, 6, 2): '接近',
        (2, 4, 3): 'キー離し', (1, 0): '確率'}


def _objs(turn, slot):
    return [o for u in turn['skillUnitCollection'] if u['unitQuantity'] == slot for o in u['skillInfoObjectList']]


WORD = {'着地': '着地してから', '命中': '当たってから', 'ループ': '繰り返した後', '接近': '相手に近づいてから',
        'キー離し': 'ボタンを離してから', '確率': '（確率で分かれた後）', '条件': '（条件で分かれた後）'}


def turn_routes(skill):
    """T0 から各ターンへの道のりのうち、条件の数が一番少なく、次に短いもの。
    値 = (通った条件のリスト, 最後の条件を満たしてからそのターンに入るまでのフレーム数)。届かないターンは入らない。
    技の頭（T0 の F0）の「着地していたら」は「地上で出したとき」（'地上'）として扱う。
    フレーム数はターンを出るジャンプのフレーム（slot 71 の startFrame）を足していく目安（ターンの継ぎ目で ±1F の誤差があり得る）。"""
    ph = skill.get('phasesInfo') or []
    best = {0: ([], 0)}; queue = [0]; done = set()
    key = lambda r: (len(r[0]), r[1])
    while queue:
        queue.sort(key=lambda t: key(best[t]))
        t = queue.pop(0)
        if t in done:
            continue
        done.add(t)
        conds, off = best[t]
        for o in _objs(ph[t], 71):
            dst = o['bsdxInfoCollectionList2'][0]
            if dst['typeList'][:1] != [0] or len(dst['typeList']) < 2:
                continue
            n = t + 1 if dst['typeList'][1] == 0 else dst['paramList'][0] if dst['typeList'][1] == 1 else None
            if n is None or not 0 <= n < len(ph):
                continue
            c = '＋'.join(COND.get(tuple(x['typeList']), '条件') for x in o['bsdxInfoCollectionList1'])
            if c == '着地' and t == 0 and o['startFrame'] == 0 and not conds:
                c = '地上'
            cand = (conds + [c], 0) if c else (conds, off + o['startFrame'])
            if n not in best or key(cand) < key(best[n]):
                best[n] = cand; done.discard(n); queue.append(n)
    return best


def _label(conds):
    words = [WORD.get(c, WORD['条件']) for c in conds if c != '地上']
    if '地上' in conds:
        return '地上で出して' + (words[-1] if words else 'から')
    return words[-1] if words else '出してから'


def ex_windows(skill, turns=False):
    """EX キャンセルの区間。既定は遊ぶ人向け（「出してから 2〜9F」「当たってから 0〜79F」）、turns=True は開発用（ターン番号）。"""
    ph = skill.get('phasesInfo') or []
    routes = turn_routes(skill)
    raw = []
    for t, turn in enumerate(ph):
        segs = sorted((o['startFrame'], o['endFrame']) for o in _objs(turn, 47) if o.get('int4') == 3)
        if segs:
            raw.append((t, segs, max([o['endFrame'] for o in _objs(turn, 71)] or [0])))
    if turns:
        out = []
        for t, segs, last in raw:
            r = routes.get(t)
            tag = '〈?〉' if r is None else ('〈%s〉' % '→'.join(r[0]) if r[0] else '')
            out.append('T%d%s F%s（〜F%d）' % (t, tag, '・'.join('%d–%d' % x for x in segs), last))
        return out
    by = {}
    for t, segs, last in raw:
        r = routes.get(t)
        lb, off = (_label(r[0]), r[1]) if r else ('（ほかの流れ）', 0)
        by.setdefault(lb, set()).update((x + off, y + off) for x, y in segs)
    if '出してから' in by and '地上で出してから' in by:    # GROUND_ARMOR の地上版・空中版で同じ区間なら 1 つに
        by['地上で出してから'] -= by['出してから']
        if by['地上で出してから']:                          # 地上と空中で区間が違う技（タックルなど）は空中側を明示
            by['空中で出してから'] = by.pop('出してから')
    out = []
    for lb in sorted(by, key=lambda l: (not l.endswith('出してから'), l)):
        m = []
        for x, y in sorted(by[lb]):
            if m and x <= m[-1][1] + 1:
                m[-1][1] = max(m[-1][1], y)
            else:
                m.append([x, y])
        if m:
            out.append('%s %s' % (lb, '・'.join('%d〜%dF' % tuple(v) for v in m)))
    return out

# ------------------------------------------------------------------ 表
def ht(hc):
    return '' if hc == 1 else '（多段）' if hc is None or hc < 0 or hc >= 9999 else '（%d 回）' % hc


def col(u, f):
    vals = [f(x) for x in u]
    return vals[0] if len(set(vals)) == 1 else '<br>'.join(vals)


TURNS = False


def rows_of(D):
    rows = []
    for k, v in sorted(D.mek['mekWeaponInfoMap'].items(), key=lambda kv: int(kv[0])):
        hs = [h for h in trace(D, D.self_file, v['wazSequence'], set()) if h['slot'] == 41 and h['tgt'] == 1 and h['pw'] > 0]
        u = []
        for h in hs:
            key = (int(h['pw'] * 1.5), h['mn'], h['st'], h['md'], h['en'], h['hc'], h['el'], h['eh'])
            if key not in u:
                u.append(key)
        sl = D.waz(D.self_file)
        ex = ex_windows(sl[v['wazSequence']], TURNS) if 0 <= v['wazSequence'] < len(sl) and sl[v['wazSequence']] else []
        rows.append((k, v['weaponName'], v['weaponCategory'], sorted(u, key=lambda x: -x[0]), ex))
    return rows


def table(rows):
    show_md = any(x[3] for r in rows for x in r[3])
    head = ['No', '武装', '威力', '最低補正', '初段補正', '補正'] + (['ヒット毎補正'] if show_md else []) + \
           ['属性', '早期廃熱', 'EX キャンセル']
    R = []
    for k, n, cat, u, ex in rows:
        name = n + ('（FC）' if cat == 1 else '')
        exc = '<br>'.join(ex) if ex else '-'
        if not u:
            R.append([k, name] + ['-'] * (len(head) - 3) + [exc])
            continue
        cells = [k, name, '<br>'.join('%d%s' % (x[0], ht(x[5])) for x in u),
                 '<br>'.join('%d%%' % round(x[1] * 100 / x[0]) for x in u),
                 col(u, lambda x: '%d%%' % x[2]), col(u, lambda x: '%d%%' % x[4])]
        if show_md:
            cells.append(col(u, lambda x: '%d%%' % x[3]))
        cells += [col(u, lambda x: x[6]), col(u, lambda x: x[7]), exc]
        R.append(cells)
    return head, R, show_md


def md_table(head, R):
    return ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)] + ['| ' + ' | '.join(r) + ' |' for r in R]


LEGEND = [
    '* **威力**: 画面に出るダメージ（内部の威力 ×1.5、補正・溜め・防御補正なし）。「多段」は 1 つの判定が何度も当たるヒット',
    '* **最低補正**: 最低ダメージ ÷ 威力。**初段補正**: コンボの最初のヒットのときだけ足される補正。**補正**: 技が終わったときに足される補正',
    '* **属性**: 感電 / 燃焼（数字は続く時間 F）。**早期廃熱**: ○ = 当てた相手がのけぞり・ダウン中でも自機の廃熱が始まる',
    '* **EX キャンセル**: キャンセルボタンで EX キャンセルできるタイミング。「出してから 2〜9F」= 技を出して 2 フレーム目から 9 フレーム目まで'
    '（60F = 1 秒）。「当たってから」「着地してから」はそのときから数える。「地上で出して〜」は地上で出したときだけの区間。'
    '空振りのまま進んだときの数え方で、フレームは目安（±1F 程度ずれることがある）',
    '* 対メカのヒットだけ（弾・ライン・エフェクトも含む）。値の違うヒットは 1 行ずつ。行の並びは威力の大きい順',
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--mech', default='Tooru')
    ap.add_argument('--variant', choices=['both', 'modified', '3b'], default='both')
    ap.add_argument('--waz110', action='store_true')
    ap.add_argument('--pac', help='任意の pac（--variant / --waz110 の代わり）')
    ap.add_argument('--turns', action='store_true', help='EX キャンセルをターン番号で出す（開発用）')
    ap.add_argument('--refresh', action='store_true', help='キャッシュを使わずに読み直す')
    ap.add_argument('-o', '--out', help='出力先（.md のファイルかフォルダ）。同じ名前の .csv も書く（Excel 用、UTF-8 BOM 付き）')
    A = ap.parse_args()
    global TURNS
    TURNS = A.turns
    M = find_mech(A.mech)
    meka, title = M.MEKA_NAME, M.MEK_BASIC.get('mekName', M.MEKA_NAME)
    base = os.path.join(ROOT, *M.MOD_DIR.split('/'), *(['variantB_waz110'] if A.waz110 else []))
    if A.pac:
        targets = [('指定の pac', A.pac)]
    else:
        targets = [(lb, os.path.join(base, *sub, 'Update3.pac')) for v, lb, sub in
                   (('modified', '改善版（modified）', ['modified']), ('3b', '原作再現版（3b）', []))
                   if A.variant in ('both', v)]
    L = ['# %s 武装一覧（威力・補正・属性・早期廃熱・EX キャンセル）' % title, '',
         '作成 %s、`python tools/weapon_table.py%s`。' % (datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
                                                       ' '.join([''] + sys.argv[1:])), ''] + LEGEND
    CSV = []
    for lb, pac in targets:
        if not os.path.isfile(pac):
            sys.exit('pac が無い: %s' % pac)
        D = Data(pac, meka, A.refresh)
        head, R, show_md = table(rows_of(D))
        T = md_table(head, R)
        CSV.append((lb + (' waz110' if A.waz110 else ''), D.sha[:8], head, R))
        L += ['', '## %s%s' % (lb, ' waz110' if A.waz110 else ''), '',
              'パック: `%s`（sha256 %s…）' % (os.path.relpath(pac, ROOT).replace('\\', '/'), D.sha[:8]) +
              ('' if show_md else '。ヒットごとに足される補正は全ヒットで 0'), ''] + T
    text = '\n'.join(L) + '\n'
    if A.out:
        out = A.out
        if os.path.isdir(out):
            out = os.path.join(out, '%s_weapon_table_%s_%s.md' % (meka.lower(), 'pac' if A.pac else A.variant,
                                                                   datetime.date.today().strftime('%Y%m%d')))
        open(out, 'w', encoding='utf-8', newline='\n').write(text)
        cp = os.path.splitext(out)[0] + '.csv'
        with open(cp, 'w', encoding='utf-8-sig', newline='') as f:     # BOM 付き: Excel でそのまま開ける
            w = csv.writer(f)
            many = len(CSV) > 1
            for i, (lb, sh, head, R) in enumerate(CSV):
                if i == 0:
                    w.writerow((['版'] if many else []) + head)
                elif head != CSV[0][2]:
                    w.writerow([]); w.writerow((['版'] if many else []) + head)
                for r in R:      # セルの中の複数行（ヒットごと）は改行のまま入れる
                    w.writerow(([lb] if many else []) + [c.replace('<br>', '\n') for c in r])
        print('書き出し:', out, cp)
    else:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stdout.write(text)


if __name__ == '__main__':
    main()
