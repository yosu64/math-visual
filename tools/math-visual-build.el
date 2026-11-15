;;; math-visual-build.el --- Build index.html from index.org -*- lexical-binding: t; coding: utf-8 -*-

;; Copyright (C)

;; Author: Codex
;; Keywords: hypermedia, outlines
;; Package-Requires: ((emacs "28.1"))

;;; Commentary:

;; Build the repository root index.html from index.org.
;; The parser relies on Org's syntax tree rather than ad-hoc regexes.

;;; Code:

(require 'cl-lib)
(require 'org)
(require 'org-element)
(require 'subr-x)
(require 'json)

(defconst math-visual-build--repo-root
  (file-name-directory (directory-file-name
                        (or (file-name-directory (or load-file-name buffer-file-name))
                            default-directory)))
  "Repository root directory.")

(defconst math-visual-build-default-input-file
  (expand-file-name "index.org" math-visual-build--repo-root)
  "Default Org sitemap file.")

(defconst math-visual-build-default-output-file
  (expand-file-name "index.html" math-visual-build--repo-root)
  "Default generated HTML file.")

(defun math-visual-build-site (&optional input-file output-file template-file)
  "Build OUTPUT-FILE from INPUT-FILE, preserving TEMPLATE-FILE's shell.

When called interactively, read the repository root `index.org' and
write the generated UTF-8 HTML to the repository root `index.html'.
By default use index.html beside INPUT-FILE as the template, when it
exists.  Only the contiguous subject sections and managed image CSS are
replaced; Pick Up and other surrounding content remain byte-for-byte.
A malformed existing template is an error, never a reason to discard it.
For a new site with no template, render a complete document."
  (interactive)
  (let* ((source (expand-file-name (or input-file math-visual-build-default-input-file)))
         (target (expand-file-name (or output-file math-visual-build-default-output-file)))
         (root (file-name-directory source))
         (existing (expand-file-name "index.html" root))
         (template (or template-file (when (file-exists-p existing) existing)))
         (site (math-visual-build--parse-org-file source))
         (_ (math-visual-build--attach-approved-images site root))
         (html (if template
                   (math-visual-build--render-into-template site template)
                 (math-visual-build--render-document site))))
    (with-temp-file target
      (set-buffer-file-coding-system 'utf-8-unix)
      (insert html))
    (when (called-interactively-p 'interactive)
      (message "Generated %s from %s" target source))
    target))

(defun math-visual-build-image-inventory (input-file output-file)
  "Write public article metadata from INPUT-FILE to OUTPUT-FILE as JSON.

The same Org AST and page order are used by the site builder.  No article
HTML, teacher notes, textbook images, or private reference files are
included.  Article bytes are read only to bind each record to its SHA-256.
Unsafe, missing, or duplicate article paths cause an error before writing."
  (let* ((source (expand-file-name input-file))
         (root (file-name-directory source))
         (site (math-visual-build--parse-org-file source))
         (seen (make-hash-table :test 'equal))
         articles)
    (dolist (section (alist-get 'sections site))
      (dolist (item (alist-get 'items section))
        (let* ((path (alist-get 'path item))
               (file (math-visual-build--safe-local-file root path "html")))
          (unless (and file (not (gethash path seen)))
            (error "Image inventory requires unique, existing local article paths"))
          (puthash path t seen)
          (push `((path . ,path)
                  (title . ,(alist-get 'title item))
                  (description . ,(alist-get 'description item))
                  (subject . ,(alist-get 'title section))
                  (textbook . ,(alist-get 'textbook item))
                  (page . ,(alist-get 'page item))
                  (published . ,(alist-get 'published item))
                  (updated . ,(alist-get 'updated item))
                  (article_sha256 . ,(math-visual-build--file-sha256 file)))
                articles))))
    (let ((json-encoding-pretty-print t))
      (with-temp-file output-file
        (set-buffer-file-coding-system 'utf-8-unix)
        (insert (json-encode
                 `((schema . "math-visual-image-inventory/v1")
                   (articles . ,(vconcat (nreverse articles))))))
        (insert "\n")))
    output-file))

(defun math-visual-build--file-sha256 (file)
  "Return SHA-256 of FILE's literal bytes."
  (with-temp-buffer
    (set-buffer-multibyte nil)
    (insert-file-contents-literally file)
    (secure-hash 'sha256 (current-buffer))))

(defun math-visual-build--safe-local-file (root relative extension)
  "Return an existing regular file below ROOT, or nil.
RELATIVE must be a ./ path ending in EXTENSION.  Reject symlink components,
remote paths, traversal, URL parameters and ambiguous empty path segments."
  (when (and (stringp relative)
             (string-match-p
              (concat "\\`\\./[A-Za-z0-9_./-]+\\."
                      (regexp-quote extension) "\\'") relative))
    (let* ((parts (split-string (substring relative 2) "/"))
           (base (file-name-as-directory (expand-file-name root)))
           (path base)
           (safe (not (file-remote-p base))))
      (dolist (part parts)
        (when (member part '("" "." "..")) (setq safe nil))
        (setq path (expand-file-name part (file-name-as-directory path)))
        (when (file-symlink-p path) (setq safe nil)))
      (when (and safe (file-regular-p path) (file-readable-p path)
                 (file-in-directory-p path base))
        path))))

(defun math-visual-build--sha256-p (value)
  "Whether VALUE is a lowercase hexadecimal SHA-256 digest."
  (and (stringp value) (string-match-p "\\`[0-9a-f]\\{64\\}\\'" value)))

(defun math-visual-build--png-p (file)
  "Check FILE's PNG signature and first chunk without decoding the image."
  (with-temp-buffer
    (set-buffer-multibyte nil)
    (insert-file-contents-literally file nil 0 24)
    (let ((data (buffer-string)))
      (and (= (length data) 24)
           (equal (substring data 0 8) (unibyte-string 137 80 78 71 13 10 26 10))
           (equal (substring data 12 16) "IHDR")))))

(defun math-visual-build--valid-image-entry-p (entry root)
  "Whether ENTRY is approved and still bound to its local article and PNG."
  (let* ((article (alist-get 'article entry))
         (article-file (math-visual-build--safe-local-file root article "html"))
         (image (alist-get 'image entry))
         (sha (alist-get 'sha256 entry))
         (image-file (and (math-visual-build--sha256-p sha)
                          (equal image (concat "./images/entries/" sha ".png"))
                          (math-visual-build--safe-local-file root image "png")))
         (alt (alist-get 'alt entry)))
    (and (eq (alist-get 'approved entry) t)
         (equal (alist-get 'role entry) "entry-illustration")
         (math-visual-build--sha256-p (alist-get 'review_id entry))
         (stringp (alist-get 'reviewed_at entry))
         (string-match-p "\\`[0-9]\\{4\\}-[0-9]\\{2\\}-[0-9]\\{2\\}T"
                         (alist-get 'reviewed_at entry))
         (stringp alt) (not (string-empty-p (string-trim alt)))
         (<= (length alt) 300)
         article-file image-file
         (equal (alist-get 'article_sha256 entry)
                (math-visual-build--file-sha256 article-file))
         (equal sha (math-visual-build--file-sha256 image-file))
         (math-visual-build--png-p image-file))))

(defun math-visual-build--attach-approved-images (site root)
  "Attach only verified approved images to SITE.  Absence is normal.
Malformed, duplicated, stale or missing assets never prevent article links
from rendering.  A generic warning does not echo manifest contents."
  (let ((manifest (math-visual-build--safe-local-file
                   root "./images/entries/manifest.json" "json"))
        (images (make-hash-table :test 'equal))
        (seen (make-hash-table :test 'equal))
        rejected)
    (when manifest
      (condition-case nil
          (let* ((size (file-attribute-size (file-attributes manifest)))
                 (data (when (<= size 1048576)
                         (with-temp-buffer
                           (insert-file-contents manifest)
                           (json-parse-buffer :object-type 'alist :array-type 'list
                                              :null-object nil :false-object :json-false))))
                 (entries (alist-get 'images data)))
            (unless (and (equal (alist-get 'schema data) "math-visual-entry-images/v1")
                         (listp entries) (<= (length entries) 500))
              (error "Invalid image manifest"))
            (dolist (entry entries)
              (let ((path (alist-get 'article entry)))
                (cond
                 ((gethash path seen)
                  (remhash path images)
                  (setq rejected t))
                 ((math-visual-build--valid-image-entry-p entry root)
                  (puthash path entry images))
                 (t (setq rejected t)))
                (puthash path t seen))))
        (error (clrhash images) (setq rejected t))))
    (when rejected (message "Some entry images were omitted: approval or asset validation failed"))
    (dolist (section (alist-get 'sections site))
      (dolist (item (alist-get 'items section))
        (let ((value (gethash (alist-get 'path item) images))
              (cell (assq 'entry-image item)))
          (if cell
              (setcdr cell value)
            (nconc item (list (cons 'entry-image value)))))))
    site))

(defun math-visual-build--render-into-template (site template-file)
  "Update SITE's subject sections in TEMPLATE-FILE without losing its shell."
  (with-temp-buffer
    (insert-file-contents template-file)
    (let* ((html (buffer-string))
           (opening "    <section class=\"subject-section\">\n")
           (closing "\n    </section>")
           (cursor 0)
           start finish ranges)
      (while (string-match (regexp-quote opening) html cursor)
        (let ((begin (match-beginning 0)) (content-begin (match-end 0)))
          (unless (string-match (regexp-quote closing) html content-begin)
            (error "Existing index template has an unfinished subject section"))
          (setq finish (match-end 0))
          (let ((body (substring html content-begin (match-beginning 0))))
            (when (string-match-p "</?section\\b" body)
              (error "Existing index template has ambiguous nested sections")))
          (push (cons begin finish) ranges)
          (setq cursor finish)))
      (setq ranges (nreverse ranges))
      (unless (and ranges
                   (= (1- (length (split-string
                                   html (regexp-quote "class=\"subject-section\""))))
                      (length ranges)))
        (error "Existing index template does not have the expected subject sections"))
      (setq start (caar ranges) finish (cdar ranges))
      (dolist (range (cdr ranges))
        (unless (string-empty-p (string-trim (substring html finish (car range))))
          (error "Custom content between subject sections must be preserved explicitly"))
        (setq finish (cdr range)))
      (setq html (concat (substring html 0 start)
                         (mapconcat #'math-visual-build--render-section
                                    (alist-get 'sections site) "\n")
                         (substring html finish)))
      (math-visual-build--insert-image-css html))))

(defun math-visual-build--insert-image-css (html)
  "Insert or replace only the managed entry-image CSS block in HTML."
  (let* ((start-marker "/* math-visual-entry-images:start */")
         (end-marker "/* math-visual-entry-images:end */")
         (css (math-visual-build--image-stylesheet))
         (start (string-match (regexp-quote start-marker) html))
         (end (string-match (regexp-quote end-marker) html)))
    (cond
     ((or start end)
      (unless (and start end (< start end)
                   (not (string-match (regexp-quote start-marker) html (1+ start)))
                   (not (string-match (regexp-quote end-marker) html (1+ end))))
        (error "Existing entry image CSS markers are malformed"))
      (concat (substring html 0 start) css
              (substring html (+ end (length end-marker)))))
     ((string-match "</style>" html)
      (let ((position (match-beginning 0)))
        (when (string-match "</style>" html (match-end 0))
          (error "Existing index template has multiple style blocks"))
        (concat (substring html 0 position) css "\n  " (substring html position))))
     (t (error "Existing index template has no style block")))))

(defun math-visual-build--image-stylesheet ()
  "CSS for optional illustration links, with no crop or required JavaScript."
  (string-join
   '("/* math-visual-entry-images:start */"
     ".entry-illustration { margin: 0 0 14px; }"
     ".entry-image-link { display: block; border-radius: 12px; }"
     ".entry-image-link:focus-visible { outline: 3px solid var(--accent); outline-offset: 4px; }"
     ".entry-image { display: block; width: 100%; aspect-ratio: 3 / 2; object-fit: contain; background: #fff; border: 1px solid var(--line); border-radius: 12px; }"
     ".entry-illustration figcaption { margin-top: 5px; font-size: 0.75rem; color: var(--muted); }"
     "/* math-visual-entry-images:end */")
   "\n"))

(defun math-visual-build--parse-org-file (file)
  "Parse FILE and return an alist representing the site."
  (with-temp-buffer
    (insert-file-contents file)
    (delay-mode-hooks (org-mode))
    (let ((ast (org-element-parse-buffer)))
      (math-visual-build--extract-site ast))))

(defun math-visual-build--extract-site (ast)
  "Extract site metadata and sections from Org AST."
  (let (site-info sections)
    (org-element-map ast 'headline
      (lambda (headline)
        (when (= (org-element-property :level headline) 1)
          (let ((title (org-element-property :raw-value headline)))
            (if (string= title "サイト情報")
                (setq site-info (math-visual-build--extract-site-info headline))
              (push (math-visual-build--extract-section headline) sections)))))
      nil nil 'headline)
    `((title . ,(alist-get 'title site-info nil nil #'equal))
      (description . ,(alist-get 'description site-info nil nil #'equal))
      (sections . ,(nreverse sections)))))

(defun math-visual-build--extract-site-info (headline)
  "Extract site metadata from HEADLINE."
  `((title . ,(math-visual-build--headline-property headline "TITLE"))
    (description . ,(math-visual-build--headline-property headline "DESCRIPTION"))))

(defun math-visual-build--extract-section (headline)
  "Extract a textbook section from level-1 HEADLINE."
  (let (items)
    (org-element-map (org-element-contents headline) 'headline
      (lambda (child)
        (when (= (org-element-property :level child) 2)
          (push (math-visual-build--extract-item child headline) items)))
      nil nil 'headline)
    `((title . ,(org-element-property :raw-value headline))
      (textbook . ,(math-visual-build--headline-property headline "TEXTBOOK"))
      (items . ,(math-visual-build--page-order (nreverse items))))))

(defun math-visual-build--page-order (items)
  "Order ITEMS by confirmed numeric pages within each textbook.
Keep textbook groups in first-seen order and preserve existing order for
equal or unknown pages.  Unknown pages follow confirmed pages.  This only
orders the rendered view; it does not rewrite Org or teaching dates."
  (let ((groups (make-hash-table :test 'equal)) books result)
    (dolist (item items)
      (let ((book (alist-get 'textbook item)))
        (unless (gethash book groups) (push book books))
        (puthash book (append (gethash book groups) (list item)) groups)))
    (dolist (book (nreverse books))
      (setq result
            (append result
                    (cl-stable-sort
                     (gethash book groups)
                     (lambda (a b)
                       (let ((ap (math-visual-build--numeric-page (alist-get 'page a)))
                             (bp (math-visual-build--numeric-page (alist-get 'page b))))
                         (and ap (or (not bp) (< ap bp)))))))))
    result))

(defun math-visual-build--numeric-page (page)
  "Return a numeric PAGE only when its entire value is confirmed digits."
  (when (and (stringp page) (string-match-p "\\`[0-9]+\\'" page))
    (string-to-number page)))

(defun math-visual-build--extract-item (headline parent-headline)
  "Extract a material card from HEADLINE under PARENT-HEADLINE."
  (let* ((item-textbook (math-visual-build--headline-property headline "TEXTBOOK"))
         (section-textbook (math-visual-build--headline-property parent-headline "TEXTBOOK")))
    `((title . ,(org-element-property :raw-value headline))
      (description . ,(math-visual-build--headline-description headline))
      (path . ,(math-visual-build--headline-property headline "PATH"))
      (textbook . ,(if (string-empty-p item-textbook) section-textbook item-textbook))
      (page . ,(math-visual-build--headline-property headline "PAGE"))
      (app . ,(math-visual-build--headline-property headline "APP"))
      (app-url . ,(math-visual-build--headline-property headline "APP_URL"))
      (published . ,(math-visual-build--headline-property headline "PUBLISHED"))
      (updated . ,(math-visual-build--headline-property headline "UPDATED")))))

(defun math-visual-build--headline-property (headline property)
  "Return HEADLINE PROPERTY as a trimmed string, or an empty string."
  (string-trim (or (org-element-property (intern (concat ":" property)) headline) "")))

(defun math-visual-build--headline-description (headline)
  "Return trimmed body text directly under HEADLINE."
  (let ((section (org-element-map headline 'section #'identity nil t)))
    (if section
        (string-join
         (delq nil
               (mapcar #'math-visual-build--extract-description-fragment
                       (org-element-contents section)))
         "\n\n")
      "")))

(defun math-visual-build--extract-description-fragment (element)
  "Extract description text from ELEMENT when it is displayable prose."
  (when (memq (org-element-type element)
              '(paragraph plain-list fixed-width example-block src-block verse-block))
    (string-trim
     (buffer-substring-no-properties
      (org-element-property :begin element)
      (org-element-property :end element)))))

(defun math-visual-build--render-document (site)
  "Render SITE alist into a full HTML document string."
  (concat
   "<!DOCTYPE html>\n"
   "<html lang=\"ja\">\n"
   "<head>\n"
   "  <meta charset=\"UTF-8\">\n"
   "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
   "  <title>" (math-visual-build--escape-html (or (alist-get 'title site) "")) "</title>\n"
   "  <script>\n"
   "    window.MathJax = {\n"
   "      tex: {\n"
   "        inlineMath: [['\\\\(', '\\\\)'], ['$', '$']]\n"
   "      },\n"
   "      svg: {\n"
   "        fontCache: 'global'\n"
   "      }\n"
   "    };\n"
   "  </script>\n"
   "  <script defer src=\"https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js\"></script>\n"
   "  <style>\n"
   (math-visual-build--stylesheet) "\n"
   (math-visual-build--image-stylesheet) "\n"
   "  </style>\n"
   "</head>\n"
   "<body>\n"
   "  <main class=\"page\">\n"
   "    <header class=\"hero\">\n"
   "      <p class=\"eyebrow\">Math Visual</p>\n"
   "      <h1>" (math-visual-build--escape-html (or (alist-get 'title site) "")) "</h1>\n"
   "      <p class=\"lead\">" (math-visual-build--escape-html (or (alist-get 'description site) "")) "</p>\n"
   "    </header>\n"
   (mapconcat #'math-visual-build--render-section (alist-get 'sections site) "\n")
   "\n  </main>\n"
   "</body>\n"
   "</html>\n"))

(defun math-visual-build--render-section (section)
  "Render SECTION to HTML."
  (concat
   "    <section class=\"subject-section\">\n"
   "      <div class=\"section-header\">\n"
   "        <h2>" (math-visual-build--escape-html (or (alist-get 'title section) "")) "</h2>\n"
   "      </div>\n"
   "      <div class=\"card-grid\">\n"
   (if-let ((items (alist-get 'items section)))
       (mapconcat #'math-visual-build--render-item items "\n")
     "        <p class=\"empty\">教材はまだありません。</p>")
   "\n      </div>\n"
   "    </section>"))

(defun math-visual-build--render-item (item)
  "Render ITEM to HTML."
  (let* ((title (or (alist-get 'title item) ""))
         (path (alist-get 'path item))
         (description (or (alist-get 'description item) ""))
         (app (or (alist-get 'app item) ""))
         (app-url (alist-get 'app-url item))
         (book-page (math-visual-build--render-book-page item))
         (meta-inline (math-visual-build--render-meta-inline app app-url
                                                             (alist-get 'published item)
                                                             (alist-get 'updated item))))
    (concat
     "        <article class=\"material-card\">\n"
     (math-visual-build--render-entry-image item)
     "          <div class=\"item-head\">\n"
     "            <h3 class=\"item-title\">"
     (if (math-visual-build--present-string path)
         (concat "<a href=\""
                 (math-visual-build--escape-attribute path)
                 "\">"
                 (math-visual-build--escape-html title)
                 "</a>")
       (math-visual-build--escape-html title))
     "</h3>\n"
     "            <p class=\"item-book-page\">"
     (math-visual-build--escape-html book-page)
     "</p>\n"
     "          </div>\n"
     "          <p class=\"item-description\">"
     (math-visual-build--escape-description-html description)
     "</p>\n"
     "          <p class=\"item-meta-inline\">"
     meta-inline
     "</p>\n"
     "        </article>")))

(defun math-visual-build--render-entry-image (item)
  "Render ITEM's verified optional illustration, keeping its text link."
  (if-let ((entry (alist-get 'entry-image item)))
      (concat
       "          <figure class=\"entry-illustration\">\n"
       "            <a class=\"entry-image-link\" href=\""
       (math-visual-build--escape-attribute (alist-get 'path item))
       "\" aria-label=\""
       (math-visual-build--escape-attribute (concat (alist-get 'title item) "を開く"))
       "\">\n"
       "              <img class=\"entry-image\" src=\""
       (math-visual-build--escape-attribute (alist-get 'image entry))
       "\" alt=\"" (math-visual-build--escape-attribute (alist-get 'alt entry))
       "\" loading=\"lazy\" decoding=\"async\">\n"
       "            </a>\n"
       "            <figcaption>教材をイメージしたイラスト</figcaption>\n"
       "          </figure>\n")
    ""))

(defun math-visual-build--render-book-page (item)
  "Render textbook and page summary for ITEM."
  (let ((parts nil))
    (when-let ((textbook (math-visual-build--present-string (alist-get 'textbook item))))
      (push textbook parts))
    (when-let ((page (math-visual-build--present-string (alist-get 'page item))))
      (push (concat "p." page) parts))
    (if parts
        (string-join (nreverse parts) " ")
      "")))

(defun math-visual-build--render-meta-inline (app app-url published updated)
  "Render compact inline metadata."
  (let* ((app-fragment (math-visual-build--render-app-fragment app app-url))
         (published-fragment
          (when-let ((published-text (math-visual-build--present-string published)))
            (math-visual-build--escape-html (concat published-text "（公開）"))))
         (updated-fragment
          (when-let ((updated-text (math-visual-build--present-string updated)))
            (math-visual-build--escape-html (concat updated-text "（更新）"))))
         (date-fragment
          (mapconcat #'identity
                     (delq nil (list published-fragment updated-fragment))
                     "・")))
    (mapconcat #'identity
               (delq nil (list app-fragment
                               (unless (string-empty-p date-fragment)
                                 date-fragment)))
               " / ")))

(defun math-visual-build--render-app-fragment (app app-url)
  "Render APP as plain text or a linked fragment."
  (when-let ((label (math-visual-build--present-string app)))
    (if (math-visual-build--present-string app-url)
        (concat "<a class=\"external-link\" href=\""
                (math-visual-build--escape-attribute app-url)
                "\" target=\"_blank\" rel=\"noopener noreferrer\">"
                (math-visual-build--escape-html label)
                "</a>")
      (math-visual-build--escape-html label))))

(defun math-visual-build--stylesheet ()
  "Return embedded CSS."
  (mapconcat
   #'identity
   '(":root {"
     "  color-scheme: light;"
     "  --bg: #f4f1ea;"
     "  --panel: #fffdf8;"
     "  --panel-alt: #f8f5ee;"
     "  --text: #222222;"
     "  --muted: #5f5a4f;"
     "  --line: #d9d1c2;"
     "  --accent: #0e7490;"
     "  --accent-strong: #155e75;"
     "  --shadow: 0 18px 45px rgba(34, 34, 34, 0.08);"
     "}"
     "* {"
     "  box-sizing: border-box;"
     "}"
     "html {"
     "  background:"
     "    radial-gradient(circle at top, rgba(14, 116, 144, 0.08), transparent 32%),"
     "    linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);"
     "}"
     "body {"
     "  margin: 0;"
     "  color: var(--text);"
     "  font-family: \"Hiragino Sans\", \"Yu Gothic\", sans-serif;"
     "  line-height: 1.7;"
     "}"
     "a {"
     "  color: var(--accent-strong);"
     "  text-decoration: none;"
     "}"
     "a:hover {"
     "  text-decoration: underline;"
     "}"
     ".page {"
     "  width: min(1120px, calc(100% - 32px));"
     "  margin: 0 auto;"
     "  padding: 40px 0 72px;"
     "}"
     ".hero {"
     "  padding: 28px 28px 8px;"
     "}"
     ".eyebrow {"
     "  margin: 0 0 10px;"
     "  color: var(--accent-strong);"
     "  font-size: 0.82rem;"
     "  font-weight: 700;"
     "  letter-spacing: 0.08em;"
     "  text-transform: uppercase;"
     "}"
     ".hero h1 {"
     "  margin: 0;"
     "  font-size: clamp(2rem, 5vw, 3.4rem);"
     "  line-height: 1.15;"
     "}"
     ".lead {"
     "  max-width: 720px;"
     "  margin: 16px 0 0;"
     "  color: var(--muted);"
     "  font-size: 1.02rem;"
     "}"
     ".subject-section {"
     "  margin-top: 28px;"
     "  padding: 28px;"
     "  background: rgba(255, 253, 248, 0.86);"
     "  border: 1px solid var(--line);"
     "  border-radius: 28px;"
     "  box-shadow: var(--shadow);"
     "  backdrop-filter: blur(12px);"
     "}"
     ".section-header {"
     "  margin-bottom: 20px;"
     "}"
     ".section-header h2 {"
     "  margin: 0;"
     "  font-size: clamp(1.4rem, 3.2vw, 2rem);"
     "}"
     ".section-textbook {"
     "  margin: 8px 0 0;"
     "  color: var(--muted);"
     "}"
     ".card-grid {"
     "  display: grid;"
     "  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));"
     "  gap: 18px;"
     "}"
     ".material-card {"
     "  min-width: 0;"
     "  padding: 18px 18px 16px;"
     "  background: linear-gradient(180deg, var(--panel) 0%, var(--panel-alt) 100%);"
     "  border: 1px solid var(--line);"
     "  border-radius: 22px;"
     "  line-height: 1.58;"
     "}"
     ".item-head {"
     "  display: flex;"
     "  justify-content: space-between;"
     "  align-items: baseline;"
     "  gap: 12px 18px;"
     "}"
     ".item-title {"
     "  margin: 0;"
     "  font-size: 1.15rem;"
     "  line-height: 1.32;"
     "}"
     ".item-book-page {"
     "  margin: 0;"
     "  flex: 0 0 auto;"
     "  color: var(--muted);"
     "  font-size: 0.95rem;"
     "  white-space: nowrap;"
     "}"
     ".item-description {"
     "  margin: 10px 0 8px;"
     "  color: var(--muted);"
     "  white-space: pre-line;"
     "  line-height: 1.62;"
     "}"
     ".item-meta-inline {"
     "  margin: 0;"
     "  padding-top: 8px;"
     "  border-top: 1px solid rgba(217, 209, 194, 0.8);"
     "  color: var(--muted);"
     "  font-size: 0.92rem;"
     "  line-height: 1.5;"
     "}"
     ".external-link {"
     "  font-size: inherit;"
     "}"
     ".empty {"
     "  margin: 0;"
     "  color: var(--muted);"
     "}"
     "@media (max-width: 640px) {"
     "  .page {"
     "    width: min(100%, calc(100% - 20px));"
     "    padding-top: 20px;"
     "  }"
     "  .hero {"
     "    padding: 18px 12px 2px;"
     "  }"
     "  .subject-section {"
     "    padding: 18px;"
     "    border-radius: 22px;"
     "  }"
     "  .material-card {"
     "    padding: 18px;"
     "    border-radius: 18px;"
     "  }"
     "  .item-head {"
     "    flex-direction: column;"
     "    align-items: flex-start;"
     "    gap: 4px;"
     "  }"
     "  .item-book-page {"
     "    white-space: normal;"
     "  }"
     "}")
   "\n"))

(defun math-visual-build--escape-html (value)
  "Escape VALUE for HTML text nodes."
  (setq value (or value ""))
  (setq value (replace-regexp-in-string "&" "&amp;" value t t))
  (setq value (replace-regexp-in-string "<" "&lt;" value t t))
  (setq value (replace-regexp-in-string ">" "&gt;" value t t))
  (setq value (replace-regexp-in-string "\"" "&quot;" value t t))
  value)

(defun math-visual-build--escape-attribute (value)
  "Escape VALUE for HTML attribute usage."
  (math-visual-build--escape-html value))

(defun math-visual-build--escape-description-html (value)
  "Escape VALUE for HTML while preserving MathJax inline math delimiters."
  (let ((placeholders nil)
        (index 0)
        (cursor 0)
        (text (math-visual-build--normalize-math-fragment (or value ""))))
    (while (string-match "\\\\(" text cursor)
      (let ((start (match-beginning 0)))
        (if (string-match "\\\\)" text (match-end 0))
            (let* ((end (match-end 0))
                   (math-fragment (substring text start end))
                   (placeholder (format "@@MATHJAX-%d@@" index)))
              (push (cons placeholder math-fragment) placeholders)
              (setq text (concat (substring text 0 start)
                                 placeholder
                                 (substring text end)))
              (setq cursor (+ start (length placeholder)))
              (setq index (1+ index)))
          (setq cursor (match-end 0)))))
    (setq text (math-visual-build--escape-html text))
    (dolist (entry placeholders text)
      (setq text (replace-regexp-in-string
                  (regexp-quote (car entry))
                  (cdr entry)
                  text t t)))))

(defun math-visual-build--normalize-math-fragment (value)
  "Normalize LaTeX escapes in VALUE for MathJax output.

This converts doubled backslashes such as `\\\\(' and `\\\\vec' to the
single-backslash form MathJax expects in static HTML."
  (replace-regexp-in-string "\\\\\\\\" "\\" value t t))

(defun math-visual-build--present-string (value)
  "Return VALUE when it is a non-empty trimmed string."
  (let ((text (string-trim (or value ""))))
    (unless (string-empty-p text)
      text)))

(provide 'math-visual-build)

;;; math-visual-build.el ends here
