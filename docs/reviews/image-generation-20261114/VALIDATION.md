# 検証結果

実装source: `c1b4cf2d18e616c524eb8215c1e044d49722ae7c`

検証日: 2026-11-14 JST。今回の検証はChatGPTによるsource-only作業と匿名fixtureで実施しました。
Codex Cloud task、Code Review bot、`@codex`依頼は起動していません。

## 実行した試験

| 検証 | 実行内容 | 結果 |
| --- | --- | --- |
| Python core/adapter | `python3 -m unittest discover -s tools/test -p 'test_image*.py' -v` | 71/71、exit 0 |
| Emacs生成器 | `emacs -Q --batch -L tools -l tools/test/math-visual-build-test.el -f ert-run-tests-batch-and-exit` | 17/17、exit 0 |
| 一連の匿名試験 | `python3 tools/test/image_pipeline_smoke.py --emacs emacs` | passed、実API 0、fake送信1 |
| 構文・差分 | Python compile、Emacs読込み、`git diff --check` | 合格 |
| 固定版保持 | baseの保護対象26ファイルのbytes/SHA-256と比較 | 全て一致 |
| 18記事の画像案 | 公開metadataのPATH・title・記事hash・順序と対応、全記事で課金なしのplan作成 | 全件合格 |
| 実一覧の生成 | 現行Orgを一時HTMLへ生成し、18カードとPick Upのmarkupを比較 | 一致 |

Python試験の合成価格はサービスの料金根拠ではありません。合成PNGは単色等の匿名fixtureであり、AIによる生成画像ではありません。
本人確認のチェックも試験内の仮の判断です。未生成の実画像を承認したものではありません。

Python suiteではHTTP、socket接続、実Keychain subprocessを遮断しています。
smokeは製品3ファイルを別の匿名repoへコピーし、hash一致を確認したうえで実Emacsの5回だけを許可します。
実repoへ候補を採用する操作はありません。

## 重点的に確認した失敗

- 課金確認、正確なplan hash、同project・専用キーの確認、価格・期限・予算が不足する場合は送信前に拒否。
- 教材用の`OPENAI_API_KEY`へfallbackしない。
- timeout、429、500、不正応答、保存失敗、中断は再送せず結果不明を保持。残りの要求も送らない。
- 同時に同じplanを実行しても、送信開始は1回。同じplanのclaimを消して再利用しない。
- usage不明・費用見積り超過で残りを停止。
- 記事・index・brief・候補画像の変更、別記事のreview、古い承認、確認項目不足を採用前に拒否。
- 候補を後から却下した場合、以前の承認は採用に使えない。
- 公開manifestへprompt、project ID、API request ID、設定、私用receiptをコピーしない。
- PNGの文字情報・EXIF・ICCを除去。secret-likeなrequest IDや例外本文を記録しない。
- repo内の私用workspace、symlink、曖昧なarticle path、既存画像の未確認置換を拒否。
- inventory取得失敗でも旧inventoryを保持。
- 画像なし・欠損・stale・不正manifestの場合もタイトルから記事へ進める。

## 原本と既存作業の保持

`index.org`、公開`index.html`、18記事、既存の3画像、科目別index、既存publication Skillは
固定baseから変更していません。詳細は[source-preservation.json](source-preservation.json)です。
画像用manifestは空です。公開ディレクトリへ新しい画像、教科書画像、教師用注記を追加していません。

Skillの配置・配布、教材用のキー設定、既存の実行作業への変更はありません。
yosu-iconsのコード、SVG、Skill、権限を読替えたり変更したりしていません。

## 環境と再現性

Linux上のPython 3.12、Pillow 13.0.0、Emacs 30.1、Org 9.7.11で検証しました。
Emacsは通常の署名付きパッケージを作業用領域へ展開して実行し、システム導入、昇格、設定・権限変更はしていません。
M5の環境で同じ試験が合格したことは意味しません。

新規試験の実行記録は[python-tests.txt](python-tests.txt)、[ert-tests.txt](ert-tests.txt)、
[smoke.json](smoke.json)に保存しています。productの固定hashとsuiteのhashはmanifestとreviewに記録しています。

## 未実施・観測できなかった項目

| 項目 | 状態 |
| --- | --- |
| OpenAIの実画像API | 未実行 |
| 実費・利用可否・実画像の品質 | 未確認 |
| M5 Keychainの実項目・読取り・同projectの実接続 | 未確認 |
| キー発行・保存・権限変更 | 未実行 |
| M5のnative匿名受入 | 未実行 |
| 実ブラウザの画像付き表示・モバイル幅目視 | 未確認 |
| 実電源断 | 未実施。fsync順序をレビュー・fixtureで確認した範囲 |
| mainへのmerge・サイト公開・実画像採用 | 未実行 |

匿名Chromium起動では`process_singleton`の`socket()`が`EPERM`で失敗し、ページを開けませんでした。
これは表示の合格・不合格の証拠ではありません。権限変更や同条件の反復は行っていません。

Gateway経由のRunner読取りはtransport failureでした。案内されたfallback後、専用Runner readerから
保存情報と`loaded-not-running`のListener観測を得ましたが、実行経路の稼働は確認できていません。
起動・修復・新規検証要求の投入はせず、M5での検証を完了扱いにしていません。

## 読戻し

実装sourceの16変更ファイルは、接続済みGitHubから固定commitで全文を読み戻し、検証したローカルbytesと一致を確認しました。
deliveryの全manifest対象、保護対象のGit blob、PR head、mainの状態は最終納品時に再照合します。
将来のbranch更新を、この固定版の検証済み状態と混同しないでください。
