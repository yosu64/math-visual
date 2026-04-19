# math-visual build tools

`tools/math-visual-build.el` は、リポジトリ直下の `index.org` を読み込み、公開用の `index.html` を生成するための Emacs Lisp ツールです。公開サイト本体と生成器を同一リポジトリ内で管理する前提に合わせ、入力元と出力先はこのリポジトリのルートに固定しやすい構成にしています。

## 期待する Org 形式

入力ファイルは `/Users/yosu64/math-visual/index.org` です。想定する構造は次のとおりです。

- レベル1見出し `* サイト情報`
- property として `:TITLE:` `:DESCRIPTION:`
- レベル1見出し `* 数I` `* 数C` `* 数III` など
- 分野見出しには `:TEXTBOOK:` を持たせてもよい
- 各分野の直下にレベル2見出し `** ドモルガンの法則` などを置く
- 各教材見出しでは `:PATH:` `:TEXTBOOK:` `:PAGE:` `:APP:` `:APP_URL:` `:PUBLISHED:` `:UPDATED:` を使える
- 教材見出しの本文は説明文として使われる

`サイト情報` 以外のレベル1見出しは分野セクションとして扱われます。教材は各分野直下のレベル2見出しだけを読みます。並び順は Org ファイル上の見出し順です。

## 使い方

Emacs から `tools/math-visual-build.el` を読み込み、公開関数 `math-visual-build-site` を実行してください。

```bash
emacs --batch \
  -l /Users/yosu64/math-visual/tools/math-visual-build.el \
  --eval "(math-visual-build-site)"
```

Emacs を開いている場合は `M-x load-file` で `tools/math-visual-build.el` を読み込んだあと、`M-x math-visual-build-site` でも実行できます。

## 読み込み元

- `/Users/yosu64/math-visual/index.org`

## 生成先

- `/Users/yosu64/math-visual/index.html`

生成される HTML は UTF-8 で書き出され、CSS は当面 `index.html` に埋め込みます。`PATH` がある教材名は内部リンクになり、`APP_URL` がある場合だけ APP 表示の横に外部リンクが付きます。公開 URL を安定させるため、`PATH` には `./math-i/...` `./math-iii/...` `./math-c/...` のような英語ディレクトリ名を使います。

## 将来拡張の余地

- HTML テンプレートと CSS を別ファイルへ分離する
- 分野や教材ごとの追加 property を表示項目に反映する
- CI から自動生成を呼ぶためのバッチ実行ラッパーを追加する
- `index.org` の妥当性チェックや警告出力を追加する
