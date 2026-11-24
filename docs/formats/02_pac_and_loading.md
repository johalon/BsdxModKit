# 02 NeXAS .pac 形式と BaldrSky.exe のリソース読み込み

対象: BALDR SKY DiveX（GIGA, NeXAS）。調査対象はステージング済みの BaldrSky.exe、Config/Dat/Script/Update/Update2/Thumbnail.pac。
ツール: `/path/to/workspace/tools/nexaspac.py`（list / extract / create / roundtrip）
展開物: `/path/to/workspace/work/extracted/<Pac>/`。各 pac の元の並び順とヘッダは `<Pac>.order.txt`、一覧は `<Pac>.list.txt`。
※画像ファイル（Thumbnail の bmp、Update の png）は中身を開いていない。名前・サイズ・バイト比較だけを扱った（コンテンツポリシーに従う）。

---

## 1. PAC フォーマット（「新形式」。BSDX の pac はすべてこれ）

| オフセット | 型 | 内容 |
|---|---|---|
| 0x00 | char[3] | `"PAC"`。exe は3バイトしか見ない（0x7942f1） |
| 0x03 | u8 | 未使用。実ファイルでは 00 / 2E / 62 とバラバラ（ゴミ値） |
| 0x04 | u32 | エントリ数 |
| 0x08 | u32 | pack type。**BSDX の全 pac が 4** |
| 0x0C | … | 各エントリのデータを隙間なく連結 |
| EOF-4-N | N bytes | インデックス（Huffman 符号化 → 全バイトをビット反転 NOT） |
| EOF-4 | u32 | N = 符号化インデックスのサイズ |

インデックスをデコードすると `count * 0x4C` バイトになる。1エントリの構造:
```
char name[0x40];   // cp932、NUL 埋め。ディレクトリは無し（ファイル名のみ）
u32  offset;       // ファイル先頭からの絶対位置
u32  unpacked_size;
u32  packed_size;
```
- Huffman: MSB ファーストのビット列。木は前順で、1 = 内部ノード（左→右）、0 = 8bit の葉。ノード番号は 256 から振る（GARbro の HuffmanDecompressor と同じ）。exe 側ではインデックスをビット反転してから `[CPack+0x2c]` のデコーダ（0x75a800）に渡している。
- エントリ単位の圧縮方式（exe 0x7938e0 のジャンプテーブル 0x793ce4）: 0 = 無圧縮、1 = LZSS（`[+0x28]`, 0x75a9b0）、2 = Huffman（`[+0x2c]`）、3 = zlib（0x75b9c0）、4/5 = 無圧縮扱い。**zstd（6/7）はこの exe には無い。** NexasPack.exe のメニューにある 7=zstd は後期エンジン向け。
- **type 4 のエントリ判定は「拡張子」で決まる（重要）。** マウント処理（0x794150, 0x7944d2〜）でファイル名を小文字化し、拡張子が `ogg / wav / png / fnt / mpg / mpeg / avi`（文字列は VA 0x819B94〜）なら無圧縮、それ以外は zlib として扱う。GARbro の `packed != unpacked` で判定する方式は、オリジナルの pac では結果が一致するが、**自作 pac では zlib 後のほうが大きくなっても非 ogg/png は必ず zlib にしなければならない。** nexaspac.py はこの exe 側の規則に合わせて実装した。
- オリジナルの zlib は level 6（`78 9C`）。全エントリが `zlib.compress(data, 6)` とバイト一致した。
- 並び順は pac ごとにまちまち（Config/Dat はソート済み、Script/Update/Thumbnail は非ソート）。ゲームはハッシュマップで引くので、順序は関係ない。
- 暗号化はインデックスの NOT だけ。データ部の暗号化や CRC は無い。zlib 自身の adler32 チェックはある。

## 2. ツール nexaspac.py

```
python3 tools/nexaspac.py list    X.pac
python3 tools/nexaspac.py extract X.pac outdir          # outdir.order.txt に元の順序を保存
python3 tools/nexaspac.py create  indir Y.pac [--type 4] [--level 6] [--order list.txt]
python3 tools/nexaspac.py roundtrip X.pac workdir
```
- 書き出しは type 4（オリジナルと同じ）で、上記の拡張子規則と zlib level 6 を使う。ファイル名は cp932 で 63 バイト以内。
- **ラウンドトリップの結果**（extract → repack → extract → 比較）: 6 pac すべてで内容の不一致 0。
  さらに **ヘッダ + データ部はオリジナルとバイト完全一致**、デコード後のインデックスも完全一致、ファイルサイズも一致。違うのは Huffman 木の同頻度時のタイブレークで決まる末尾の符号化インデックス数百バイトだけ（意味は同じ）。
- 追加テスト: 任意のフォルダから新規 pac（2ファイル）を create し、再展開して一致を確認。

## 3. 各 pac の中身

| pac | 件数 | 種別 | 備考 |
|---|---|---|---|
| Config.pac | 67 | .dat ×67 | 各種テーブル（Meka.dat, MekaPilot.dat, SelectMekaMenu.dat, TournamentMekaData.dat, Survival*.dat, Weapon*.dat, PlugIn*.dat, System.dat, BQ*.dat など） |
| Dat.pac | 221 | .mek ×103, .waz ×110, .grp ×8 | 機体（mek）、武装（waz）、グループ定義（MekaGroup / WazaGroup / MapGroup / SeGroup / SpriteGroup / BatVoice / Term / ProgramMaterial.grp） |
| Script.pac | 147 | .bin ×147 | NeXAS スクリプト（`__GLOBAL.bin`、本編のおまけシナリオ、Hell*.bin の地獄モードステージなど） |
| Update.pac | 411 | .bin 107, .ogg 148, .mek 95, .waz 26, .dat 15, .spm 11, .png 5, .map 3, .grp 1 | v1.07 のパッチ。ogg と png は無圧縮 |
| Update2.pac | 1 | system.dat | Update 版 System.dat から1バイト（offset 2422: 01→00）だけ変えたもの |
| Thumbnail.pac | 590 | .bmp ×590 | サムネイル画像（中身は見ていない） |

Update.pac の内訳（大文字小文字を無視した名前比較）:
- 他の pac と同名で **内容が違うもの**: Dat 92 件（mek/waz）、Script 87 件、Config 14 件、Config+Update2 1 件（System.dat）
- 同名で内容も同じもの: Dat 29 件（mek）
- Update にしか無いもの: 188 件（ogg 148、新 Hell ステージ .bin、TitleBar*.spm、BQ*.spm、sora.spm、NewArena_S04-06.map、png、**zako003a.mek**）
  - `zako003a.mek` は Dat/MekaGroup.grp に登録が無い（グループは Zako003b/c だけ）。未使用データか、スクリプトから名前で直接参照されている可能性がある（推測）。

### NeXAS_DX/src/main/resources/game/bsdx との対応（MD5 で比較）
| dir | 件数 | 出所 |
|---|---|---|
| bin | 167 | Script 60 + **Update 107** |
| dat | 67 | Config 52 + **Update 14** + **Update2 1**（System.dat） |
| grp | 8 | Dat 7 + Update 1（MapGroup.grp） |
| mek | 105 | Update 66 + Dat&Update 同一 29 + Dat 9 + 不明 1（Akao.mek） |
| waz | 112 | Dat 84 + Update 26 + 不明 2（Akao.waz, Moribito.waz） |
| spm | 1989 | Update 11 + 残り 1978 はステージングした pac に無い（System.pac 由来と推測） |

→ NeXAS_DX の bsdx データは **最終的に有効なファイル（Update2 > Update > 元 pac）** になっている。どのファイルも、一番優先度の高い pac の版と一致した。
Akao.mek / Akao.waz / Moribito.waz は今回の pac にも MekaGroup.grp / WazaGroup.grp にも無い。System.pac など未ステージングの pac にあるか、別作品から混入したものと推測。

## 4. BaldrSky.exe の読み込み処理

PE: i386、ImageBase 0x400000。CPack 関連のクラスは 0x7933e0〜0x795xxx（RTTI `.?AVCPack@@`）。

### 4.1 ファイル検索（0x7935a0 / 0x793490）
- 要求されたファイル名を **小文字化**（0x7648b0。SJIS の先行バイトは飛ばす）し、boost 系の unordered_map（hash + 0x9e3779b9）で引く。**ディスクを先に探す処理は無い。** マップに無ければ失敗。
- マップのキーは「ファイル名だけ」。pac 名もフォルダも含まない。つまり全 pac が1つの名前空間を共有する。
- 挿入（0x40a8e0）は、同じキーが既にあれば **上書きしない**（insert 方式）。**→ 先にマウントした pac が勝つ。**
- エントリには「ルーズファイル」フラグ（+0x88）とフルパスを持つ型もある（0x793740 が FindFirstFile + GetFullPathName で登録）。ただし後述のとおり、これを使うのは Movie フォルダだけ。

### 4.2 マウント順（グローバル: 0x71b070、別系統: 0x742490, 0x451c60）
1. 最初に **Config.pac だけ** をマウントし（0x7424f0）、`System.dat` を読んでグローバル設定（0xbf1300 の構造体）に入れる（0x415430）。
2. 設定構造体 +0x458（VA 0xbf1758）にある **8つの pac 名スロット** を、**スロット7 → スロット0 の順**（0xbf181c から 0x1c ずつ減らす）でマウントし、Config.pac もマウントし直してから System.dat を **もう一度読む**。
   System.dat の並び（Config/Update/Update2 で共通）: `MascotVoice, Update, Update2, Update3, Update4, Update5, Update6, Update7`（NUL 区切りの連続文字列、offset 2785〜）
   → スロットとの対応（推測。並び順と動作が整合する）: slot0=MascotVoice, slot1=Update, …, slot7=Update7
3. メインの読み込みループ（0x71b880）のテーブル（文字列 VA 0x818be0〜）。順番がそのまま優先順位になる:
   `[Update7, Update6, Update5, Update4, Update3, Update2, Update, MascotVoice]` → `Voice, Stand, Face, Thumbnail, System, Script, Bgm, Visual, Movie, Se, Config, PlugIn01..08, Bmp, Dat`
   それぞれ `name + ".pac"` をカレントディレクトリ（起動時に SetCurrentDirectory で exe のフォルダにしている）から開く。
   - 各エントリのフラグ A（ルーズフォルダ代替）: **Movie だけ 1**。pac が無ければ `Movie\*.*` を再帰的に列挙して登録する（0x793d00）。
   - フラグ B（必須）: Voice, Stand, System, Script, Bgm, Visual, Se, Config, Bmp, Dat が 1。無ければ DVD ドライブ（ボリュームラベル `BALDRSKYDIVEX`、0x71af60）を探し、「ディスクを入れて」ダイアログを出す。
   - Update*/MascotVoice/Face/Thumbnail/PlugIn01-08/Movie は任意。**存在しなくてもエラーにならず、黙って飛ばされる**（現状でも Update3〜7 は存在しない）。

**優先度（高い順）: Update7 > Update6 > Update5 > Update4 > Update3 > Update2 > Update > MascotVoice > Voice > Stand > Face > Thumbnail > System > Script > Bgm > Visual > Movie > Se > Config > PlugIn01..08 > Bmp > Dat**
（Update2 の system.dat が Update/Config の System.dat に勝つこと、NeXAS_DX のデータが Update 版になっていることと矛盾しない。）

### 4.3 ルーズファイル
- 一般のファイルについて、ゲームフォルダやサブフォルダのルーズファイルを優先して読む仕組みは **無い**。FindFirstFileA を使っているのは Movie フォルダの代替（0x793d00）と単一ファイル登録（0x793740）、および Susie プラグイン `%s\*.spi` の列挙だけ。GetFileAttributesA は登録済みルーズファイルの存在確認と Save 系で使っている。
- `..\Master\` と `Dat\Meka\`、`Script\Battle\*.h` といった文字列は開発用エディタの SAVE 処理のもの（"SAVE ERROR : CMekaGroup" など）。読み込みには使われていない（推測。高確度）。

### 4.4 改竄チェック
- pac に CRC、ハッシュ、サイズ表などの照合は **無い**。ヘッダの "PAC" とインデックスがデコードできるかだけを見ている。Filechk 系の文字列も無い。zlib 内部の adler32 だけは有効（"incorrect data check"）。
- `AutoUpdate.exe -c / -n` を起動するオートアップデート機能がある（System.dat に旧 URL）。サーバーはもう無いが、StartUpTool で無効にしておくのが安全。

## 5. 推奨する注入方法

**新しく `Update3.pac` を作り、ゲームフォルダに置く**（確度: 高。実機テストは未実施）
- 理由: System.dat が既に Update3〜7 を宣言している。Update3 は Update/Update2 より先にマウントされ、優先される。exe・System.dat・既存 pac を **一切変更しなくてよい**。消せば元に戻る。AutoUpdate が Update/Update2 を上書きしても影響を受けない。
- 中身: 置き換えたいファイル、または新しいファイルを **同じファイル名（大文字小文字は無視）で** 入れる。type 4、非 ogg/png 等は zlib。`nexaspac.py create <dir> Update3.pac` で作れる。
- 複数の MOD を重ねるなら Update4〜7 も使える（番号が大きいほど優先）。
- 代替案: Update.pac を作り直す。元の 411 件 + 変更分を repack すればヘッダ・データ部はオリジナルと同一形式になる。ただし AutoUpdate で上書きされる恐れがあり、元に戻すのも面倒なので次善策。
- ルーズファイルは使えない（Movie を除く）。

### 新しい機体を追加する場合に Update3.pac に入れるもの（見込み）
- `MekaGroup.grp`（Dat.pac にしか無い。形式: u32 count(=0x67=103) + {u32 1, name\0, ENUM\0}×n。新しい機体名を追加。**既存の ID がずれないよう末尾に追加すべき**）
- `<New>.mek`、`<New>.waz`（と WazaGroup.grp）、必要な `.spm`（大半は System.pac にある＝未ステージング）
- 選択や出現の表: Config 系の `Meka.dat`, `MekaPilot.dat`, `SelectMekaMenu.dat`, `TournamentMekaData.dat`, `SurvivalMeka*.dat`（最新版は Update 側を優先して使うこと。Update にある dat は Update 版が正）

## 6. exe 内の機体関連の手がかり
- 機体ファイル名は exe に **ハードコードされていない**。`Dat\Meka\` + 名前 + `.mek` / `.waz`。名前のリストは MekaGroup.grp から読み、enum の接頭辞は `MEKA_`。`m_lpMekaLoader`、"Meka: Load & WeaponLoad"。
- ハードコードされている例外: `RandomMapUnitKou.spm`, `BQUnit_%s%02d.ogg`（BQ = バルドクエスト）。
- 機体 ID 関連のエラー文字列: "LockMeka：一致するメカＩＤ(%d)がありません", "AlgAngleMeka：登録されていないメカＩＤ(%d)です", "メカ(%s)には存在しないアルゴリズム番号(%d)です"。ID は MekaGroup のインデックスと推測。
- 選択画面関係: SelectMekaMenu.dat / SelectMekaMenu.spm / SelectMekaMenuMeka.spm / MekaPilot.dat / MekaPilot.spm / TournamentMekaData.dat / SurvivalMekaMain・Zako・Rare.dat。リプレイ表示 "[使用メカ : %s]"。
- 機体図鑑系: "機体名", "メカ名", "メカのルビ", "メカ解説", "メカグループ番号"（エディタの項目名）。

## 7. 未解決の点
1. スロットと System.dat 文字列の対応（MascotVoice=slot0）は、デシリアライザ 0x41a7c0 を最後まで追えていないので推測。優先順位の結論（Update3 > Update2 > Update）は、マウントループが逆順であることと、Update 系の名前が連番であることから、どちらにしても成り立つ。
2. 実機での確認: 最小テストとして、Update3.pac に改変した `Meka.dat`（または表示文字列の dat）を1つだけ入れて反映されるかを見たい。
3. spm の大半と Akao/Moribito は System.pac などにある可能性がある。新機体のスプライトを作るには System.pac の一覧が必要（ユーザーに `nexaspac.py list System.pac` の実行を頼むのが軽い）。
4. 符号化インデックスをオリジナルとバイト完全一致させるには Huffman のタイブレーク規則が必要だが、ゲーム動作には関係ないので未対応。
