# 独立レビュー

実装source: `c1b4cf2d18e616c524eb8215c1e044d49722ae7c`

## 結果

**最終版の未解消blocking指摘は0件です。Critical、High、Mediumはいずれも0件です。**

共通core、CLI、Emacs生成器、価格・設定例、通常利用文書を、これらの実装に参加していない別のChatGPT担当が読み、
匿名再現と既存suiteの再実行で確認しました。Codex CloudやGitHubの外部review botは使っていません。
これは人間のコード承認、本人による実画像の採用承認、OpenAIの実課金試験ではありません。

レビュー担当は18記事の画像案の作成には参加しています。そのJSONは独立レビューの対象から除外しました。
主担当が全18件の主題・避ける誤解・alt案を確認し、固定記事のPATH・title・hashとの対応を検証しています。

## 指摘と解消

| 重大度 | 当初の問題 | 解消と確認 |
| --- | --- | --- |
| High | 一度承認してから却下した候補に、古い承認を使えた | 候補ごとの最新review参照とlockを導入。古い承認の拒否を確認 |
| High | inventoryのsymlink先をEmacsが先に書き換える余地 | subprocess前のsymlink拒否、一意な一時出力、検証後のatomic置換 |
| Medium | 新しいrun名の親ディレクトリへの永続化が不足 | API送信前に親ディレクトリをfsync。実電源断の保証には広げない |
| Medium | RGB再保存時にICC情報が残る | PNG metadataを明示的に消去。文字情報・EXIF・ICCの回帰に合格 |
| Medium | `..`を含むpathで、export済みrepo内workspace判定を回避できる | symlink確認後に物理pathを解決し、明示repo境界を確認 |
| Medium | 異常なrequest IDに秘密らしい文字列が残る余地 | 通常応答・例外応答の両方でsafe request ID検査 |
| Medium | index/生成器symlinkと曖昧なarticle path | 正本ファイルのsymlink拒否、canonicalなarticle pathを要求。結合試験に合格 |

加えて価格profileの完全なfield制限、subjectの秘密らしい文字列の拒否、workspaceと候補のbinding、
引数エラーが入力内容をそのまま表示しないことを確認しました。

## 再実行した検証

- Python core/adapter **71/71**。
- Emacs ERT **17/17**。
- 実Emacsを使う匿名の一連のsmoke **合格**。
- 固定版の5科目、18カード、Pick Up、既存hrefの並び **保持**。
- `index.org`、既存`index.html`、既存Skill **不変**。

初期の独立auditでも、課金確認なし、timeout、同plan再送、秘密sentinel非露出、usage不明、
費用超過、同時claim、別記事への誤採用、記事変更、公開manifestの制限等を再現しました。
最終的な再現入口はリポジトリに含む匿名suiteとsmokeです。

## 確認した境界

生成はモデル・送信内容・対象記事・枚数・品質・寸法・価格・予算・設定を含むplanの確認に結び付いています。
自動retryはなく、開始済みの結果不明を未送信へ読み替えません。
採用には実画像hash、対象記事hash、最新の本人判断が必要です。
公開用には確認済みPNGと限定manifestだけを渡し、CLIに公開・Git操作はありません。

生成器は既存HTMLの周辺部分を保持し、分からないshellを無言で作り直しません。
画像の欠損や古さで記事の入口を失わせません。
費用未確認の停止、専用Keychain項目が設計値であること、請求上限の限界、
yosu-iconsのSVG正本を変更しないことは文書と実装で一致しています。

## 証拠と限界

検査対象の完全なSHA-256と機械可読の判定は[INDEPENDENT-REVIEW.json](INDEPENDENT-REVIEW.json)に記録しています。
M5 native、実Keychain、実OpenAI API、実課金、実画像の数学的確認、ブラウザ目視、
実電源断、本番公開は、このレビューの合格範囲に含めていません。
