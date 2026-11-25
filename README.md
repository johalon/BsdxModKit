# BsdxModKit

NeXAS エンジンのゲーム（以下「対象ゲーム」）の MOD 制作のための、データ形式の資料・調査ツール・移植パイプラインです。
別のゲーム（以下「移植元のゲーム」）の機体「透」を対象ゲームの自機として移植した MOD の制作過程で作ったものを、他の開発者向けに切り出しました。

**非公式のファンメイドです。** ゲームの画像・音声・データ・実行ファイルは一切含みません。使うには、ゲームを自分で持っている必要があります。

## 中身

| フォルダ | 内容 |
|---|---|
| `docs/formats/` | pac・waz・mek・spm などのデータ形式、pac の読み込み順、機体の登録の仕組み |
| `docs/engine/` | 対象ゲームのエンジン仕様の早見（スロット番号の意味、計算式、exe 上の場所） |
| `docs/game_spec/` | ゲーム仕様（コンボ・キャンセルの規則、waz の項目の体感上の意味） |
| `docs/bfe/` | 移植元のゲームのデータ形式の調査 |
| `docs/porting/` | 別ゲームの機体を対象ゲームに移植するやり方（変換器の構造、変換規則のカタログ、ビルド） |
| `tools/` | Python のツール一式（下の表） |
| `mods/phase3b_tooru/` | 透パックのビルドスクリプト（`build_phase3b.py`）と機体の設定 |
| `mods/phase3a_tsukuyomi/` | さらに別のゲームの機体ツクヨミを移植した初期の実験（クラウド環境用の古いスクリプト） |

`tools/` の主なもの:

| ファイル | 内容 |
|---|---|
| `nexaspac.py`・`pac_extract.py`・`pac_list_all.py` | NeXAS の pac の展開・作成・一覧 |
| `bfepac.py`・`bfe_spr.py`・`bfe_gr2.py`・`bfe_waz.py` | 移植元のゲームの形式の読み取り |
| `waz_summary.py`・`waz_refs.py`・`waz_struct_diff.py`・`mek_check.py` | waz / mek の要約・参照・差分・検査 |
| `waz_fields.json`・`bfe_waz_fields.json`・`waz_terms_ux.json` | waz の項目辞書（項目名・意味・確度）。GUI ツール BsdxWorkshop と共通。`gen_*.py` が生成元 |
| `bfe2bsdx_*.py`・`modified_tweaks.py`・`build_packs.py` | 移植元 → 対象ゲームの変換器、改善版の調整表、ビルドの入口（参考実装） |
| `harness/`・`patches/`・`delombok/` | NeXAS_DX を呼ぶ Java の小道具 |

GUI で waz を見る・編集するなら、別リポジトリの [BsdxWorkshop](https://github.com/OWNER/BsdxWorkshop) を使ってください。

## 必要なもの

* Python 3.11 以上、Java 17（移植パイプラインのみ）
* [NeXAS_DX](https://github.com/Karaik/NeXAS_DX)（移植パイプラインのみ。データの読み書きに使います）
* 対象ゲーム（と、移植元のゲーム）を自分で持っていること

変換器とビルド（`tools/bfe2bsdx_*.py`・`mods/`）は制作環境に合わせて書かれた参考実装で、まっさらな環境でそのまま動く手順はまだ用意していません。ゲームから取り出したデータ（`work/` 以下）を自分で用意する必要があります。古いスクリプトの一部は `/path/to/workspace` などの仮のパスを書き換えて使ってください。

資料の中の「調査記録 NN」は、制作中の調査の記録（非公開）の番号です。結論は資料の本文に書いてあります。

## 資料の確度

資料の「確定」は exe の処理かゲームデータの全件確認で裏付けたもの、「推定」「未確認」はそうでないものです。

## 謝辞

対象ゲームのデータ形式の解析の多くは、[Karaik](https://github.com/Karaik) さんの [NeXAS_DX](https://github.com/Karaik/NeXAS_DX)（MIT License）の成果を土台にしています。pac 形式の理解には [GARbro](https://github.com/morkt/GARbro) も参考にしました。

## ライセンス

コードは MIT License（[LICENSE](LICENSE)）、資料（`docs/`）は CC BY 4.0（[docs/LICENSE](docs/LICENSE)）です。
対象ゲーム・移植元のゲームの著作権は、それぞれの権利者にあります。
