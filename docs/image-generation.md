# 記事の入口画像を生成・確認・採用する

この仕組みは、記事に合う画像案を私用の作業領域で準備し、本人が生成枚数と費用を確認してから候補を生成し、実画像を見て採用するためのものです。採用はローカルの画像とmanifestの更新までです。HTMLの確認、Gitへの保存、サイト公開は、それぞれ後の工程です。

最初の利用先はmath-visualです。生成処理は記事サイトから分離してあるため、将来の別用途でも候補作成と確認の仕組みを再利用できます。

## 今回の実装範囲

出発点はmath-visualの固定版 `218811cb490ba7ac46ce4b100c0c86af1d5a54ab` です。今回の作業はソース、匿名検証、レビュー、続行手順の作成です。実際のOpenAI画像APIによる生成、APIキーの発行・変更、M5 Keychainへの保存、サイト公開は実施していません。実画像の品質、本人のOpenAIアカウントでのモデル利用可否、実請求、M5の実キーとの接続は、この匿名検証で確認済みになりません。

既存Skillは変更しません。画像生成のために、教材用のキーや既存の教材作業を切り替える処理もありません。

## 構成とデータの持ち主

| 部品 | 役割 | 扱わないこと |
| --- | --- | --- |
| `tools/image_pipeline.py` | 計画、費用見積り、1回限りの送信、実行記録、候補画像、本人確認の共通処理 | Orgの記事一覧、サイト公開、SVG正本の編集 |
| `OpenAITransport` | 固定のOpenAI Images APIへHTTPSで1回POSTする | 別providerへのfallback、redirect先の追跡、SDKによる再試行 |
| `load_key` | 専用環境変数、または専用Keychain項目の読取り | キー発行、キー保存・更新、教材用キーへのfallback |
| `tools/imagegen.py` | CLIとmath-visual用の変換処理。記事、画像案、採用先を結び付ける | 自動生成、Git操作、サイト公開 |
| `tools/math-visual-build.el` | 既存Org構文木からの記事一覧取得と、採用済み画像を使うHTML生成 | OpenAI API、秘密情報、候補画像の自動採用 |
| `tools/imagegen-config/math-visual-briefs.json` | 記事ごとの公開用要約、画像案、数学上の確認点、alt案 | 教師用注記、教科書画像、記事HTML全文のAPI送信 |

共通処理の`subject`には、利用先を表すadapter名と対象IDを渡します。math-visual用の処理は、`index.org`の公開メタデータ、記事HTMLのSHA-256、画像案のSHA-256を結び付けます。記事HTMLは一致確認のために読みますが、本文を自動抽出して画像APIへ送る処理はありません。APIへ送るのは、共通の作風指定と、明示的に整えた公開用要約・画像案です。

新しい記事を追加したときは、現在の記事を確認して画像案を追加します。既存の画像案と記事のhashが違う場合、別記事の案や過去の画像を推測で結び付けません。

### 私用の作業領域

`--workspace`には、Git checkout、Webサーバーの公開ルート、Dropbox・iCloud等の同期対象から外れた、本人だけが読めるローカルディレクトリを指定します。Git配下とsymlink経路はコードで拒否します。Webサーバーの設定やクラウド同期設定を検出する機能はないため、後二者は配置時に確認します。

新規ディレクトリは所有者のみが使えるモードで作成します。既存ディレクトリは所有者とモードを検査し、他の利用者に権限がある場合は拒否します。既存ディレクトリを自動で`chmod`して通すことはありません。標準の配置はディレクトリ`0700`、生成する私用ファイル`0600`です。

| 作業領域内の場所 | 内容 |
| --- | --- |
| `workspace.json` | この作業領域の識別子 |
| `inventory.json` | Orgから抽出した公開記事メタデータ |
| `plans/<plan_id>.json` | プロンプト、記事の結び付け、設定hash、枚数、価格、予算を含む計画 |
| `runs/<plan_id>/receipt.json` | 送信試行、取得画像、使用量、結果不明の記録 |
| `runs/<plan_id>/candidate-*.png` | 未公開の候補画像 |
| `reviews/` | 本人の採否、確認項目、画像hash、現在有効なレビューへの参照 |
| `previews/` | 本人が候補を見比べるためのHTML |

実際の価格・project設定、plan、receipt、候補一覧、確認用HTMLは私用領域に置きます。公開用のソースには匿名テンプレートと公開用の画像案だけを含めます。CLIの出力にもplanや確認用情報が含まれるため、そのままGitHubや公開ログへ貼り付ける運用にはしません。

## 確認を分ける

| 段階 | 確認する内容 | 次に許される操作 |
| --- | --- | --- |
| 価格 | model・品質・寸法に対応する出力見積り、単価、確認日、有効期限 | 価格を含む新しいplanの作成 |
| project | 教材用と画像用で使う正確なproject ID、別キーを使う方針 | 設定の作成 |
| キーの準備 | 別キーの発行・保存が必要か、既存の正式経路を使えるか | 本人が承認した別作業での発行・保存 |
| 課金を伴う生成 | 対象記事、送信内容、枚数、品質、寸法、見積り、予算、完全なplan ID | そのplanの送信を1回だけ開始 |
| 候補の確認 | 実画像、記事との対応、数学上の誤解、私的情報や教科書の混入、alt | 指定画像hashへの承認または却下の記録 |
| 採用 | 現在有効なreview IDと、必要なら置換対象の画像hash | ローカルの採用PNGとmanifestの更新 |
| サイトの確認 | 画像付き入口、既存リンク、教科書順、教材日時、Pick Up | 公開候補の内容確定 |
| 公開 | 実際に公開する差分と既存の公開手順 | 承認された公開操作 |

planを作ったことは課金許可ではありません。キーが読めることも課金許可ではありません。確認ページを開いただけでは採用されず、`adopt`を実行しても公開されません。

## モデル、品質、費用

### 初版の選択

初版のモデルは`gpt-image-2.5-flare-2026-09-08`に固定しています。2026-11-14に取得した公式資料では、この日付付きIDが案内され、モデルページにDeprecated表示はありませんでした。一方、公式の新規ワークフロー向け案内は2.6系を推奨しています。今回は、日付付きモデルに画像案と価格確認を結び付け、変更を本人が見直せる構成を優先しました。最新モデルへの自動切替はしません。将来変更するときは、モデルの利用可否、料金、生成例を確認して価格プロファイルとテストを更新します。

- [GPT-Image-2.5 Flareのモデルと日付付きID](https://developers.openai.com/api/docs/models/gpt-image-2.5-flare)
- [現在の画像生成ガイド](https://developers.openai.com/api/docs/guides/image-generation)
- [GPT-Image-2.6の画像プロンプト案内](https://developers.openai.com/api/docs/guides/image-prompting?model=gpt-image-2.6)

初版が受け付ける品質は`low`・`medium`・`high`、寸法は`1024x1024`・`1536x1024`・`1024x1536`です。既定は`low`、`1536x1024`。`auto`、SVG、GIF、画像編集、入力画像、streamingはこの実装に含めません。形式はPNG、背景は`opaque`に固定します。モデルが持つ全機能をこのCLIが公開するわけではありません。

### 価格プロファイルを埋める前は生成できない

2026-11-14に取得した公式資料の標準処理単価は、入力テキストが100万tokensあたりUSD 5、出力画像が100万tokensあたりUSD 30でした。これらは`price.example.json`に出典付きで示しています。品質と寸法ごとの出力費用は、この調査で数値根拠を確定できていないため、`output_image_estimate_usd`は`null`です。過去モデルの1枚あたり価格表を流用していません。

- [公式料金](https://developers.openai.com/api/docs/pricing)
- [モデル・品質・寸法を選ぶ公式計算器](https://developers.openai.com/api/docs/guides/image-generation#calculating-costs)

本人が後日利用するときに、テンプレートを私用領域へコピーし、選ぶmodel・quality・sizeの組合せで公式計算器を確認します。`output_image_estimate_usd`にはその組合せの1枚分の出力見積りを記入し、単価も再確認します。`verified_at`と`valid_until`はISO形式の日付、`operator_verified`は確認後に`true`にします。確認日から有効期限までは最大14日で、実行日のUTC日付がその範囲内でなければ拒否します。

数値不明、未確認、期限切れ、model・品質・寸法の不一致は、0円として扱わず停止します。価格ファイルの更新で既存planを上書き修正する運用にはせず、新しい価格付きplanを作り、改めて確認します。

見積りは次の計算です。

```text
1回の入力token割当 = プロンプトのUTF-8 byte数 + 1024
1回の入力見積り   = 入力token割当 × 入力単価 ÷ 1,000,000
全体の事前見積り  = (1回の入力見積り + 1枚の出力見積り) × 枚数
予約する見積額    = 全体の事前見積り × 1.25
```

金額はUSDで扱い、小数第6位まで切り上げます。UTF-8 byte数と1024の余裕、1.25倍の予備費はアプリ側の見積り方針です。正確なAPIトークン数や最終請求額の保証ではありません。`--budget-usd`が予約見積額未満なら送信しませんが、Images APIには今回確認した生成schema上、請求金額の上限を強制する引数がありません。**厳格に制限するのは送信回数と枚数であり、費用の制限は見積りに基づくものです。**

レスポンスに有効な使用量があれば、確認済み単価から使用量ベースの費用を計算します。それも請求書ではないため、成功時も`billing_total_known`は`false`です。税、為替、他の処理によるproject全体の使用額を集計する機能はありません。

## キーとprojectの設定

`settings.example.json`を私用領域へコピーして設定します。`project_id`と`textbook_project_id`に、本人が確認した同じIDを記入し、`same_project_confirmed`と`dedicated_image_key_confirmed`を確認後に`true`にします。設定全体のhashをplanへ結び付け、送信時には`OpenAI-Project`ヘッダーへ指定IDを渡します。

この検査は、記入されたIDの一致と本人の確認の記録です。キー本文からproject所属を解読する機能や、OpenAIの管理APIで所属を照会する機能はありません。したがって「教材用と同じprojectであることを実接続で検証済み」とは扱いません。

秘密の読取り元は次のどちらかです。

| `key_source` | 読取り元 |
| --- | --- |
| `environment` | `OPENAI_IMAGE_API_KEY`のみ |
| `keychain` | macOSの`/usr/bin/security find-generic-password`による固定service・指定accountの読取り |

`OPENAI_API_KEY`へのfallbackはありません。キー本文をCLI引数、設定JSON、ソースへ渡す入口もありません。環境変数を使う場合も、キー本文をコマンド履歴へ入力する手順は本書では設けません。本人が承認した秘密管理の方法でプロセスへ渡します。

Keychainのservice名は`org.yosu.openai.images`です。これは今回の実装が定めた設計値であり、その項目がM5に存在することを確認した値ではありません。`keychain_account`も実物を確認して記入する必要があります。このプログラムは項目を作成・変更しません。新しい画像用キーの発行・保存が必要な場合は、既存の教材用キーを保ち、本人の承認がある別作業として行います。

秘密は課金承認を確認した後で読みます。transportは固定origin、通常のTLS証明書検証、1回のPOSTを使い、エラー本文や秘密をログへ書きません。記録するのは安全な分類コード、HTTP status、形式を検査したrequest ID等です。

- [公式の認証、project指定、request IDの説明](https://developers.openai.com/api/reference/overview)
- [APIキーとservice accountの説明](https://developers.openai.com/api/docs/guides/api-keys)

## 通常利用の流れ

以下は将来利用するときの手順です。今回の納品では実画像APIを呼び出していません。課金を伴う例は、本人の確認後にだけ使う工程として分けています。

必要な実行環境はPython 3.10以上、`tools/requirements-imagegen.txt`のPillow、既存生成器が要求するEmacs/Orgです。Emacsの宣言上の下限は28.1です。検証した具体的な環境とM5で未確認の項目は、固定納品の検証結果・続行手順で確認してください。

### 1. APIを呼ばずに記事一覧と画像案を確認する

公開サーバーに配信されない私用checkoutから実行します。パスは実際の配置に置き換えます。

```bash
image_repo='/path/to/private-checkout/math-visual'
image_workspace="$HOME/.local/state/yosu-image-generation"
cd "$image_repo"

python3 tools/imagegen.py --workspace "$image_workspace" inventory \
  --repo "$image_repo" --emacs emacs

python3 tools/imagegen.py --workspace "$image_workspace" plan \
  --repo "$image_repo" \
  --article './math-ii/apollonius-circle.html' \
  --candidates 2 --quality low --size 1536x1024
```

`inventory`は既存Org構文木から公開メタデータを取得します。`plan`は私用の計画ファイルを作ります。この段階ではAPIもキーも使いません。価格・settingsを省略したplanは費用未確認の下書きとして作れますが、そのまま生成には使えません。

返された64桁の`plan_id`を使うと、送信予定の全文を確認できます。

```bash
image_draft_plan='返された64桁のplan_id'
python3 tools/imagegen.py --workspace "$image_workspace" show-plan \
  --plan "$image_draft_plan"
```

### 2. 後日、価格・project・専用キーの準備を確認する

テンプレートは私用領域へコピーします。次の例は既存の同名ファイルを上書きしません。

```bash
(
  umask 077
  cp -n tools/imagegen-config/price.example.json "$image_workspace/price.json"
  cp -n tools/imagegen-config/settings.example.json "$image_workspace/settings.json"
)
```

前述の確認を済ませてから私用コピーを編集します。キー本文はどちらのJSONにも記入しません。キー発行が必要なら、この工程で別途本人が承認した正式な準備を行います。

価格・設定を含めたplanを新しく作ります。下例のUSD 1.00は予算入力の例であり、実費や適切な予算を示す値ではありません。実際には本人が認めた予算に置き換えます。

```bash
python3 tools/imagegen.py --workspace "$image_workspace" plan \
  --repo "$image_repo" \
  --article './math-ii/apollonius-circle.html' \
  --candidates 2 --quality low --size 1536x1024 \
  --price "$image_workspace/price.json" \
  --settings "$image_workspace/settings.json" \
  --budget-usd 1.00
```

生成枚数、model、品質、寸法、プロンプト、見積り、予約見積額、予算を確認します。新しく返されたIDが、次の課金確認の対象です。下書きのIDを流用しません。

### 3. 本人がそのplanへの課金を承認した後だけ生成する

**次のコマンドは実際に課金を伴うAPIリクエストを送る入口です。今回の納品時点で実行する工程ではありません。**

```bash
image_plan='本人が内容と課金を確認した64桁のplan_id'
python3 tools/imagegen.py --workspace "$image_workspace" generate \
  --repo "$image_repo" --plan "$image_plan" \
  --settings "$image_workspace/settings.json" \
  --confirm-plan "$image_plan" --approve-charge
```

`--confirm-plan`の完全一致と`--approve-charge`の両方が必要です。設定・記事・index・画像案・価格がplanと合わなくなっていれば停止します。

1つのplanは最大4枚で、常に`n=1`のリクエストを逐次送ります。最初に各送信の記録を保存してからPOSTします。自動retryは0回です。1件でも結果不明になれば残りを送りません。画像が取得できても、使用量が不明、または使用量ベースの費用が予約見積り等を超えた場合は残りを停止します。

### 4. 実画像を見て採否を記録する

```bash
python3 tools/imagegen.py --workspace "$image_workspace" status --plan "$image_plan"
python3 tools/imagegen.py --workspace "$image_workspace" review-page \
  --repo "$image_repo" --plan "$image_plan"
```

返されたHTMLをローカルで開きます。候補画像、対象記事へのリンク、記事の要約、記事固有の数学上の確認点、画像hash、生成計画が表示されます。このページは未公開の確認資料です。

本人が実画像を見て承認するときは、画面に出た画像hashを指定します。5つの確認フラグは、実際に確認した内容の記録です。生成に成功しただけで指定するものではありません。

```bash
image_sha='本人が見た候補の64桁の画像SHA-256'
python3 tools/imagegen.py --workspace "$image_workspace" review \
  --plan "$image_plan" --candidate 1 --image-sha256 "$image_sha" \
  --decision approve \
  --viewed-image --matches-article --math-not-misleading \
  --no-private-or-textbook-material --alt-checked \
  --alt '円形の光の軌跡でアポロニウスの円をイメージしたイラスト'
```

不適切なら、同じ画像hashを指定し`--decision reject`で記録します。却下時には承認用の確認フラグを揃える必要はありません。採否を更新すると、その候補の現在有効なレビューが切り替わるため、後から却下した候補に古い承認を使って採用することはできません。

### 5. 採用PNGをローカルに配置する

```bash
image_review='現在有効な承認レビューの64桁のreview_id'
python3 tools/imagegen.py --workspace "$image_workspace" adopt \
  --repo "$image_repo" --plan "$image_plan" \
  --review-id "$image_review" --confirm-review "$image_review"
```

画像hash・記事hash・現在のレビューを再確認し、`images/entries/<画像hash>.png`と`images/entries/manifest.json`を更新します。既に同じ記事の画像がある場合は、既存manifestにある画像hashを`--replace-image-sha256`で明示しなければ置換しません。

採用先へ渡すのは、確認済みPNGと最小限のmanifestです。プロンプト、候補一覧、project ID、API request ID、設定、実行receipt、教師用注記は公開用ディレクトリへコピーしません。`adopt`の結果は`published: false`です。HTML生成、commit、push、deployは実行しません。

### 6. サイトの見え方を確認し、その後に公開を判断する

公開されていない私用checkout内で、既存`index.html`をテンプレートにして別名の確認用HTMLを生成できます。未使用の出力名を選びます。

```bash
emacs -Q --batch -L tools -l tools/math-visual-build.el \
  --eval '(math-visual-build-site "index.org" "index.image-review.html" "index.html")'
```

同じcheckout内に置くことで、既存の相対記事リンクと採用画像の経路を確認できます。この確認用HTMLを公開対象へ自動追加する処理はありません。`math-visual-build-site`を出力指定なしで呼ぶと既定の`index.html`を更新するため、プレビュー段階では別名を指定します。

公開前には、生成HTMLの差分と実際の表示を確認します。採用済み画像だけを含めること、教科書画像や教師用注記を公開物へ加えないことを確認したうえで、既存の公開手順を使います。本機能に公開コマンドはありません。

## 数学の誤解を避けるための確認

画像案は入口用のイラストに限定し、文字、数字、数式、座標軸、ラベル付きグラフ、教科書の再現を生成指示から除いています。たとえば、二項分布は実測値のグラフではなく二色のコイン、アポロニウスの円は特定の比や定点の位置を主張しない円形の光として提案します。

こうした指示でも生成結果の正しさは保証できません。候補確認では、図が誤った集合領域、確率の高さと面積の混同、条件の逆転、根拠のない数値や図形の位置関係を示していないかを、対象記事と見比べます。正確な説明図が必要な場合は、この入口画像の採用で代用しません。

受信PNGはbase64、ファイル形式、指定寸法、実際の画素のdecodeを検査します。RGBに変換し、PNGの付随メタデータを落として保存します。候補と承認は保存した画像のhashで結び付け、画像を差し替えた後に以前の確認を流用できないようにします。画素検査やメタデータ除去は、内容の数学的検証ではありません。

サイトには「教材をイメージしたイラスト」と表示します。altは画像の内容を説明し、画像が証明や正解の図であるかのように書かないことを確認します。

## 既存の入口を保つ

記事の正本は引き続き`index.org`です。既存のOrg構文木とページ番号の整列を使い、教科書のページ順、記事URL、アプリへのリンク、公開日・更新日を画像の生成日時で置き換えません。

有効な採用画像があれば、画像からも既存記事へ進める入口を追加します。タイトルのリンクは残します。画像がない、承認情報がない、画像が欠損している、画像hashが違う、記事HTMLが変わっている等の場合は、その画像を表示せず既存のタイトルリンクを使います。manifestの不備で記事一覧そのものを消す設計にはしていません。

既存`index.html`をテンプレートとして使う場合、更新するのは連続した教科セクションと管理対象の画像CSSです。Pick Upなど周辺の既存内容は保持します。既知のセクション構造を判定できない、セクションが曖昧に入れ子になっている、教科セクション間に独自内容がある場合は、全体を作り直して消すのではなく生成を拒否します。その場合は、現在のテンプレートと残す内容を確認してから生成器を対応させます。

## 失敗・中断後は同じ記録を確認する

```bash
python3 tools/imagegen.py --workspace "$image_workspace" status --plan "$image_plan"
```

| 状態 | 意味と扱い |
| --- | --- |
| `not_attempted` | この作業領域に実行claimがない。課金許可や設定が成立したことは意味しない |
| `claimed_outcome_unknown` | 実行用ディレクトリはあるがreceiptが読める形でない。未送信と断定せず、再送しない |
| `prepared`・`dispatch_started`・`in_progress` | 完結したreceiptではない。statusに結果不明の観測注記を付け、再送しない |
| `outcome_unknown` | 送信結果、中断後の状態、保存結果等が不明。請求の可能性を保持する |
| `stopped_usage_unknown` | 画像は取得したが使用量を確定できず、残件を停止した |
| `stopped_cost_overrun` | 使用量ベースの費用が見積り条件を超え、残件を停止した |
| `candidates_received` | 候補を取得した。本人確認・採用・公開・最終請求確認は別 |

同じplanに対する実行claimは削除せず、再実行を拒否します。receiptの保存が途中で失敗しても、残ったclaimを自動で解除しません。APIが画像を生成した後に通信が切れる可能性があるため、timeoutを0円・未生成とは扱いません。

**結果不明のplanを避けるために、内容が同じ新しいplanを作って送り直してはいけません。** 新planのIDを跨ぐ請求照会や重複判定は実装していません。保持したplan・receipt・request ID、本人のAPI利用状況等を確認し、何が未確認かを残したうえで、追加の生成を行うか別途判断します。取得済みの候補を見て確認する作業と、残りを再生成する判断は分けます。

API request IDは調査の手掛かりであり、重複請求を防ぐ保証ではありません。[公式のリクエスト追跡の説明](https://developers.openai.com/api/reference/overview)と、[timeout後にも処理が続き得ることを説明する公式予算制御例](https://developers.openai.com/cookbook/articles/per_run_spending_controller_responses_api)を参照してください。後者はResponses APIの例であり、本実装にImages APIの結果回収機能を追加するものではありません。

## 将来のyosu-icons等との連携

yosu-iconsではSVGが正本です。今回、その現行リポジトリの内容は確認しておらず、変更もしていません。画像生成モデルにSVG出力機能があっても、それだけで既存SVGの置換を許す理由にはしません。

再利用できる範囲は、共通coreによる候補作成、費用・送信記録、実画像への本人確認までです。将来の連携先へ渡す場合も、まず候補または参考資料として扱います。この版には、ラスタ画像からSVGへの変換、SVG正本への自動書込み、yosu-icons用の採用adapterはありません。

連携を実装する際には、その時点の正本・編集規則・既存Skill・公開工程を読み、必要な出力形式と確認項目を定めます。別の利用先を追加するだけで、既存の課金許可や採用許可を引き継ぐことはありません。

## 匿名検証

共通coreの検証は、合成PNG、合成project ID、合成価格プロファイル、固定したテスト日付を使います。HTTP、socket接続、Keychainのsubprocessは遮断またはmockに置き換えます。合成価格は料金の根拠ではありません。

```bash
python3 -m unittest discover -s tools/test -p 'test_image_pipeline.py' -v
```

承認前の送信0回、秘密のfallback禁止、枚数制限、未知を残す中断、再送禁止、並列claim、画像・レビューの差替え拒否、metadata除去等を検証します。CLIとOrg生成器の検証、独立レビュー、固定ソースに対応する実行結果は、納品時の検証資料で別に記録します。

本書のOpenAI仕様・料金の確認日は2026-11-14です。日付付きモデルであっても、将来の利用可否と料金を保証しません。実生成前に公式資料と本人のprojectで再確認し、確認できない値を推測で補わず、価格未確認のまま保持してください。
