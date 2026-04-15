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

(defun math-visual-build-site (&optional input-file output-file)
  "Build OUTPUT-FILE from INPUT-FILE.

When called interactively, read the repository root `index.org' and
write the generated UTF-8 HTML to the repository root `index.html'."
  (interactive)
  (let* ((source (expand-file-name (or input-file math-visual-build-default-input-file)))
         (target (expand-file-name (or output-file math-visual-build-default-output-file)))
         (site (math-visual-build--parse-org-file source))
         (html (math-visual-build--render-document site)))
    (with-temp-file target
      (set-buffer-file-coding-system 'utf-8-unix)
      (insert html))
    (when (called-interactively-p 'interactive)
      (message "Generated %s from %s" target source))
    target))

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
      (items . ,(nreverse items)))))

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
   "  <style>\n"
   (math-visual-build--stylesheet) "\n"
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
     (math-visual-build--escape-html description)
     "</p>\n"
     "          <p class=\"item-meta-inline\">"
     meta-inline
     "</p>\n"
     "        </article>")))

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

(defun math-visual-build--present-string (value)
  "Return VALUE when it is a non-empty trimmed string."
  (let ((text (string-trim (or value ""))))
    (unless (string-empty-p text)
      text)))

(provide 'math-visual-build)

;;; math-visual-build.el ends here
