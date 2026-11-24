# 04 BALDR FORCE EXE (BFE) 形式調査と TOORU 移植の下調べ（Stage 2）

対象: `/path/to/GIGA/BALDRFORCEEXE/` に置いたファイル（読み取り専用）。
作業出力: `/path/to/workspace/work/bfe_*`。作成したツール: `/path/to/workspace/tools/bfepac.py`、`bfe_gr2.py`、`bfe_spr.py`、`bfe_waz.py`。
凡例: 【確定】=データで検証済み、【推測】=根拠はあるが未検証。

---

## 0. 要約

* **BaldrForce.exe は保護（パック/暗号化）されている**【確定】。セクション名はランダム（`ubrtjaiu`、`xocgxhdl`）で、`.detour` セクションと `skeleton.dll!TestHello` の import がある。タイムスタンプは 2017-11-03。exe 内には意味のある文字列が一つもない（import 名だけ）。このため **exe の静的解析（読み込み処理、ステータス表、技パラメータの意味）は今のところできない**。暗号化されていない exe が必要（§6）。
* 古い PAC 形式は解析済み【確定】。`tools/bfepac.py` で 3 つの pac（Table、Update、Exe）を全部展開した。**Exe.pac に入っている開発ツールは `AnimeEditer.exe` だけ**（2000-12 に VC6 でビルドされた、UI 用 .ANI/.BMP アニメのエディタ）。機体スプライトやスキルのエディタではない。
* **GR2 は完全にデコードできる**【確定】（GARbro の NeXAS GRP 実装と同じ LZ）。TOORU の 80 枚はすべて想定サイズどおりに展開でき、PNG に変換済み。8bpp パレットで、**透過色はパレット index 255**。
* **SPR は構造を完全に解析した**【確定：2 ファイルともファイル末尾まで矛盾なく読める】。8 方向 × フレーム（パターン）、32 個の固定判定スロット、512 個の固定アニメスロット。**BSDX の SPM と同じ系譜**で、どちらも 8 方向ページ方式。ページ番号が 8 の倍数で、kou.spm の「立ち」は BFE の slot 6 とページ列 (0,8,16,8) まで一致する。スプライトの画素サイズもほぼ同じ（立ち絵は BFE 80×96、BSDX 75×88）。
* **WAZ はレコードの境界を完全に解析した**【確定】。**TOORU.WAZ は 213 技** = 通常武装 63 種 × Lv1-3（189）+ マーカーミサイル 3 + 必殺技 21。1 技 = 108 バイトのヘッダ + phase × (392 バイト固定ブロック + スプライトイベント n × 48 バイト)。固定ブロックの中で意味が確定しているのは Tama 参照（+0xF0）など一部だけ。
* **Tama.dat は WAZ と同じ形式**【確定】で、弾・爆風など 453 技が入っている。BSDX の Tama01-05.waz に相当する。TOORU が直接参照するのは 148 個で、連鎖参照を含めると 194 個。
* **CPU（AI）** は生の構造体ダンプ。ヘッダ + 96 バイトのレコード列 + 54 バイトのレコード列。「無制限」を 9999/-999/999 で表す点が BSDX の MEK_AI と同じ。中身の解析は一部のみ。
* **機体ステータス（HP・速度など）は、渡されたデータファイルのどこにも見つからない**。exe 内にあると推定する【推測】。exe が保護されているので未確認。
* **移植の見通し**: 見た目（スプライト・アニメ）の移植は **難易度が低く、ほぼ機械的に変換できる**。技の挙動を忠実に再現するのは **難易度が高い**（固定ブロックの意味が不明で、exe も読めない）。現実的な方針は、BSDX の甲（Kou）の技をテンプレートにして、スプライト参照・ダメージ・タイミングを BFE の値で置き換えること。

---

## 1. 古い PAC 形式（tools/bfepac.py）

```
+0x00 'PAC' + 1 バイト（0x00 または 'w'。リーダーは見ていない）
+0x04 u32 count
+0x08 u32 pack_type   0=無圧縮 1=LZSS 2=Huffman 3=zlib 4=zlib/無圧縮混在
+0x0C entry[count] × 0x4C バイト:
        char name[0x40] (cp932, NUL 埋め) / u32 offset(絶対位置) / u32 unpacked / u32 packed
データはインデックスの直後に続く（BSDX の新形式のように「インデックスがファイル末尾」ではない）
LZSS = Okumura 方式（窓 4KB、初期位置 0xFEE、窓の初期値 0、フラグ LSB→、1=リテラル）
```
3 つとも pack_type=1。全エントリでサイズが一致した。使い方: `python3 tools/bfepac.py list|extract <pac> [outdir]`。

### 1.1 中身（展開先 `/path/to/workspace/work/bfe_extracted/{Table,Update,Exe}/`）

| pac | 件数 | 中身 |
|---|---|---|
| Table.pac | 13 | BGMInfo, CGInfo, ChapterFlowInfo, DatabaseInfo, **EquipmentInfo**, FlgInfo, FlowInfo, ItemInfo, ReplayInfo, SceneInfo, ScriptInfo, StandInfo, VisualInfo（いずれも .DAT。固定長レコードで、ほとんどがテキスト） |
| Update.pac | 64 | パッチ。シナリオ .bin（ayane/minori/ren/bachelor…）、Replay03-41.bin、Title.bin、DatabaseInfo/EquipmentInfo/FlowInfo/SceneInfo.DAT、GameMenu/SaveMenu/SkillUp の .bmp と .ani、107990.wav |
| Exe.pac | 35 | **AnimeEditer.cfg / AnimeEditer.exe**、シナリオ .bin 数本、CGInfo/DatabaseInfo/EquipmentInfo/ItemInfo/VisualInfo.DAT、ヒロイン系 BMP 6 枚（O*.bmp, 640×480 24bit：**中身は開いていない**）、STAFFROLL*.ANI/bmp、Thum_92x.bmp（サムネイル：**開いていない**）、TITLE_* |

### 1.2 開発ツール AnimeEditer.exe（PE32、VC6、2000-12-21 ビルド。DirectDraw/DirectInput を使う）
* メニュー文字列は「スプライト登録(F1)/スプライト編集(F2)/アニメ登録(F3)/アニメ編集(F4)、左右反転、グリッドにスナップ、自動中心点設定、自動矩形補正」。編集対象は **`.ANI` + `.BMP`**（`ANI\0` + u32 + bmp 名 + 矩形・フレームの表。GameMenu.ani や TITLE_MENU.ANI がこれにあたる）。
* つまり **メニュー・タイトル UI のアニメを編集するツール**で、機体の SPR/WAZ を作るツールではない。Bmp/Meka にある 5 個の `.ani` は、機体選択画面などの UI 部品と推測する。AnimeEditer.cfg（68 バイト）は環境設定値（グリッドサイズなど）。
* 結論: 開発ツールとして使える価値は限られる。それでも .ANI 形式の資料にはなるので、Wine などで動かせれば .ANI を確認できる。

### 1.3 Table の DAT（戦闘に関係するもの）
* **EquipmentInfo.DAT**: 240 バイト × 85 件。cp932 の武装説明文だけで数値はない【確定】。0-62 が通常武装、63 は空き、64-84 が必殺技。順番は TOORU.WAZ と一致する（§4.3）。
* ItemInfo.DAT（292 バイト × 50）: 戦闘以外のアイテムとアンロック条件。type=4 の行は「必殺技の入手条件」。ステータス値は入っていない。
* それ以外（CG/Scene/Flow/Stand/Visual…）は ADV 用。中身は見ていない。

---

## 2. GR2 画像（tools/bfe_gr2.py）

```
+0x00 'GR2'   +0x03 u16 bpp(=8)   +0x05 u32 w   +0x09 u32 h
+0x0D u32 unpacked_size (= w*h + 0x300)
+0x11 u32 ctl_bits ; ctl[(bits+7)/8] (LSB→) ; u32 data_size ; data
  bit0 → リテラル 1 バイト / bit1 → u16 w: len=(w&0x1F)+1, dist=(w>>5)+1   （GR3 は 3bit/13bit）
画素: 8bpp index、行は上から下【確定：目視】。パレット: 末尾 256×RGB（R,G,B の順）。
透過: index 255【確定：80 枚すべてで最頻値が 255。RGB は紫・緑・黄などシートごとに違うので、色ではなく index で判定する】
```
* tooru001..080 の 80 枚はすべて想定サイズどおりに展開できた（640×2400 から 392×184 まで）。DebugEft.grp は 640×8。
* PNG 出力: `/path/to/workspace/work/bfe_png/tooruNNN.png`（RGBA、index255→α0）。目視確認に使ったのは 2 枚（tooru002 のシート、SPR から合成したフレーム 0-15）だけで、どちらも機体スプライト。
* 使い方: `bfe_gr2.py info|png|unspr ...`

---

## 3. SPR（スプライト・アニメ定義、tools/bfe_spr.py）

コンテナは `'SPR' + u32 unpacked_size + GR2 と同じ LZ`。展開後の構造は以下【確定：tooru・akira とも末尾まで読め、src 矩形 8856 個がすべてシート内に収まり、dst と src のサイズも一致】:

```
u16 imageCount ; char name[]×imageCount (NUL 終端、拡張子なし → <name>.grp)
u16 frameCount                      tooru=3960 (=495 パターン × 8 方向), akira=568
frame:
  u32 partCount ; u16 0
  part × partCount (40B): u16 drawAttr(0/1-3/8/0x400/0x800…【意味は推測】) , u16 mirror(0/1),
                          u16 imageNo, u16 0x12, i32 dst[l,t,r,b], i32 src[l,t,r,b]
  u32 frameAttr (0/8/0x400/0x800…)
  i32 rect[32][4]   判定・マーカー用の 32 スロット（全部 0 なら未使用）
anim[512]（スロット数は固定。スロット番号がそのままエンジンの動作 ID）:
  u16 patCount ; pat × patCount: u16 baseFrame(8 の倍数), u16 wait, i32 0
```
* **8 方向**【確定：目視】。baseFrame+0..7 は正面 → 右斜め前 → 右 → 右斜め後 → 背面 → 5..7（3..1 を mirror=1 で反転したもの）。
* tooru: 画像 80 枚、パターン 495、使用中のアニメスロット 385/512（最大 388）。
* 判定スロットの使われ方（tooru）: 14/15 = 4×4 の点（手や銃口の位置。全フレームの約 90% で使用）、5/6 = 幅 4 の縦長矩形、1/2/4/10-12/16-20 = 40px 前後の矩形（攻撃判定やくらい判定と推測）。

### 3.1 BSDX の SPM との対応

| 項目 | BFE SPR | BSDX SPM（VER-2.00） | 変換 |
|---|---|---|---|
| 画像 | 8bpp GR2、名前のリスト | PNG 名のリスト（アトラス） | GR2→RGBA PNG（そのまま、またはアトラスに再パック） |
| 8 方向 | 8 ページすべてを保持（5-7 は反転） | **5-7 のページは空**。anim 側の animRotateDirection=3 と animReverseDirection でエンジンが反転する | 方向 0-4 だけ書き出し、5-7 は空ページにする |
| パーツ | part{img,mirror,dst,src} | chip{imageNo,dst,w,h,src,drawOption,value,option} | ほぼ 1 対 1。drawAttr→drawOption の対応は要確認 |
| 判定 | 32 スロット固定、各 16B | hitFlag ビット + 該当分だけ {unk0 種別, rect, unk1, unk2} | **スロットの意味が違う**（BFE 14/15 の点 ≒ BSDX 18/19、BFE 5/6 の縦線 ≒ BSDX 14/15【推測】）。対応表を作る必要がある |
| アニメ | 512 固定スロット、名前なし | 名前付き（立ち/歩き1…）、可変個 | **スロット→動作名の対応表が必要**。わかっているのは slot6=立ち（ページ列まで一致）、slot0=歩き1 だけ |
| 寸法 | 立ち 80×96 px | 立ち 75×88 px | **拡大縮小なしで使える** |

BSDX の spm 1 本あたり、ページ数は 495×8=3960 程度になる見込み（kou.spm は 16333 ページ、559 アニメ）。

---

## 4. WAZ（技、tools/bfe_waz.py）

### 4.1 構造【確定：TOORU.WAZ・akira.waz・Tama.dat の 3 つとも末尾ちょうどまで読める】
```
u16 skillCount
skill:
  header 108B (0x6C)   ※MSVC デバッグビルドの構造体をそのまま書き出したもの。0xCC は未初期化領域の埋め値
    +0x00 char name[40]   cp932。NUL の後は以前のバッファの残骸や 0xCC
    +0x2A u16 消費ヒート【推測：ｱｰﾑｼﾞｬﾌﾞ=5（説明文に「最も減りが少ない」とある）、必殺技=130】
    +0x2C u16 ?（9 / 1 / 9999）
    +0x30 u16 次の Lv までの経験値【推測：600→300→0（Lv3=0）】
    +0x34 i32 ?（25-240）   +0x38 i32 ?（0/-5/-7）
    +0x3C u8×3 分類フラグ？（01 02 00 / 01 03 00 / 07 07 00=マーカー）
    +0x3F u8[43] phase 遷移表と思われる値（1,2,3,… を 0x63=99 で埋めたもの）
    +0x6A u8 phaseCount
  phase × phaseCount:
    392B 固定パラメータブロック
    u32 nEv ; event × nEv (48B)
```
**スプライトイベント（48B）**: +0 u16 開始フレーム、+2 u16 終了フレーム（100=最後まで？）、+4 i16 **SPR アニメスロット**（-1..388。参照先のスロットはすべて定義済みだった【確定】）、+6 i16（-1 または 336.. など）、+8 u16（1/257…ループ指定？）、+0xA =45、+0x1E =100、+0x22..+0x28 =256×4（拡大率 256=1.0？）、+0x2A/+0x2C =64。

**392B 固定ブロック（判明分）**: **+0xF0 i16 = Tama.dat の技 index（-1=なし）【確定：ﾊﾝﾄﾞｶﾞﾝ Lv1-3→Tama 12/13/14、ｼｮｯﾄｶﾞﾝ→18/19】**。+0x9A..+0xA0 にダメージ系と思われる値（50/500/100）、+0x13C に効果音か Effect の ID と思われる値がある。残りの約 180 フィールドは値の分布しかわかっていない。値の範囲を見る限り、移動ベクトル、ヒットストップ、のけぞり、装甲、キャンセル可否、SE などが入っている（BSDX の 72 スロットの元になったものと推測）。

### 4.2 BSDX・BHE の waz との差
* BHE（83 スロット）と BSDX（72 スロット）は、「phase × N 個の型付きスロット（CEvent クラス）、各スロットに count+可変数のイベント、さらに start/end の時間区間」という汎用の形。
* BFE は **phase × 固定構造体（392B）+ スプライトイベント列だけ**。BSDX の汎用スロット（位置・ベクトル・攻撃：メカ・SE…）が、BFE では固定フィールドとして埋め込まれている。概念（phase、フレーム区間、スプライト参照、弾を技として呼ぶ）は共通だが、**バイナリとしての互換性はまったくない**。
* **BFE の WAZ には基本動作（立ち、歩き、ダッシュ、ジャンプ、被弾、ダウン）が一つも入っていない**【確定】。これらは exe 側で SPR のアニメスロット（WAZ から参照されていない slot 3-10、13-23、32-50 など）を直接再生していると推定する。BSDX では基本動作も waz の skill（mek の PairBlock から参照）なので、**変換時にはこれらを新たに作る必要がある**。
* 弾は、BFE では Tama.dat（453 技・共通）、BSDX では Tama01-05.waz と CEventWazaSelect(wazFileNo, seq) で、考え方は同じ。

### 4.3 TOORU の技構成（213 = 0..212）
* 0-188: 通常武装 63 種 × Lv1/2/3（EquipmentInfo の i 番 → waz の 3i..3i+2）。格闘系（ｱｰﾑｼﾞｬﾌﾞ〜ﾏｲﾝｽｲｰﾊﾟ、0-89）、ｽﾌﾟﾚｯﾄﾞﾊﾟﾝﾁ・ｴﾈﾙｷﾞｰﾌｨｰﾙﾄﾞ、射撃（ﾊﾝﾄﾞｶﾞﾝ〜対空ｽﾌﾟﾚｯﾄﾞﾎﾞﾑ）、ﾚｰｻﾞｰ系、防御・ﾋﾞｯﾄ系、ｸﾞﾗﾋﾞﾃｨﾌｨｰﾙﾄﾞ（186-188）。
* 189-191: ■マーカーミサイル（非公開・開発用と推測）。
* 192-212: 必殺技 21 種（ｷｬﾉﾝﾌﾞﾚｲｶｰ、T・K・O、月華衝、ﾒｶﾞ･ﾌﾞｰｽﾄｱｯﾊﾟｰ…ﾏﾙﾁﾌﾟﾙﾐｻｲﾙ）= EquipmentInfo 64-84。
* phase 数は 1-14（3 phase が 100 技で最多）。phase の合計は 716、スプライトイベントは 905。参照しているアニメスロットは 279 種。
* 一覧 JSON: `/path/to/workspace/work/bfe_waz/TOORU.json`（akira.json、Tama.json もある）。

---

## 5. CPU（AI）・BatVoice・ステータス

* **CPU**（TOORU.CPU 6020B、akira.cpu 1646B）: 生の構造体ダンプ（ヒープのポインタがそのまま残っている）。
  * ヘッダ: 約 0x36 バイト（u16 群に 200/25/10/3/10/100/10/100/1000 など、+0x22 から 40,121,122,123,124,41、+0x2E に件数（akira=11、TOORU=13）、その直後にポインタの残骸）。
  * 本体: 96B レコード × 件数（発動距離 500/600、確率 100、角度 -64/64、9999/-999/999 = 無制限）と、それに続く 54B レコード列（移動系と推測）。
  * BSDX の MEK_AI（CCpuEventMove / CCpuEventAttack、発動範囲 Min/Max、角度範囲、-999=無制限）と**考え方は同じで、直系の祖先**と推測する。フィールドごとの対応付けは未着手。
* **BatVoice**（akira.dat）: `char[32] × 4 スロット × 12 種 = 1536B` の WAV 名表【確定】。BSDX の BatVoice（builtin 13 種）に対応する。
* **ステータス**: HP・速度・装甲などの表は、WAZ、CPU、Table/*.DAT のどこにも見つからない。CPU ヘッダの 1000 などが CPU 機の耐久値である可能性はある【推測】。プレイヤー機の値は exe 内のテーブル、またはスクリプトから設定されていると推定する【推測】。

---

## 6. BFE→BSDX 変換器に必要なもの

| 段階 | 入力 | 出力 | 難易度 | 内容 |
|---|---|---|---|---|
| 1 画像 | tooruNNN.grp ×80 | PNG（RGBA）80 枚（必要ならアトラスに再パック） | 低 | **bfe_gr2.py でほぼ完成**。命名は `tooru_000_NNNN.png` など kou に合わせる |
| 2 スプライト | tooru.spr | tooru.spm（VER-2.00）JSON → NeXAS_DX Generator | 低〜中 | ページ = BFE フレーム（方向 0-4、5-7 は空）、chip = part、anim = 512 スロットのうち使用中の 385 個に名前を付ける。**判定スロットの対応表**と **drawAttr→drawOption** は要調査 |
| 3 基本動作 | （BFE では exe 内） | waz の基本 skill + mek の PairBlock | 中 | Kou の基本 skill（立ち/歩き/ダッシュ/ジャンプ/被弾/ダウン）を複製し、CEventSprite だけ tooru.spm のアニメに差し替える。**BFE のアニメスロット→動作名の対応表**が必須（ビューアで目視して作る） |
| 4 武装 | TOORU.WAZ 213 技 | BSDX waz の skill + mek WeaponInfo | 高 | 392B ブロックの意味が不明なので**テンプレート方式**にする（例: ｱｰﾑｼﾞｬﾌﾞ→Kou「ジャブ」の skill を複製し、phase ごとのスプライト・フレーム長・ダメージを BFE の値で置換）。Lv は 3 段から 1 つ選ぶか、BSDX の成長表（Weapon.dat）に割り当てる |
| 5 弾・エフェクト | Tama.dat の 194 技 + Bmp/Effect | Tama0x.waz に追記、または新しい waz + Effect の spm | 高 | 射撃・ﾋﾞｯﾄ系を移植するなら必要。格闘系だけなら省略できる |
| 6 AI | TOORU.CPU | mek ④ AI | 中（プレイヤー機なら低） | プレイヤー機としてだけ使うなら Kou の AI を流用でよい |
| 7 ステータス | 不明（exe） | mek ① MekBasicInfo | 低（手動で決める） | BSDX のバランスに合わせて手で設定する |
| 8 SE・ボイス | Se/、BatVoice | SeGroup/BatVoice の grp 追加 | 中 | 03 ノートで判明した grp 長の制約が絡む |

ツール側の設計: `bfe_spr.py` / `bfe_waz.py` は JSON を出力するので、NeXAS_DX の Spm/Waz JSON に変換する `bfe2bsdx_spm.py` を次に作るのが最短【提案】。Stage 1 の「外部機体インポート」パイプラインの入力側に BFE アダプタを 1 つ足す形になる。

---

## 7. 実現可能性とリスク

* **実現可能（見た目と基本操作）**: 画像と SPR は完全に読めていて、8 方向方式とピクセル寸法も BSDX と同じ。「透の機体が BSDX で歩いて、ダッシュして、Kou 流の技を出す」ところまでは高い確度で届く見込み。
* **リスク（大）**: 技の挙動を忠実に再現すること。392B ブロックの意味解析が必要で、exe が保護されているため、Stage 1 の新規機体登録の課題（03 ノート: ハードコードされた 103、grp の長さ）に加えて、**BFE 側の RE コストが大きい**。
* **リスク（中）**: BFE のアニメ 512 スロットの意味付け（手作業）、判定スロットの対応、drawAttr（加算合成など）の対応。
* **リスク（中）**: BSDX は 8bpp パレット画像を使っていない → RGBA に変換すれば済む。ただし BSDX の描画で、パレット由来の縁の色が浮く可能性がある（透過色の縁取りがあれば要処理）。
* **法的・倫理面**: ユーザーが所有するゲームを個人で改造する範囲。保護された exe のメモリダンプは解析目的に限り、配布はしない前提とする。

---

## 8. ユーザーの PC から追加でもらいたいもの（優先度順）

1. **ゲームフォルダ全体のファイル一覧**（サイズ付き）: `dir /s /a-d > bfe_list.txt`。
2. **Bmp/Meka の `*.lst`（5 個）と `*.ani`（5 個）**。lst にアニメスロット名や機体一覧が入っていれば、スロット対応表を作る手間が大きく減る。
3. **Dat フォルダの残り全部**: `Dat/Waza/*.WAZ`（他機体との比較用）、`Dat/Cpu/*`、`Dat/BatVoice/*`（**tooru 用があれば最優先**）。どれも小さい。
4. **Bmp/Effect/ 全部と Bmp/BatParts/**（弾やエフェクトの SPR/GRP。戦闘アセットなので扱ってよい）。
5. **Se/ のファイル一覧**と、TOORU の技で使う SE（ファイル名の対応がわかった後で）。
6. **Script.pac**（バトル開始コマンドから機体の初期化パラメータ＝ステータスを探すため。シナリオ本文は読まない）。Chapter.pac も一覧だけほしい。
7. **保護されていない BaldrForce.exe**:
   (a) パッケージ版（2002 年の BALDR FORCE、または BALDR FORCE EXE のディスク版）の exe があればそれが一番よい。
   (b) なければ、起動後に x32dbg + Scylla などでメモリダンプを取る（OEP の特定などは手順書を用意する）。
   これがあれば、ステータス表、WAZ 固定ブロックの各フィールド、ハードコードされた基本動作のアニメスロットを確定できる。
8. 参考資料として、ゲーム内の「データベース」画面で透の機体スペックが表示されるならスクリーンショット（テキスト部分だけでよい）。

---

## 付録: 作成物
* `tools/bfepac.py` — 旧 PAC の一覧表示と展開
* `tools/bfe_gr2.py` — GR1/2/3 → PNG、SPR の展開
* `tools/bfe_spr.py` — SPR → JSON（`work/bfe_spr/tooru.json`、`akira.json`）
* `tools/bfe_waz.py` — WAZ/Tama → JSON（`work/bfe_waz/*.json`）
* `work/bfe_extracted/` — 3 つの pac の展開結果、`work/bfe_png/` — TOORU の PNG 80 枚（`_view_*.png` は確認用）
