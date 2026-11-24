# 02 ビルドと pac — パックの作り方・検証・配置

対象: 透（TOORU）パック `Update3.pac` の作り方、検証、配置、補助ツール、よくある失敗。
パスの表記: `<PROJECT>` = このリポジトリを置いた作業フォルダ、`<GAME>` = BALDR SKY DiveX のゲームフォルダ、`<BFE>` = BALDR FORCE EXE のゲームフォルダ。
表記: 【確認済】= コードや資料の原文で確認、【未確認】= 資料に無い・確かめられなかった、旧 → 現 = 日付の新しいほうを採用。

---

## 0. 先に結論（最短版）

| やりたいこと | やること | 根拠 |
|---|---|---|
| PC で 4 パックを作り直す | `python tools/build_packs.py`（同期 → 2 回ずつビルド → sha256 照合 → `<PROJECT>\mods\phase3b_tooru\` に配置 → `SHA256SUMS.txt` 更新）。§3 | `tools/build_packs.py` |
| 決定的か確かめる | build_packs.py が 2 回ずつビルドして自動で照合する | `tools/build_packs.py`、制作記録 旧 §4、調査記録 36 §6 |
| ゲームで試す | 作者が `Update3.pac` を `<GAME>`（`BaldrSky_07.exe` と同じ場所）へ置く。作業者はゲームフォルダに書かない | 制作記録「PC 上でのコマンド実行」、制作記録 §2 |
| 元に戻す | `Update3.pac` を削除する | mods/phase3b_tooru/README.md 「入れ方」4、docs/formats/02_pac_and_loading.md §5 |
| sha256 を記録する | 制作記録 に先頭 8 桁（`…` 付き）。pac 自体は git に入れない | 制作記録 §4、制作記録 11/14〜11/16 の行 |

---

## 1. 4 つの成果物

ビルドは 1 回の実行で「原作再現版」と「改善版」の 2 つを出し、`--waz110` 付きでもう 1 回走らせると同じ 2 つの waz110 版が出る。合計 4 パック。

| パス（`mods/phase3b_tooru/` から） | 呼び名 | 中身 |
|---|---|---|
| `Update3.pac` | 3b（faithful、原作再現版） | BFE の「透」を忠実に変換した版。WazaGroup は **[110] を空き（existFlag 0）のまま [111] に透** |
| `modified/Update3.pac` | modified（改善版） | 3b のコピーに「改善版だけの調整」を当てた版。ダメージ系（最低値・技終了時など）と挙動系の調整のみが 3b と違う |
| `variantB_waz110/Update3.pac` | 3b の waz110 版 | 3b と同じ内容で、透を **WazaGroup [110] に直接**置いた版（[110] の空きエントリなし） |
| `variantB_waz110/modified/Update3.pac` | modified の waz110 版 | modified と同じ内容を [110] に置いた版 |

出典: `build_phase3b.py` 冒頭の docstring、`WAZ_SLOT = 111`（`--waz110` で 110）、`OUT = MOD + '/variantB_waz110'`、I2 節の `BOUT = OUT + '/modified'`。

### 1.1 waz110 版がなぜあるか
* 通常版は WazaGroup の [110] を「ツクヨミ（phase 3A）用の予約」として空エントリで残し、透を [111] に置く。ツクヨミとの統合パック（phase3c）が作れるようにするため（`build_phase3b.py` の `WAZ_SLOT` のコメント、調査記録 12 §1）。
* 「[110] が空のままだと起動・ロードで落ちるかもしれない」という**保険**が waz110 版（README「分かっている近似・制限」の最終項、調査記録 09 末尾の未確認リスト「落ちるなら variantB_waz110」）。落ちたら waz110 版を試す、という使い方。
* 実際に通常版で [110] が原因で落ちた記録は、読んだ資料には見当たらない【未確認】。11/16 の 制作記録 も通常版（3b / modified）を主に案内し、waz110 は「落ちる場合」の予備として書いている。

### 1.2 faithful と modified の違い
* modified は `build_phase3b.py` I2 節で、3b のファイル群を丸ごとコピーしたあと、変えたファイルだけ書き換える（`bgen` に入ったもの）。
  * ダメージ系: `tools/bfe2bsdx_balance.py`（最低値、技終了時、FC の威力など）。
  * 挙動系: `tools/bfe2bsdx_modified_behavior.py`。調整は **すべて `tools/modified_tweaks.py` に 1 件ずつ登録**し、`on` で切り替え、`params` で値を決める（制作記録 §2「11/10〜」、調査記録 39）。一覧は `python tools/modified_tweaks.py`（`--md` で Markdown）。
* 「modified が 3b と違うのはここだけ」をビルドが自動で検査する: ① spm は触ったアニメ・ページ以外 3b と同じ、② waz は最低値・技終了時のキー以外同じ（挙動を変えた技だけ除外）、③ 共通 waz はバニラのバイト列が先頭に残る、④ それ以外のファイルは 3b とバイト一致（I2 節の `assert`）。
* 3b が変わらない更新（modified だけ変えた）は 制作記録 に「3b 不変」と書かれる（例: 制作記録 11/16「3b D08A1C91 / waz110 865F18C5（不変）」）。

### 1.3 pac の中身（機体登録の全体像）
3b は ID 10（バニラの Sora2、完全未使用）を転用して透を登録する（docs/formats/03_mech_registry_and_player.md §4(b)「新 ID を作らず未使用 ID 10 を差し替える」、調査記録 09 §1）。

| ファイル | 変更 | 出典 |
|---|---|---|
| `MekaGroup.grp` | [10] Sora2 → Tooru/TOORU（`assert MG[NEW_ID] == Sora2` で確認） | build_phase3b.py F 節 |
| `Tooru.mek` | 甲の mek を土台に作成。武装 88（通常 63・マーカー 3〔うち 2 は非表示、`weaponIdentifier 2`〕・必殺 21・イニシャライザ）。ボイスなし（`mekVoiceInfo.version = -1`） | build_phase3b.py E 節、調査記録 09 §0 |
| `Tooru.waz` | 100 技（0–10 基本動作、11 区切り、12–98 移植、99 イニシャライザ） | 調査記録 09 §0 |
| `WazaGroup.grp` | 通常 [110] 空き + [111] ◆透。waz110 版は [110]。共通 waz の `param`（技数）も更新 | build_phase3b.py F 節 |
| `SpriteGroup.grp` | [135] `tooru_eft.spm`（BFE Effect.spr のうち使う分）、[136] `tooru.spm`（空きスロット 133〜136 を使う。配列長 138 は変えない） | docs/formats/01_formats_and_tools.md §0・§5.2、build_phase3b.py |
| `SeGroup.grp` | カテゴリ 37 の末尾に `BFE_*.ogg`（BFE の SE 70 種）を追加 | build_phase3b.py D 節 |
| `tooru.spm` / `tooru_eft.spm` + PNG | 機体スプライトと BFE エフェクト | 調査記録 09 §1–2、§8 |
| `SelectMekaMenuMeka.spm` + `s_tooru_1/2.png` | 選択画面のサムネ（anim 追加） | build_phase3b.py B 節 |
| `Tama02.waz` / `Tama04.waz` / `Laser.waz` | **共通 waz の末尾に追記**（バニラの先頭バイトは不変）。Tama02 = ヒットエフェクト、Tama04 = 弾、Laser = レーザー／ワイヤーの線分 | build_phase3b.py の `BULLET_FILE, EFFECT_FILE, LASER_FILE = 4, 2, 6` |
| `WeaponEquip.dat` | 行 10（= MekaGroup ID）に初期装備 14 枠（通常 12 + キャノンブレイカー + イニシャライザ） | build_phase3b.py の `LOADOUT_BFE` / `we()` |
| `SelectMekaMenu.dat` | 行 27（晴嵐のボタン）→ `[10, THUMB, -1]`、晴嵐の元の行は末尾へ | `smmd()` |
| `MekaPilot.dat` | 行 30 `[97]`（晴嵐）→ `[10]` | `mp()` |
| `Meka.dat` | 末尾に `[10, 150]`（自機の機体マスタ。コイン倍率） | `mk()` |

* 3b の pac は 181 ファイル前後（制作記録 11/06「181 files」。以降の更新で数は増減しうるので、実際の数は各ビルドの出力行 `N files, M bytes (extract-verified)` で確認）。
* **ゲームに実際に反映される範囲**: 選択画面のボタンは 70 個固定（docs/formats/03_mech_registry_and_player.md §5）。透は晴嵐のボタン枠（行 27）を借りる。選択できるのは「究極サバイバル」「バルド地獄」（docs/formats/03_mech_registry_and_player.md 冒頭の表）。
* **Phase0 のテスト名残の削除（11/06 作者指示）**: `AkisRoomItem.dat`（69 機を 1 コインで解禁）と `SelectGameMode.dat`（【MODテストTOORU】）はもう書き出さない。旧 README の「【MODテストTOORU】と出れば読まれている」は**現行では使えない**（旧: README 入れ方 3 → 現: 制作記録 11/06、build_phase3b.py 末尾コメント）。読み込まれたかは、選択画面で晴嵐の枠が透になるかで確認する。
* 統合パック `mods/phase3c_merged/`（ツクヨミ + 透）は、透を **ID 77（アイアンファイル）・ボタン行 28** に置く古い設計（調査記録 12 §1）。「統合パックは phase3.5 まで作らない」（制作記録 §1）ので、現行の ID 10 方式とは別物。混ぜない。
* `mods/phase4_slots/` は機体 ID 上限 103 を 120 に広げる**未テスト**の実験版 exe パッチ（`README_EXPERIMENTAL.txt`、調査記録 11）。パックの作り方とは無関係。

---

## 2. ビルドの前提（入力と環境）

### 2.1 入力
`build_phase3b.py` は次を読む（`<WS>` = ビルドする作業ツリーの根。`tools/bfe2bsdx_common.py` の `P` で、PC では `<PROJECT>/_ws/proj`、クラウドでは `/path/to/workspace`。§3）。

| 入力 | 場所（`<WS>` = ワークスペース根） | 備考 |
|---|---|---|
| バニラ BSDX の展開物 | `<WS>/work/extracted/{Update2,Update,Dat,Config}/` | `src()` が Update2 → Update → Dat の順に探す（= ゲームの優先順位、§5.2）。Config は dat 用 |
| バニラの NeXAS_DX JSON | `<WS>/work/nexas_rt/json/`（`VAN`） | `tools/run_roundtrip.sh` の出力 |
| BFE 側 | `work/bfe_spr/tooru.json`、`work/bfe_png/`、`work/bfe_waz/{TOORU_named,Tama_named}.json`、`work/bfe_se/*.wav`、`work/bfe_extracted/Update/EquipmentInfo.DAT`、`work/bfe_effect/`（Effect.spr + grp） | すべて**ゲーム由来のため git 対象外**（`.gitignore`: `/mods/*/files/`、work のゲーム由来 json/waz など） |
| NeXAS_DX（Java） | `<WS>/../ext/NeXAS_DX` ほか 4 リポジトリ（Karaik/NeXAS_DX、Karaik/NeXAS_SPM_VIEWER、Karaik/BALDRSKYDIVEX_DAT、morkt/GARbro、Aserain-Nodid/DX_MOD_PAC） | `restore.sh` が GitHub から clone（`tools/restore.sh`）。ビルドは `ext/NeXAS_DX` の spm を直接読む（`DXSPM`） |
| Java クラスのスナップショット | `work/tooru_port/nexas_snap`（環境変数 `BFE2BSDX_SNAP` で変更可） | 別の作業の `tools/nexas_build` 再ビルドと干渉しないための私的コピー（`tools/bfe2bsdx_common.py` 冒頭） |
| jar | `tools/libs/` の hutool・jackson・slf4j（`/opt/gradle-8.14.3/lib` があればそちら） | `bfe2bsdx_common.py` の `L` |

* ワークスペースの写し（git HEAD）には `work/` のゲーム由来データも `_ws` も入っていない。**新しい環境でゼロから再現する手順は資料に無い**【未確認】。実績があるのは (a) 制作記録 §0 のクラウド復元（`_handoff/ws_20261028` の分割アーカイブから）と、(b) すでに `_ws/proj` ができている PC。`_ws/proj` / `_ws/ext` の**初回の作り方**は 調査記録 33 末尾にも書かれていない【未確認】（restore.sh 相当を PC 側に展開したものと推測されるが資料に無い）。

### 2.2 実行環境
* Python: PC は **3.11.9**、Java **17.0.12**（制作記録 冒頭付近「Windows 環境」、制作記録「PC 上でのコマンド実行」）。クラウドは python3、JDK 17+（制作記録「Tools available」）。
* Python パッケージ: **Pillow**（サムネとシート処理に使う、`build_phase3b.py` B 節の `from PIL import Image`）。PC では `_ws/s_tmp/py/` に入れてあり、build_packs.py が `PYTHONPATH` で渡す。
* **ffmpeg**: クラウドは `libvorbis` で SE を wav → ogg にする（`-fflags +bitexact -map_metadata -1 -flags:a +bitexact`、D 節）。PC には無いので、**既存の ogg を使い回す**（§3.2 `OGG_CACHE`）。
* PC では PowerShell（リモート実行）から `python tools/build_packs.py` を実行する。Git Bash は要らない（`C:\Program Files\Git\bin\bash.exe` はあるが PATH には無い）。

---

## 3. PC（Windows）でのビルド手順（現行）

**`python tools/build_packs.py` の 1 コマンド**（2026-11-16〜。PowerShell・リモート実行 からそのまま実行できる）。
旧: 11/07 より前はクラウドでビルドして PC に転送 → 11/07〜11/15 は Git Bash で `tools/win_build/sync.sh` → `build.sh` を手で 4 回、成果物も手でコピー → 現: `build_packs.py`。

### 3.1 構成
```
<PROJECT>\                  ← git リポジトリの根（ブランチ main）。ゲーム由来のデータは持たない
  tools\build_packs.py       ← ビルドの入口
  mods\phase3b_tooru\        ← 配置先（4 つの Update3.pac と SHA256SUMS.txt）
  _ws\proj\                  ← ビルド専用の写し（git 対象外）。work/ にゲーム由来のデータ、tools/libs に jar
  _ws\ext\NeXAS_DX           ← 外部リポジトリの clone（バニラの spm を読む）
  _ws\s_tmp\py\              ← Pillow など（PYTHONPATH に入る）
  _ws\s_tmp\ogg\             ← 以前に作った BFE_*.ogg（71 個）。PC には ffmpeg が無いのでこれを使う
  _ws\build_logs\            ← ビルドのログ（build_1.log、build_1_waz110.log、build_2…）
```
`_ws\s_tmp` にはこれまでの作業の一時ファイルも溜まっている（環境変数 `S_TMP` で別の場所にできる）。

### 3.2 build_packs.py がやること
| 段 | 内容 |
|---|---|
| ロック確認 | `_ws/proj/work/tooru_port/BUILD.lock` が 30 分以内にあれば止まる（他の作業がビルド中）。古いロックは消す。自分のビルド中はロックを置き、終わったら消す |
| 同期 | `git ls-files -co --exclude-standard`（追跡中 + 未追跡で .gitignore 対象外）のファイルを `_ws/proj` に重ねる。前回同期したのに git から見えなくなったファイルは `_ws/proj` からも消す（`_ws/proj/.synced_files.txt` で管理）。同梱 jar の class 版数が Java 17 より新しければ 61 に下げる |
| ビルド | `_ws/proj` で `build_phase3b.py` と `--waz110` を **2 回ずつ**（`PYTHONUTF8=1`、`PYTHONPATH=_ws/s_tmp/py`、`OGG_CACHE=_ws/s_tmp/ogg`）。1 回 約 40 秒、全部で 3 分弱（11/16 実測） |
| 照合 | 1 回目と 2 回目で 4 パックの sha256 が一致しなければ止まる（配置しない） |
| 配置 | 置いてある pac が `SHA256SUMS.txt` の記録と違えば止まる（他の作業が置き換えた）。問題なければ 4 パックと自動生成ファイル（`調査記録 15`、`15b`、`15c`、`work/tooru_port/report.txt`、`balance_table*.md`）を `<PROJECT>` に戻し、コピー後の sha256 を確かめ、`mods/phase3b_tooru/SHA256SUMS.txt` を書き直す |
| 表示 | パックごとの sha256 先頭 8 桁と `same`（前回の記録と同じ）／`CHANGED (was XXXXXXXX)`。表示は英数字だけ（PowerShell 越しの文字化けを避ける）。制作記録 にそのまま貼れる日本語の 1 行（`3b … / waz110 …（不変）、modified … / waz110 …（2 回ビルド一致）`）は `_ws/build_logs/summary.txt`（UTF-8）に書く。止まったときは先頭に `LOCKED:`・`NONDETERMINISTIC:`・`PLACED-PAC-CHANGED:` |

オプション: `--once`（各 1 回だけ。試行用）、`--no-copy`（配置しない）、`--sync-only`、`--status`（記録と置いてある pac を比べるだけ）、`--force`（ロックや記録との不一致を承知で進める）。

`SHA256SUMS.txt` は git に入れる（pac 自体は入れない）。コミットに「どのパックができたか」が残り、次のビルドで「3b 不変」を自動で判定できる。
配置を自動にした理由: 11/16 朝のビルド（調査記録 64）は `_ws/proj` にだけあり、`<PROJECT>\mods\phase3b_tooru\modified\` には 1 つ前のパックが残っていた（制作記録 の sha256 と食い違う状態）。手でコピーする手順は抜けやすい。

### 3.3 以前の sync.sh がしていた書き換えは、ソース側に取り込んだ（11/16）
| 以前 sync.sh が `_ws` の写しにだけ当てていた置換 | 現在 |
|---|---|
| `/path/to/workspace`・`/path/to/ext` → `_ws/proj`・`_ws/ext` | `tools/bfe2bsdx_common.py` の `P`（= tools/ の 1 つ上）と `EXT`（= P の隣の ext）。環境変数 `BSDX_PROJ`・`BSDX_EXT` で差し替え可。他のツールも自分の場所から求める |
| `['python3', ` → `[sys.executable, ` | ソースが `sys.executable` |
| ffmpeg 呼び出し → ogg のコピー | 環境変数 `OGG_CACHE` があればコピー、無ければ ffmpeg（`build_phase3b.py` D 節） |
| `os.symlink(` → `shutil.copyfile(` | Windows（`os.name == 'nt'`）だけコピー |
| classpath の `:` → `os.pathsep`、Java 出力の `encoding='utf-8'` | ソースがそうなっている |

この取り込みの前後で 4 パックの sha256 は変わっていない（D08A1C91 / 865F18C5 / 70F001E7 / 6F648BFE、11/16 に確認）。
`tools/win_build/sync.sh`・`build.sh` は互換用の薄い入口として残してある（中身は `build_packs.py --sync-only` と、写しでの単発ビルド）。
古い phase のビルド（`mods/phase1_test`・`phase3a_tsukuyomi`・`phase3c_merged`）とクラウド用のシェル（`restore.sh`・`run_roundtrip.sh`・`build_nexas_dx.sh`・`porttool.sh`）は `/path/to/…` の直書きのまま（PC では動かしていない）。

### 3.4 注意
* **sha256 はクラウドの旧ビルドと比べられない**: Pillow の版が違うので PNG の圧縮バイトだけ変わる（画素・データは一致を確認、調査記録 33 末尾）。11/07 以降は PC 同士で比較する。
* 通常と `--waz110` は `work/tooru_port/check/` などを共有するので、**同時に走らせない**（build_packs.py は順に走らせる）。
* 新しい SE を使う変換を足すと `OGG_CACHE` に ogg が無く `FileNotFoundError` になる。ffmpeg のある環境で `-fflags +bitexact -map_metadata -1 -c:a libvorbis -q:a 5 -fflags +bitexact -flags:a +bitexact` で作って `_ws/s_tmp/ogg` に置く（D 節）。
* `_ws/proj`・`_ws/ext` の初回の作り方は資料に無い【未確認】。作り直すときは `_handoff/ws_20261028` と `tools/restore.sh`（§4）が手がかり。
* `work/tooru_port/nexas_snap` の class 版数（Java 17 向けに 61）は `_ws/proj` に当て済み（調査記録 33 末尾）。作り直したら同じ処理が要る。
* `tools/gui`・`tools/human`・`_ws`・`_handoff` は同期されない（.gitignore）。

---

## 5. build_phase3b.py の流れと主なオプション

### 5.1 オプション・環境変数（コードで確認済み）
| 指定 | 効果 | 出典 |
|---|---|---|
| `--waz110` | `OUT = mods/phase3b_tooru/variantB_waz110`、`WAZ_SLOT = 110`、[110] の空きエントリを作らない。調査記録 15・15b・15c の自動生成と `report.txt` は **書かない／別名**（`report_waz110.txt`、`balance_table_waz110.md`） | `VARIANT110`、I2 節、末尾の `if not VARIANT110` |
| `TOORU_DIAG=<名前>`（環境変数） | 診断用パック。`OUT = mods/phase3b_tooru/diag_<名前>`、**I2（modified）は作らない**。現在の定義は `mbu`（メガブーストアッパーの 3 ヒット診断）のみ | `DIAG`、G0 節 |
| `BFE2BSDX_SNAP`（環境変数） | Java クラスのスナップショット場所 | `bfe2bsdx_common.py` |
| `OGG_CACHE`（環境変数） | あれば SE を ffmpeg で作らず、このフォルダの `BFE_<名前>.ogg` をコピーする。PC では build_packs.py が `_ws/s_tmp/ogg` を渡す | build_phase3b.py D 節 |
| 上記以外のコマンドライン引数 | **ない**（`sys.argv` を見るのは `--waz110` だけ） | `grep sys.argv` |
| `BUILD.lock` | **コードは見ていない**。別の作業の同時ビルドを避ける運用上の約束（§6.3） | `grep BUILD.lock` で build_phase3b.py にヒットせず |

### 5.2 段階（節の見出し順）
| 段 | 内容 |
|---|---|
| A | バニラの grp/waz/mek/spm を `PortTool b2j`（Java）で JSON 化。`assert len(WG)==110 and len(SG)==138 and len(SE)==38 and len(BV)==30 and len(MG)==103`（入力が違うとここで落ちる） |
| B | BFE の SPR → `tooru.spm`（`bfe2bsdx_spm.convert`）。選択画面サムネ（`SelectMekaMenuMeka.spm` に anim 追加） |
| C | 技の変換（`Converter.convert`、63 通常 + マーカー 3 + 必殺 21 = 87 技）、基本モーション 0–10（甲の複製）、SD/BD（村正/ノイの技、`bfe2bsdx_basic`）、イニシャライザ。弾・エフェクト・ラインは `bfe2bsdx_tama.Fx` で必要な分だけ共通 waz に追記。装甲関連の値を ×2（`double_armor`）。ヒットロックの除外指定（`HITLOCK_KEEP`） |
| C2 | `tooru_eft.spm`（使う Effect.spr のアニメだけ） |
| D | SE: BFE の wav → ogg（クラウド: ffmpeg、PC: `OGG_CACHE`）→ SeGroup カテゴリ 37 に追記 |
| E | `Tooru.mek`（甲の mek を複製、基本情報・武装・熱量・AI の武装参照付け替え・MaterialBlock 再構築）。自己テストとして Rain の MaterialBlock 規則を再現 |
| F | レジストリ（WazaGroup / SpriteGroup / MekaGroup[10]）の書き換え |
| G0 | 診断用の変更（`TOORU_DIAG` のとき） |
| G1・G1b | エンジン差のパッチ（ブーストアッパー等の F0 ずらし `HITSTOPMOVE`、FIRELOCK の目印除去、`FOLLOWCUT`）。**両パック共通** |
| G | JSON → バイナリ（`j2b`）→ 再パース（`b2j`）→ 元 JSON と比較。バニラ共通 waz が先頭バイト一致で伸びているか。PNG コピー。dat 4 個（WeaponEquip / SelectMekaMenu / MekaPilot / Meka）を `bsdx_dat` で編集（往復一致も assert） |
| H | `mek_check.py`（違反 0 を assert）と `--spm --full --also-waz Tama02,Tama04,Laser`（バニラ基準外 0 を assert）。`work/tooru_port/view/` 作成（waz_summary 用） |
| I | `nexaspac.py create FILES Update3.pac` → `extract` して全ファイル一致を assert |
| I2 | modified: 3b のファイル群をコピー → `bfe2bsdx_balance.apply` + `bfe2bsdx_modified_behavior.apply` → 再パース一致 + 「3b との差は許した部分だけ」検査 → pac 化 + 展開検証 |
| 末尾 | `weapons_table.md`、`weapons.json`、**調査記録 15**（`tools/provenance.py`）、`report.txt` |

* G の前に `bfe2bsdx_balance.pop_bal` で各ヒットの「最低値」の候補を取り出し、3b 側のファイルには入れない（ROLEMIN、modified だけで使う）。

### 5.3 ビルドが自動でやる検証（失敗すると `assert` / `SystemExit`）
1. **再パース一致**: 生成した 12 ファイル（Tooru.mek/.waz、tooru.spm、tooru_eft.spm、SelectMekaMenuMeka.spm、Tama02/Tama04/Laser.waz、grp 4 個）を `j2b` → `b2j` し、元 JSON と一致（`re-parse mismatch` で停止）。出力例「12 ファイル再パース一致」（調査記録 36 §6）。
2. **共通 waz の先頭バイト一致**: バニラの Tama02/04/Laser は生成物の先頭にそのまま残る（末尾追加のみ）。
3. **`mek_check.py`**: 違反 0（`OK (no violations)`）。結果は `work/tooru_port/mek_check.txt`。
4. **`mek_check --full --spm`**: 共通 waz も含めた全体検査。バニラの Sora.mek を基準にして「基準外 = 新規違反」が 0 であること。バニラにも出る既存の指摘が 8 件ある（制作記録 / 調査記録 36 §6「8 件すべてバニラ基準内」）。結果は `mek_check_full.txt`。
5. **pac 展開検証**: 作った pac を `nexaspac.py extract` し、`FILES` の全ファイルとバイト一致（`extract-verified`）。modified も同様。
6. 規則ごとの assert（スプライト参照が範囲内、WazaSelect が存在、`kou.spm` 参照が残っていない、など。C 節）。

### 5.4 ビルドが自動生成するファイル
| ファイル | 内容 | `--waz110` | 備考 |
|---|---|---|---|
| `調査記録 15` | 武装ごとの「値の出どころ」（R/E/M/V… の分類） | 書かない | **手で触らない**（制作記録「値の出どころの記録」）。手書きの `調査記録 15` は phase の最後にだけ更新 |
| `調査記録 15b` | modified の最低値・技終了時の表（`bfe2bsdx_balance.table_md`） | 書かない（`work/tooru_port/balance_table_waz110.md` に出る） | |
| `調査記録 15c` | 改善版の調整一覧 + 「このビルドで当てた挙動の調整」ログ | 書かない | |
| `work/tooru_port/weapons_table.md` / `weapons.json` | 武装ごとの状態（変換 / 変換（推定あり） / 近似）と近似・推定の理由 | **両方が上書きする**（後に走ったほうが残る） | 調査記録 09 §9 |
| `work/tooru_port/report.txt`（waz110 は `report_waz110.txt`） | 近似・置換の全件（Report のカテゴリ別） | 別名 | |
| `work/tooru_port/mek_check.txt` / `mek_check_full.txt` | 検査結果 | **上書き** | |
| `work/tooru_port/view/` | `tools/waz_summary.py Tooru --json-dir work/tooru_port/view` 用 | 上書き | |
| `work/tooru_port/check/`、`check_modified/`（waz110 は `check_modified_waz110/`） | 生成物の読み戻し JSON（調査・差分に使う） | `check/` は共有 | `check/` は毎回消して作り直す |

* 同じ `work/tooru_port/` を使うので、**2 つのビルド（通常と `--waz110`）を同時に走らせない**。同時実行でも壊れる（`check/` を消す）。
* 調査用の読み戻しデータの典型的な場所: modified は `work/tooru_port/check_modified/Tooru.waz.json`（調査記録 54、調査記録 56、調査記録 65 が参照）。

---

## 6. 所要時間・決定性・ロック

### 6.1 所要時間
* README「作り直し方」: 約 1 分。制作記録 §4: 約 2 分（クラウド）。PC での実測は資料に無い【未確認】。通常 + waz110 の 2 回 × 2 回確認 = 4 回走らせる想定で見ておく。

### 6.2 決定的ビルド
* **2 回ビルドして `Update3.pac` の sha256 が一致する**（制作記録 §4、調査記録 36 §6「faithful は 2 回ビルドで同じ sha256」、制作記録 の「2 回ビルド一致」多数）。
* 決定性のために入れてあるもの: ogg の ffmpeg に `-fflags +bitexact -map_metadata -1 -flags:a +bitexact`（ストリーム番号が毎回乱数になるのを防ぐ。調査記録 12 §5、調査記録 09 §0）、pac の zlib level 6 固定（nexaspac.py）。PC では ogg を再生成せず既存を使うので問題が起きない。
* 確認は `tools/build_packs.py` が自動で行う（2 回ずつビルドして 4 パックを照合、不一致なら配置しない）。
* 「変えていないのに sha が変わる」ときは、ツールや入力が変わっている。前のビルドと比べるため、**前の `check_modified` / `check` の JSON を退避**しておくと差分が取れる（`work/strip_test_leftovers_20261106.py` のように、作業前の pac を `work/pre_*/` に取っておく例もある、制作記録 11/06）。
* 変更を入れる前後で「off にすると前の sha を再現する」ことを確かめる運用がある（制作記録 11/15「off で前版 2442F47B を再現」）。

### 6.3 BUILD.lock（別の作業同時作業の約束）
* `work/tooru_port/BUILD.lock` を作ってからビルドし、終わったら消す。ロックがあれば待つ。**30 分以上残っていたら消してよい**（`work/tooru_port/制作記録`、`制作記録`）。
* `build_phase3b.py` 自体はロックを見ない。`tools/build_packs.py` が見る（30 分以内のロックがあれば止まり、自分のビルド中はロックを置く）。互換用の `tools/win_build/build.sh` は先頭で `rm -f` するので、他の作業がビルド中でないことを確かめてから使う（11/06 は build_phase3b.py・制作記録・pac が別の作業で更新されていた、制作記録 旧 §2）。
* 「作業前 git <hash>」を notes の冒頭に書く運用が 11/10 以降ある（調査記録 40、43、47、48、49）。ビルド前に `git log -1` で控える。

---

## 7. pac の構造と読み込み

### 7.1 NeXAS の pac 形式（`tools/nexaspac.py`、docs/formats/02_pac_and_loading.md §1–2）
| 位置 | 内容 |
|---|---|
| 0x00 | `"PAC"`（3 バイト）、0x03 は未使用（ゴミ値） |
| 0x04 | u32 エントリ数 |
| 0x08 | u32 pack type。**BSDX の全 pac が 4** |
| 0x0C | 各エントリのデータを隙間なく連結 |
| 末尾 | インデックス（エントリ × 0x4C バイト: name[0x40] cp932、offset、unpacked_size、packed_size）を **Huffman 符号化 → 全バイトをビット反転（NOT）**したもの。最後の u32 が符号化インデックスのサイズ |

* エントリ圧縮の種別（exe 0x7938e0）: 0 無圧縮、1 LZSS、2 Huffman、3 zlib、4/5 無圧縮扱い。**zstd（6/7）はこの exe には無い**（NexasPack.exe のメニューの 7 = zstd は後期エンジン向け）。
* **type 4 では「拡張子」で圧縮が決まる（重要）**: `ogg / wav / png / fnt / mpg / mpeg / avi` は無圧縮、それ以外は **zlib（level 6）**。自作 pac では zlib 後のほうが大きくなっても、非 ogg/png は必ず zlib にする（GARbro の `packed != unpacked` 判定とは違う）。`nexaspac.py` の `TYPE4_STORED_EXT` がこの規則。
* ファイル名は cp932 で 63 バイト以内、フォルダなし（ファイル名だけ）。CRC・暗号化（インデックスの NOT 以外）・改竄チェックは無い（docs/formats/02_pac_and_loading.md §4.4）。
* 使い方:
  ```
  python tools/nexaspac.py list    X.pac
  python tools/nexaspac.py extract X.pac outdir         # outdir.order.txt に元の順序
  python tools/nexaspac.py create  indir Y.pac [--type 4] [--level 6] [--order list.txt]
  python tools/nexaspac.py roundtrip X.pac workdir
  ```
  ラウンドトリップ検証は 6 pac で内容不一致 0（ヘッダ + データ部はオリジナルとバイト一致。違うのはインデックスの Huffman 木のタイブレークによる末尾数百バイトのみ。docs/formats/02_pac_and_loading.md §2）。

### 7.2 Update3.pac を置くだけで反映される仕組み（docs/formats/02_pac_and_loading.md §4–5）
* 読み込み: `BaldrSky.exe` は起動時に、設定（System.dat）の 8 つの pac 名スロット（`MascotVoice, Update, Update2, Update3, Update4, Update5, Update6, Update7`）を逆順にマウントする。**存在しなくてもエラーにならず黙って飛ばされる**。全 pac が 1 つの名前空間（キーは「小文字化したファイル名」だけ。pac 名・フォルダは無関係）を共有し、**先にマウントした pac が勝つ**（同じキーを上書きしない）。
* **優先度（高い順）**: `Update7 > Update6 > Update5 > Update4 > Update3 > Update2 > Update > MascotVoice > Voice > Stand > Face > Thumbnail > System > Script > Bgm > Visual > Movie > Se > Config > PlugIn01..08 > Bmp > Dat`（docs/formats/02_pac_and_loading.md §4.2）。
* → `Update3.pac` を `<GAME>` に置けば、同名のファイルが Update2 / Update / Dat / Config 内のものより優先される。exe・System.dat・既存の pac は変更しない。**exe や既存 pac を触らないのでオートアップデートに上書きされない**。スロットとの対応（MascotVoice = slot0 …）は推測だが、優先順位の結論は変わらない（docs/formats/02_pac_and_loading.md §7-1）。実機でも 3b が動いている（制作記録）ので、この方式は実証済み。
* ルーズファイル（pac 外のファイル）は **Movie フォルダを除いて読まれない**（docs/formats/02_pac_and_loading.md §4.3）。ゲームフォルダに直接 mek や waz を置いても反映されない。
* 複数 MOD を重ねるなら Update4〜7 も使える（番号が大きいほど優先）。ただし 3b は ID 10・SpriteGroup・WazaGroup 等を使うのでツクヨミ版（phase3a）と**同時には入れない**（README 冒頭）。
* 同じ Update3.pac を他の MOD も使うことがある。既存の `Update3.pac` が `<GAME>` にあれば、**別の場所へ退避してから置く**（README「入れ方」1）。

### 7.3 原状復帰
* `Update3.pac` を `<GAME>` から削除すれば元に戻る。元のファイルは一切書き換えていない。セーブデータの形式も変わらない（phase3c README）。
* 念のためのお願い: **戻す前に、サバイバル／地獄で選んでいる機体を普通の機体に戻してからセーブ**しておく（phase3c README の注意。透を選んだままバニラに戻すと選択済み ID が 10 のまま残るため、という趣旨。3b README には書かれていない）。
* 設置・削除は 作者が行う。作業者はゲームフォルダに書かない（§8）。

### 7.4 パックに入れるファイルの種類（ビルドが `FILES` に出すもの）
mek / waz / spm / grp / dat（バイナリ。NeXAS_DX の `PortTool j2b` と `bsdx_dat.py`）、png（スプライトシート。Pillow 経由）、ogg（SE。無圧縮で格納）。ビルドが作らないもの（SelectGameMode.dat など）は入れない（11/06 から）。ファイル名は大文字小文字を無視して引かれる（§7.2）ので、`tooru.spm` と `Tooru.mek` のように混在していてよい。

---

## 9. 補助ツール一覧

| ツール | 用途 | 使い方・出典 |
|---|---|---|
| `tools/nexaspac.py` | pac の list / extract / create / roundtrip（§7.1） | ビルド I 節が内部で使用 |
| `tools/pac_extract.py` | 巨大 pac（Bmp.pac 2.1GB など）から**名前のパターンに合うファイルだけ**を取り出す（読み取りのみ、末尾のインデックスだけ読む） | `python tools\pac_extract.py <pac> <出力> "tsukuyomi*" …`（先頭 docstring） |
| `tools/pac_list_all.py` | フォルダ内の全 `.pac` のファイル一覧を txt に出す（列: offset、展開後サイズ、格納サイズ、ファイル名）。数 GB でも一瞬 | `python tools\pac_list_all.py <GAME> <PROJECT>\pac_lists\BALDRSKY_DIVEX`。出力が `pac_lists/BALDRSKY_DIVEX/*.list.txt`、`pac_lists/BALDRHEARTEXE/` |
| `tools/win/pac_index_dump.ps1` | 巨大 pac から**インデックス部分だけ**を小さなファイルに切り出して 作者に送ってもらう用（PowerShell、読み取りのみ） | `powershell -ExecutionPolicy Bypass -File pac_index_dump.ps1 -GameDir "<GAME>" -OutDir "<PROJECT>\pac_index\…"`（先頭コメント） |
| `tools/mek_check.py` | mek（+ waz）が登録（grp・Term・SE・スプライト）の範囲内かの検査。W1/A1/V1/M1〜M4/R1〜R9。`--json-dir`（mod → 元の順）、`--spm`（R9: spm のアニメ・パターンの存在）、`--full`（違反を全部出す）、`--also-waz A,B`（共通 waz も全検査） | ビルド H 節。単独: `python tools/mek_check.py <mek.json> --json-dir <mod JSON> <vanilla JSON>`（先頭 docstring） |
| `tools/bsdx_dat.py` | `.dat`（表）のバイト一致の読み書き。`dump` / `build` / `rt`（往復テスト） | ビルド G 節が `read`/`write` を使用。先頭 docstring |
| `tools/waz_summary.py` | 技（waz）を人が読める表にする。`Tooru --skills`、`--skill N`（ターン別タイムライン）、共通 waz（`Tama04` 等）も可、`--csv` | `python tools/waz_summary.py Tooru --json-dir work/tooru_port/view`（`view/` はビルドが作る） |
| `tools/modified_tweaks.py` | 改善版だけの調整の一覧・切り替え（§1.2） | `python tools/modified_tweaks.py [--md]` |
| `tools/provenance.py` | 値の出どころの分類（`KIND_CAT`）と 調査記録 15 表の書き出し | ビルド末尾 |
| `tools/weapon_table.py` | 武装一覧（威力・最低・補正・属性・早期廃熱・EX キャンセル）を、置いてある pac から Markdown で出す（2026-11-16、旧 tooru_weapon_table.py） | `python tools/weapon_table.py -o _ws/tables`（既定: 透の改善版と原作再現版。`--variant`・`--waz110`・`--mech`・`--pac`）。05 §2.6 |
| `tools/attack_count_check.py` | 変換した技・弾ごとに、BFE 原作と DiveX 出力の攻撃イベント数を比べて差を出す（調査記録 25） | 先頭 docstring |
| `tools/bsdx_tables.py` / `bsdx_mekinfo.py` / `bsdx_mech_xref.py` / `bsdx_bindis.py` / `bsdx_native_case.py` | dat・grp を TSV 化、mek の基本情報と武装、MekaGroup ID × 各表のクロスリファレンス、`.bin` スクリプトの逆アセンブラ、ネイティブ関数 ID → exe ハンドラ | docs/formats/03_mech_registry_and_player.md 冒頭の一覧 |
| `tools/mod_origin.py` / `mod_registry_diff.py` / `waz_struct_diff.py` / `waz_refs.py` / `port_remap_check.py` / `bhe_deps.py` | 他人の MOD や BHE→BSDX 移植の調査用（出所の分類、registry の差分、waz の構造差、参照一覧、依存の閉包）。透の通常ビルドでは使わない | 各ファイル先頭の docstring |
| `tools/port/{bhe2bsdx,material_images,spm_append}.py` | ツクヨミ（BHE）移植用（spm 末尾追記など） | 調査記録 08、調査記録 12 §5 |
| `tools/build_nexas_dx.sh` | **Linux で** NeXAS_DX（非 GUI）を lombok・Maven 無しでビルド: delombok → javac。出力 `tools/nexas_build`。**PC のビルドでは使わない**（`work/tooru_port/nexas_snap` を使う） | 先頭コメント、docs/formats/01_formats_and_tools.md §1.1・付録 C |
| `tools/run_roundtrip.sh` | 全形式の parse → JSON → generate → バイト比較。出力 `work/nexas_rt/json`（= `VAN`、バニラ JSON のもと） | docs/formats/01_formats_and_tools.md §1.2 |
| `tools/porttool.sh` + `tools/harness/PortTool.java` | NeXAS_DX の変換（`b2j` バイナリ→JSON、`j2b` JSON→バイナリ）を再パース検査つきで実行する CLI。`bfe2bsdx_common.porttool()` が呼ぶ | `build_phase3b.py` の `porttool(*jobs)` |
| `tools/harness/*.java` | `RoundTrip`（往復テスト。JUnit の代替）、`Direct`（JSON を介さない parse→generate）、`BheRoundTrip`（BHE 全件）、`CloneMech`（機体複製の試作）、`RunTsukuyomiPipeline` / `JsonTransWaz`（BHE → BSDX の waz 変換試作）、`DiagPipeline` / `DiagWaz`（診断） | docs/formats/01_formats_and_tools.md 付録 C |
| `tools/restore.sh` | クラウドの復元（§4） | 制作記録 §0 |
| `tools/win_build/{sync,build}.sh` | PC ビルド（§3） | 調査記録 33 末尾 |

---

## 10. よくある失敗と対処

| 症状 | 原因 | 対処 | 出典 |
|---|---|---|---|
| ビルドが `UnicodeEncodeError` / 文字化けで落ちる、Java の出力が読めない | Windows の既定コードページ（cp932） | `PYTHONUTF8=1` を付ける（build_packs.py は付けている。`build_phase3b.py` を直接叩くときは自分で付ける）。Java の出力は `bfe2bsdx_common.porttool` が UTF-8 で読む。クラウドの Java は `LC_ALL=C.UTF-8`（非 ASCII ファイル名で `InvalidPathException`） | build.sh、sync.sh、docs/formats/01_formats_and_tools.md §1.1 |
| `ffmpeg` が見つからない | PC に ffmpeg が無い | `OGG_CACHE`（現行 pac から展開した `BFE_*.ogg`）を使う。**新しい SE を追加したとき**（`semap.items` が増えたとき）はキャッシュに無く `FileNotFoundError` になる。ogg を別途作って `OGG_CACHE` に置く（ffmpeg のあるクラウドで作るか、PC に ffmpeg を入れる）。ogg の作り方は `-fflags +bitexact -map_metadata -1 -c:a libvorbis -q:a 5`（D 節） | sync.sh、build_phase3b.py D 節 |
| `UnsupportedClassVersionError` / Java が jar を読めない | jar・nexas_snap が新しい JDK でコンパイルされている（PC は Java 17 = class 61） | class バージョン（major）を 61 に下げる（hutool は sync.sh が毎回、nexas_snap は `_ws` に当ててある） | 調査記録 33 末尾、sync.sh |
| `assert len(WG) == 110 …` で A 節で落ちる | バニラ入力（`work/nexas_rt/json`、`work/extracted`）が違う・古い・不完全 | `work/nexas_rt/json` を `run_roundtrip.sh` で作り直す。展開物が Update2 > Update > Dat の最終版か確認 | build_phase3b.py A 節、docs/formats/02_pac_and_loading.md §3 |
| `mek_check failed` / `re-parse mismatch` / `not only 最低値/技終了時` | 変換規則を変えて構造を壊した、または modified の調整で I2 の許容外を変えた | `work/tooru_port/mek_check.txt`・`mek_check_full.txt`、`check/`・`check_modified/` の JSON を読み戻して比較。`--full` の「基準外」は前回からの差（`not in vanilla baseline` 節） | build_phase3b.py H・I2 節 |
| ビルドが別の作業の途中の変更を拾う | 同じ作業ツリーで別の作業が編集・ビルド | `BUILD.lock` を作ってからビルド（§6.3）。別の作業の変更は `制作記録` の末尾 1 行で把握 | 制作記録 |
| `BUILD.lock` が残ってビルドが始まらない（または `build.sh` が無断で消す） | ロックは運用ルールで、コードは見ない | 残ったロックは **30 分以上経っていれば消してよい**。`build.sh` は先頭で `rm -f` するので、別の作業が走らせていないか確認してから叩く | 制作記録、build.sh |
| `restore.sh` が成功したように見えるが古い pac | rev1 は ext 無しでビルド失敗しても古い sha を表示した | rev2 を使う（失敗時は `BUILD FAILED` で終了、`pac was not rewritten` も検出） | 制作記録 10/28、tools/restore.sh |
| クラウドと PC で sha が合わない | Pillow の版違いで PNG の圧縮だけ違う | PC 同士・クラウド同士で比べる。11/07 以降は PC を正とする | 調査記録 33 末尾 |
| SE の ogg が毎回違う（sha が揺れる） | ffmpeg が ogg のストリーム番号を乱数にする | `-fflags +bitexact -map_metadata -1 -flags:a +bitexact` を付ける（入っている） | 調査記録 12 §5 |
| PC のファイルを上書きして別の作業の変更を消した | 別の作業が同じファイル（制作記録、build_phase3b.py、制作記録、pac）を更新していた（11/06） | 上書き前に PC 側を取り込み、前回保存時のハッシュと一致するか確認（§8） | 制作記録 §2 |
| 同名ファイルを `<GAME>` に置いても反映されない | pac 外のルーズファイルは読まれない（Movie 以外） | `Update3.pac` にまとめる（§7.2） | docs/formats/02_pac_and_loading.md §4.3 |
| pac を作ったが、ゲームで読めない | type 4 の拡張子規則（png/ogg 以外は zlib）を間違えた、ファイル名が cp932 で 63 バイト超 | `nexaspac.py create` を使う（規則を実装済み）。`extract` で戻して確認 | docs/formats/02_pac_and_loading.md §1 |
| 起動・ロードで落ちる | `[110]` 空きエントリが原因かもしれない（未確認）／他の MOD の Update3.pac との同居／ツクヨミ版との併用 | `variantB_waz110/Update3.pac` を試す。他の `Update3.pac` を退避 | README「分かっている近似・制限」 |
| 新しいコンテナで便利スクリプト（dumpsk.py など）が消えている | クラウドの `/tmp` にあった使い捨て | 必要なら作り直す（`waz.json` の skillList → phasesInfo → skillUnitCollection を unitQuantity ごとに表示するだけ）。恒久版は `tools/waz_summary.py` | 制作記録 §3 |

---
