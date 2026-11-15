# OpenAI画像生成の共通基盤とmath-visual入口

作成日時: 2026-11-14 17:22 JST

**実装・匿名検証・独立レビューまで完了したsource-onlyの納品です。**
生成画像を採用した状態にはしていません。公開用manifestは空で、既存のサイト入口と教材を維持しています。

## 固定入口

| 項目 | 固定値 |
| --- | --- |
| Repository | `yosu64/math-visual` |
| Draft PR | [#3](https://github.com/yosu64/math-visual/pull/3) |
| Branch | `feature/reviewed-image-pipeline-20261114` |
| 指定されたbase | `218811cb490ba7ac46ce4b100c0c86af1d5a54ab` |
| 実装source | [`c1b4cf2d18e616c524eb8215c1e044d49722ae7c`](https://github.com/yosu64/math-visual/tree/c1b4cf2d18e616c524eb8215c1e044d49722ae7c) |
| 納品delivery | この文書を含む固定commit。最終返信・PR説明に完全なSHAを記載 |

実装sourceには製品コード、18記事の画像案、設定例、全匿名テスト、通常利用の説明が含まれます。
後続のdeliveryは検証証拠・レビュー・続行手順だけを加え、製品コードを変更しません。
この文書自身へ自分のcommit/hashを書き込む循環参照は作りません。

## 完成した流れ

1. 既存のOrg構文木から記事一覧を取得し、記事に合う画像案を計画する。ここではAPIもキーも使わない。
2. モデル・枚数・品質・寸法・価格・予算・送信内容を確認し、完全なplan IDへの課金確認がある場合だけ候補を生成する。
3. 私用HTMLで候補と対象記事を見比べ、記事との対応・数学的な誤解・教科書や私的情報の混入・altを確認する。
4. 指定画像hashへの最新の承認がある候補だけを、ローカルのPNGと公開用manifestへ採用する。
5. 既存のPick Upを保持してHTMLを作り、表示と差分を確認してから、別途公開を判断する。

共通coreにはサイト固有の処理を入れず、Org・記事の結び付け・採用先はmath-visual用の処理に置きました。
yosu-iconsの現行版は未確認・未変更です。SVG正本の自動置換、ラスタからSVGへの変換、専用の書込み処理はありません。

## 検証結果

| 検証 | 結果 |
| --- | --- |
| Pythonの匿名試験 | **71/71**（core 40、adapter 31） |
| Emacs/OrgのERT | **17/17** |
| 実Emacsを使う匿名の一連の試験 | **合格** |
| 固定版の18記事・Pick Up・全既存リンク・日時 | **保持** |
| `index.org`・`index.html`・記事・既存画像・Skill等の保護対象 | **26ファイル不変** |
| 独立レビュー後の未解消Critical/High/Medium | **0件** |
| 実画像API・実キー取得・実Keychain操作 | **0回** |

出力見積りを確認していない条件は`null`のままです。公式計算器でそのモデル・品質・寸法の金額を確認し、
有効期限付きの価格profileと予算を用意するまで生成しません。費用は事前見積りであり、APIによる請求保証上限ではありません。

## 読む順番

- [通常利用・構成・価格と秘密管理・将来のSVG連携](../../image-generation.md)
- [検証結果と未確認事項](VALIDATION.md)
- [独立レビューと修正履歴](REVIEW.md)
- [M5での続行手順](M5-CONTINUE.md)
- [納品manifest](MANIFEST.json)
- [機械可読の検証結果](validation.json)
- [匿名smoke証拠](smoke.json)
- [既存ファイルの保持証拠](source-preservation.json)
- [独立レビューの固定対象](INDEPENDENT-REVIEW.json)

## 今回行っていないこと

実画像の本番生成、キーの発行・保存・変更、権限変更、サイト公開、mainへのmerge、
M5への導入、停止中の接続・Runnerの復旧は行っていません。
M5の実キー、実モデル利用、実課金、実候補の数学的内容、実ブラウザでの目視は確認済みではありません。

Chromiumの匿名表示試験はページを開く前の環境エラーで起動できませんでした。
コード上のHTML構造・リンク・画像の採用境界の検証と、目視による表示確認を区別しています。
