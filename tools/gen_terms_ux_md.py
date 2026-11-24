# -*- coding: utf-8 -*-
"""notes/41_terms_ux.md を tools/waz_terms_ux.json（体感の説明）と tools/waz_fields.json（技術メモ）から作る。
  python3 tools/gen_terms_ux_md.py            # リポジトリのルートで実行
説明文を直すときは tools/waz_terms_ux.json を直してから、これと GUI のビルド（resources へのコピー）をやり直す。"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U = json.load(open(os.path.join(ROOT, 'tools', 'waz_terms_ux.json'), encoding='utf-8'))
F = json.load(open(os.path.join(ROOT, 'tools', 'waz_fields.json'), encoding='utf-8'))
OUT = os.path.join(ROOT, 'notes', '41_terms_ux.md')

GROUPS = [
    ('見た目（絵）', range(0, 11)),
    ('位置と動き', range(11, 24)),
    ('動きの補正率（%。技を出すたびに 100 に戻る。重力だけは戻らない）', range(24, 34)),
    ('耐久・装甲・無敵・熱', range(34, 41)),
    ('攻撃', range(41, 45)),
    ('CPU・キャンセル・発射など', range(45, 52)),
    ('音・演出', range(52, 71)),
    ('ターンの流れ', range(71, 72)),
]
CLASSES = [
    ('CEventHit', '攻撃判定（slot 41 / 42）の中身'),
    ('CEventNokezori', 'のけぞり（攻撃判定の中の 地上 / 空中 / 空中→地上 / ダウン）'),
    ('CEventEffect', '発射（slot 48）の中身'),
    ('CEventVal', '値のイベント（多くのスロット共通）'),
    ('CEventValRandom', 'ばらつき付きの値のイベント'),
    ('CEventWazaSelect', '出す物の指定'),
    ('CEventSprite', '絵の指定（slot 0）'),
    ('CEventSlipHosei', '技後の慣性補正（slot 33）'),
    ('CEventTouch', '接触（slot 51）'),
    ('CEventChange', '変更処理（slot 71）'),
    ('CEventCharge', '溜め（slot 50）'),
    ('CEventBlink', '残像（slot 49）'),
    ('CEventSpriteYure', 'スプライト振動（slot 6）'),
    ('CEventSpriteAttr', 'スプライト属性（slot 7）'),
    ('CEventSe', '効果音（slot 52）'),
    ('CEventVoice', 'ボイス（slot 53）'),
    ('CEventEscape', 'CPU 回避（slot 45）'),
    ('CEventCpuButton', 'CPU ボタン入力（slot 46）'),
]


def cell(s):
    return (s or '').replace('|', '／').replace('\n', ' ')


def main():
    slots = {s['slot']: s for s in F['slots']}
    L = ['# 41 用語の体感メモ（ユーザー体験から見た各項目の意味）', '',
         '技データ（waz）と武装（mek）の各項目が、遊んだときに何として感じられるかをまとめたもの。GUI ツール（BsdxWorkshop v4）では、項目名・スロットの行・ツリーのスロット・のけぞりなどの枠にマウスを乗せると、同じ説明が「体感」として出る。',
         '', '* 確度: **確定** = exe の解析か実機で確認 / **推定** = データの使われ方や名前からの推定 / **不明**。',
         '* 単位: F = フレーム、px/F = 1 フレームに進むピクセル数、% は 100 が「そのまま」。',
         '* 元データ: 体感の説明 `tools/waz_terms_ux.json`、技術メモ `tools/waz_fields.json`。このファイルは `python3 tools/gen_terms_ux_md.py` で作り直す（手で直さない）。', '']
    L += ['## スロット（タイムラインの行）', '']
    for title, rng in GROUPS:
        L += ['### ' + title, '', '| slot | 名前 | 体感 | 確度 |', '|---|---|---|---|']
        for n in rng:
            s = slots.get(n, {}); u = U['slots'].get(str(n), {})
            L.append('| %d | %s | %s | %s |' % (n, cell(s.get('name_ja', '')), cell(u.get('ux', '')), u.get('conf', '')))
        L.append('')
    L += ['## 項目（イベントの中身）', '']
    for cn, title in CLASSES:
        c = F['classes'].get(cn)
        if not c:
            continue
        rows = []
        for f in c.get('fields', []):
            u = U['fields'].get(cn + '.' + f['key'])
            if u:
                rows.append((f['name_ja'], f['key'], u))
        for s in c.get('subobjects', []):
            u = U['subs'].get('%s#%d' % (cn, s['index']))
            if u:
                rows.append((s['name_ja'], 'サブ[%d]' % s['index'], u))
        if not rows:
            continue
        L += ['### ' + title, '', '| 名前 | 生の名前 | 体感 | 確度 |', '|---|---|---|---|']
        for name, raw, u in rows:
            L.append('| %s | %s | %s | %s |' % (cell(name), cell(raw), cell(u['ux']), u['conf']))
        if cn == 'CEventEffect':
            L += ['', '発射のサブのうち、スロットと同じ名前のもの（ﾍﾞｸﾄﾙ：速度、ｽﾌﾟﾗｲﾄ：拡大縮小 など）は、出した弾・エフェクトに対して同じ名前のスロットと同じ意味になる（GUI でも同じ説明を出す）。']
        L.append('')
    L += ['## 武装（mek）', '', '| 名前 | 生の名前 | 体感 | 確度 |', '|---|---|---|---|']
    for f in F['mek_weapon']:
        u = U['weapon'].get(f['key'])
        if u:
            L.append('| %s | %s | %s | %s |' % (cell(f['name_ja']), f['key'], cell(u['ux']), u['conf']))
    L.append('')
    open(OUT, 'w', encoding='utf-8', newline='\n').write('\n'.join(L))
    print('wrote', OUT, len(L), 'lines')


if __name__ == '__main__':
    main()
