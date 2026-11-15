# math-visual build tools

`tools/math-visual-build.el` reads the repository's `index.org` with Org's syntax
tree. It builds the subject lists and can export a public article inventory for
the reviewed image workflow. These operations do not call an API or publish a
site.

## Preserve the existing site

`math-visual-build-site` accepts `input-file`, `output-file`, and an optional
`template-file`. With no arguments, it uses the repository's `index.org` and
`index.html`. When `index.html` exists beside the input, the builder uses it as
the template, even when writing a preview elsewhere.

The builder replaces only the contiguous `subject-section` region and its own
entry-image CSS block. The surrounding HTML, including **Pick Up**, existing
styles, header, and other custom content, stays in place. An explicit third
argument selects another template. If an existing template is malformed, or
custom content is found between subject sections, the build stops before
writing. It never silently falls back to a fresh document and discards the
existing shell. A fresh complete document is generated only when no template
exists.

From the repository root, create a preview in a fresh temporary directory:

```sh
image_preview_dir="$(mktemp -d "${TMPDIR:-/tmp}/math-visual-preview.XXXXXX")"
emacs -Q --batch -l tools/math-visual-build.el \
  --eval "(math-visual-build-site \"index.org\" \"$image_preview_dir/index.html\")"
```

Relative article and image links need the repository's accompanying files. For
a clickable preview, use an isolated copy of the repository, build its
`index.html`, and serve or open that copy. A standalone temporary HTML is useful
for a diff, but is not a complete site preview. Check the diff and browser view
before separately approving publication. Building does not commit, push, merge,
or deploy anything.

## Org metadata and ordering

- The level-one `サイト情報` heading has `TITLE` and `DESCRIPTION`.
- Other level-one headings are subjects and may have `TEXTBOOK`.
- Direct level-two headings are articles. Supported metadata remains `PATH`,
  `TEXTBOOK`, `PAGE`, `APP`, `APP_URL`, `PUBLISHED`, and `UPDATED`.
- Article descriptions come from the direct heading body. Article HTML is not
  imported into the sitemap.
- Subject order and first-seen textbook group order are retained. Within each
  textbook, confirmed integer `PAGE` values sort numerically. Equal pages retain
  their existing order. Unconfirmed/non-numeric pages stay last without being
  guessed. Date metadata is displayed as recorded and is never rewritten by
  sorting or image adoption.

The existing publication Skill remains authoritative for confirming actual
textbook pages and keeping textbook images and teacher notes out of public
HTML. This change does not modify that Skill or authorize publication.

## Approved entry illustrations

The optional manifest is `images/entries/manifest.json`. It is written by the
separate reviewed image adoption step; editing a manifest is not a substitute
for reviewing a candidate. Its public schema is:

```json
{
  "schema": "math-visual-entry-images/v1",
  "images": [
    {
      "article": "./math-i/example.html",
      "article_sha256": "64 lowercase hexadecimal characters",
      "image": "./images/entries/<image-sha256>.png",
      "sha256": "64 lowercase hexadecimal characters",
      "alt": "The reviewed image's useful short description",
      "role": "entry-illustration",
      "reviewed_at": "2026-11-14T00:00:00Z",
      "review_id": "64 lowercase hexadecimal characters",
      "approved": true
    }
  ]
}
```

The builder requires an exact article `PATH` match, matching article and image
SHA-256 hashes, approval metadata, a PNG header, and confined local file paths.
It rejects symlink components, traversal, external URLs, duplicated article
bindings, and stale assets. An absent, invalid, stale, or missing image is
omitted; the existing title link, description, textbook page, and dates remain
usable. A generic warning contains no raw manifest data.

An accepted illustration links to the same article as the title, has reviewed
alt text, uses `object-fit: contain`, and has the caption
「教材をイメージしたイラスト」. The title link is always present, including when
the browser cannot load the image. The image is an entrance illustration;
mathematical explanations remain in the article. No candidate directory,
private review receipt, textbook image, or teacher note is rendered by this
manifest reader.

## Export an article inventory

```sh
image_inventory_dir="$(mktemp -d "${TMPDIR:-/tmp}/math-visual-inventory.XXXXXX")"
emacs -Q --batch -l tools/math-visual-build.el \
  --eval "(math-visual-build-image-inventory \"index.org\" \"$image_inventory_dir/inventory.json\")"
```

The schema is `math-visual-image-inventory/v1`. The `articles` array contains
`path`, `title`, `description`, `subject`, `textbook`, `page`, `published`,
`updated`, and `article_sha256`. It is generated from the same Org parser and
ordering rules as the site. Article bytes are read only to calculate their
hash; the inventory contains no article HTML or referenced files. Missing,
unsafe, or duplicate article paths cause a failure before output is written.
The inventory is data for offline planning, not permission to send its content
to an image API.

## Anonymous regression tests

```sh
emacs -Q --batch -L tools \
  -l tools/test/math-visual-build-test.el \
  -f ert-run-tests-batch-and-exit
```

Fixtures use synthetic article HTML and a local one-pixel PNG. They make no API
calls. Coverage includes Pick Up preservation and repeatability, refusal to
discard custom shell content, page/date/link preservation, approval and hash
binding, missing/stale assets, symlinks and traversal, malformed/duplicate
manifests, escaped alt text, and metadata-only inventory export.
