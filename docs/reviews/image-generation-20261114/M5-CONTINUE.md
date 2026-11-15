# M5での続行手順

作成日時: 2026-11-14 17:22 JST

対象: [math-visual Draft PR #3](https://github.com/yosu64/math-visual/pull/3)

実装source: `c1b4cf2d18e616c524eb8215c1e044d49722ae7c`

以下は後日M5で続行する担当者向けの手順です。この納品作業ではM5への導入・接続復旧・本番操作をしていません。
既存の作業場所、Skill、教材、キーを変更せず、独立したcheckoutで匿名受入を行ってください。

## 1. 既存作業から分けた固定checkout

既存の対象repoを確認して`image_repo`を設定します。未コミット作業をstash、reset、cleanしたり、
既存branchを切り替えたりする必要はありません。

```bash
image_repo='/path/to/existing/math-visual'
image_accept_root="$(python3 -c 'from pathlib import Path; import tempfile; print(Path(tempfile.mkdtemp(prefix="math-visual-accept-")).resolve())')"

git -C "$image_repo" fetch origin feature/reviewed-image-pipeline-20261114
git -C "$image_repo" worktree add --detach "$image_accept_root/source" \
  c1b4cf2d18e616c524eb8215c1e044d49722ae7c

cd "$image_accept_root/source"
git rev-parse HEAD
git status --short
```

HEADが上の完全なsource SHAと一致し、checkoutが清潔であることを確認します。
納品文書の後続commitは検証資料を加えたものです。実行する製品sourceは上記で固定できます。
このcheckoutをGitHub Pages等の公開元へ設定しないでください。

macOSの`/var`等はsymlinkになり得るため、匿名fixtureと私用workspaceの親には上の物理pathを使います。
通常のsource/assetにsymlinkがある場合はguardを緩めず、正しい実体を確認してください。

## 2. 既存の実行環境を確認

```bash
python3 --version
python3 -c 'import PIL; print(PIL.__version__)'
emacs -Q --batch --eval '(progn (require (quote org)) (princ (format "Emacs %s; Org %s\n" emacs-version (org-version))))'
```

Python 3.10以上、Pillow、Emacs/Orgが必要です。今回検証した環境はPython 3.12、Pillow 13.0.0、
Emacs 30.1、Org 9.7.11です。依存が不足する場合は、その不足を記録します。
キー発行・権限変更・停止中の接続復旧を依存の準備へ混ぜません。
新しいPython環境が必要なら、本人の既存方針に従う専用環境へ`tools/requirements-imagegen.txt`を導入する判断を別に行います。

## 3. APIを呼ばない匿名受入

```bash
mkdir "$image_accept_root/results"

python3 -m unittest discover -s tools/test -p 'test_image*.py' -v \
  > "$image_accept_root/results/python-tests.txt" 2>&1

emacs -Q --batch -L tools \
  -l tools/test/math-visual-build-test.el \
  -f ert-run-tests-batch-and-exit \
  > "$image_accept_root/results/ert-tests.txt" 2>&1

python3 tools/test/image_pipeline_smoke.py --emacs emacs \
  --output "$image_accept_root/results/smoke.json"
```

各コマンドのexitとログを個別に確認し、失敗後に後続工程の成功だけで全体成功にしないでください。
期待結果はPython **71/71**、ERT **17/17**、smoke **passed**です。
smokeには実API 0、Keychain 0、network 0、fake transport 1の証拠が含まれます。
合成画像と仮の本人確認は一時fixture内だけで扱い、終了後に削除されます。

失敗した場合はこの同じsourceでの匿名結果を保持し、原因を限定して確認します。
APIへの切替、教材用キーへのfallback、権限緩和、M5サービスの再起動で試験を通しません。
同じ証拠ファイルを上書きせず、再確認が必要なら未使用の結果先を選びます。

## 4. 固定18記事の計画を課金なしで確認

```bash
python3 tools/imagegen.py --workspace "$image_accept_root/workspace" inventory \
  --repo "$image_accept_root/source" --emacs emacs

python3 tools/imagegen.py --workspace "$image_accept_root/workspace" plan \
  --repo "$image_accept_root/source" \
  --article './math-ii/apollonius-circle.html' \
  --candidates 1 --quality low --size 1536x1024 \
  > "$image_accept_root/results/draft-plan.json"

image_draft_plan="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["plan_id"])' "$image_accept_root/results/draft-plan.json")"
python3 tools/imagegen.py --workspace "$image_accept_root/workspace" show-plan \
  --plan "$image_draft_plan"
```

記事一覧18件、正確な対象記事、公開要約、画像案、3項目の確認点、alt案を確認します。
価格と設定を指定していないplanは`unverified`で、費用は`null`です。
それは0円でも、送信可能でもありません。この段階ではキーを取得しません。

画像なしの公開表示を確認する場合も、出力は隔離したcheckout内にします。

```bash
emacs -Q --batch -L tools -l tools/math-visual-build.el \
  --eval '(math-visual-build-site "index.org" "index.image-review.html" "index.html")'
```

相対リンクが機能する同じcheckout内でプレビューを開き、18記事、教科書順、日時、Pick Upを確認します。
このファイルをcommit・公開する操作は含めません。画像付き表示と候補確認画面の実ブラウザ目視は、
後日の候補取得・採用が承認された段階で追加確認します。今回のLinux試験はブラウザ起動前の環境エラーで止まったため、
その未確認をM5合格へ読み替えないでください。

## 5. 後日の実生成へ進む前に、具体的な計画を本人へ提示

今回の依頼は本番生成、キー発行、権限変更、公開を含みません。
匿名受入が合格しただけで、この段階へ自動で進めません。

次に本人へ示す内容は、対象記事、送信する画像案、モデル、枚数、品質、寸法、
出典付き費用見積り、予算、保存先、数学上の確認点です。
キーを新規発行する必要があるなら、その操作と保存先を別に具体化します。

- 教材用と同じOpenAI projectを確認し、画像用の別キーを使う。
- Keychain service `org.yosu.openai.images` は今回定義した読取り先で、M5に存在確認済みの項目ではない。
- 既存の教材用キー・Keychain項目・ACLを流用・上書きしない。
- モデル・品質・寸法ごとの出力見積りを公式計算器で確認する。数値が確認できなければ停止。
- 有効期限付き価格profileと設定を私用領域に作り、費用を含む新しいplanを本人が確認する。
- 生成の確認と、実画像の採否、ローカル採用、サイト公開の判断を分ける。

操作の実引数は[通常利用手順](../../image-generation.md)に記載しています。
この続行手順には、すぐ実行できる課金コマンドやキー発行コマンドを組み込んでいません。

## 6. 中断時

開始済みplanのclaimやreceiptを消さず、同じplanの`status`を読みます。
timeoutや保存失敗は、未送信・未生成・0円の証明ではありません。
結果不明を避けるための新plan再送もしません。
取得済み候補の確認と、追加費用を伴う生成の判断を分けて、本人へ現在の記録と未確認点を示します。

M5の受入結果には、source SHA、実行環境、各試験のexitと件数、smokeのAPI/Keychain回数、
既存作業不変、ブラウザ目視の有無を記録してください。生の秘密・project ID・候補ログを公開PRへ貼らないでください。
