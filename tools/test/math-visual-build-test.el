;;; math-visual-build-test.el --- Tests for math-visual-build -*- lexical-binding: t; coding: utf-8 -*-

(require 'ert)
(require 'math-visual-build)

(defconst math-visual-build-test--sample-org
  "* サイト情報
:PROPERTIES:
:TITLE: 数学ビジュアル教材
:DESCRIPTION: 分野ごとに教材ページへ移動できます。
:END:
* 数I
:PROPERTIES:
:TEXTBOOK: 深進数学I
:END:

** ドモルガンの法則
:PROPERTIES:
:PATH: ./math-i/De-morgan-visualizer.html
:PAGE: 90
:APP: HTML
:PUBLISHED: 2026-04-15
:UPDATED: 2026-04-15
:END:
ベン図を用いて \\(A \\cup B\\) の関係を理解する教材。

* 数C

** 空間ベクトル分解
:PROPERTIES:
:PATH: ./math-c/space-vector-decomposition-with-reference.html
:TEXTBOOK: 深進数学C
:PAGE: 45
:APP: Three.js
:APP_URL: https://threejs.org/
:PUBLISHED: 2026-04-15
:UPDATED: 2026-04-15
:END:
ベクトル \\(\\vec{p}\\) を \\(s\\vec{a} + t\\vec{b} + u\\vec{c}\\) の合成として確認できる。
")

(ert-deftest math-visual-build-parse-org-file ()
  (let ((input-file (make-temp-file "math-visual" nil ".org" math-visual-build-test--sample-org)))
    (unwind-protect
        (let* ((site (math-visual-build--parse-org-file input-file))
               (sections (alist-get 'sections site))
               (first-item (car (alist-get 'items (car sections))))
               (second-item (car (alist-get 'items (cadr sections)))))
          (should (equal (alist-get 'title site) "数学ビジュアル教材"))
          (should (equal (alist-get 'description site) "分野ごとに教材ページへ移動できます。"))
          (should (= (length sections) 2))
          (should (equal (alist-get 'textbook first-item) "深進数学I"))
          (should (equal (alist-get 'description first-item) "ベン図を用いて \\(A \\cup B\\) の関係を理解する教材。"))
          (should (equal (alist-get 'app-url second-item) "https://threejs.org/")))
      (delete-file input-file))))

(ert-deftest math-visual-build-site-writes-html ()
  (let ((input-file (make-temp-file "math-visual" nil ".org" math-visual-build-test--sample-org))
        (output-file (make-temp-file "math-visual-out" nil ".html")))
    (unwind-protect
        (progn
          (math-visual-build-site input-file output-file)
          (with-temp-buffer
            (insert-file-contents output-file)
            (let ((html (buffer-string)))
              (should (string-match-p "<title>数学ビジュアル教材</title>" html))
              (should (string-match-p "window.MathJax" html))
              (should (string-match-p "href=\"\\./math-i/De-morgan-visualizer.html\"" html))
              (should (string-match-p "class=\"item-head\"" html))
              (should (string-match-p "深進数学C p\\.45" html))
              (should (string-match-p (regexp-quote "\\(\\vec{p}\\)") html))
              (should-not (string-match-p (regexp-quote "\\\\(\\\\vec{p}\\\\)") html))
              (should (string-match-p "<p class=\"item-meta-inline\"><a class=\"external-link\" href=\"https://threejs.org/\"" html)))))
      (delete-file input-file)
      (delete-file output-file))))

(defun math-visual-build-test--write (file content &optional literal)
  "Write synthetic CONTENT to FILE, optionally as LITERAL bytes."
  (make-directory (file-name-directory file) t)
  (with-temp-buffer
    (when literal (set-buffer-multibyte nil))
    (insert content)
    (let ((coding-system-for-write (if literal 'no-conversion 'utf-8-unix)))
      (write-region (point-min) (point-max) file nil 'silent))))

(defun math-visual-build-test--read (file)
  (with-temp-buffer (insert-file-contents file) (buffer-string)))

(defmacro math-visual-build-test--with-image-fixture (&rest body)
  "Run BODY with an anonymous, locally approved image fixture."
  (declare (indent 0) (debug t))
  `(let* ((root (make-temp-file "math-visual-image-test-" t))
          (source (expand-file-name "index.org" root))
          (target (expand-file-name "preview.html" root))
          (article (expand-file-name "math-i/De-morgan-visualizer.html" root))
          (second-article (expand-file-name "math-c/space-vector-decomposition-with-reference.html" root))
          (png (base64-decode-string
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a0x8AAAAASUVORK5CYII="))
          (sha (secure-hash 'sha256 png))
          (image-relative (concat "./images/entries/" sha ".png"))
          (image (expand-file-name image-relative root))
          (manifest (expand-file-name "images/entries/manifest.json" root))
          entry)
     (unwind-protect
         (progn
           (math-visual-build-test--write source math-visual-build-test--sample-org)
           (math-visual-build-test--write article
                                         "<html><p>Anonymous article.</p><!-- PRIVATE-NOTE-DO-NOT-EXPORT --></html>")
           (math-visual-build-test--write second-article "<html>Another anonymous article.</html>")
           (math-visual-build-test--write image png t)
           (setq entry `((article . "./math-i/De-morgan-visualizer.html")
                         (article_sha256 . ,(math-visual-build--file-sha256 article))
                         (image . ,image-relative)
                         (sha256 . ,sha)
                         (alt . "二つの円を用いた教材のイメージ")
                         (role . "entry-illustration")
                         (reviewed_at . "2026-11-14T00:00:00Z")
                         (review_id . ,(make-string 64 ?a))
                         (approved . t)))
           (math-visual-build-test--write-manifest manifest (list entry))
           ,@body)
       (delete-directory root t))))

(defun math-visual-build-test--write-manifest (manifest entries)
  (math-visual-build-test--write
   manifest
   (json-encode `((schema . "math-visual-entry-images/v1")
                  (images . ,(vconcat entries))))))

(ert-deftest math-visual-build-page-order-is-stable-and-does-not-change-dates ()
  (let* ((items '(((title . "unknown") (textbook . "book-a") (page . "未確認") (updated . "2000-01-01"))
                  ((title . "ten-first") (textbook . "book-a") (page . "10") (updated . "2001-01-01"))
                  ((title . "two") (textbook . "book-a") (page . "2") (updated . "2002-01-01"))
                  ((title . "ten-second") (textbook . "book-a") (page . "10") (updated . "2003-01-01"))
                  ((title . "other-book") (textbook . "book-b") (page . "1") (updated . "2004-01-01"))))
         (before (copy-tree items))
         (ordered (math-visual-build--page-order items)))
    (should (equal (mapcar (lambda (item) (alist-get 'title item)) ordered)
                   '("two" "ten-first" "ten-second" "unknown" "other-book")))
    (dolist (item ordered)
      (should (equal item (cl-find (alist-get 'title item) before
                                  :key (lambda (value) (alist-get 'title value)) :test #'equal))))))

(ert-deftest math-visual-build-approved-image-keeps-title-link-and-metadata ()
  (math-visual-build-test--with-image-fixture
    (math-visual-build-site source target)
    (let ((html (math-visual-build-test--read target)))
      (should (string-match-p "<figure class=\"entry-illustration\">" html))
      (should (string-match-p (regexp-quote image-relative) html))
      (should (string-match-p "教材をイメージしたイラスト" html))
      (should (string-match-p "<h3 class=\"item-title\"><a href=\"./math-i/De-morgan-visualizer.html\">" html))
      (should (string-match-p "2026-04-15（公開）・2026-04-15（更新）" html))
      (should (string-match-p "object-fit: contain" html)))))

(ert-deftest math-visual-build-missing-image-retains-article-link ()
  (math-visual-build-test--with-image-fixture
    (delete-file image)
    (math-visual-build-site source target)
    (let ((html (math-visual-build-test--read target)))
      (should-not (string-match-p "<figure class=\"entry-illustration\">" html))
      (should (string-match-p "href=\"./math-i/De-morgan-visualizer.html\"" html)))))

(ert-deftest math-visual-build-stale-article-omits-image ()
  (math-visual-build-test--with-image-fixture
    (math-visual-build-test--write article "<html>Changed article.</html>")
    (math-visual-build-site source target)
    (should-not (string-match-p "<figure class=\"entry-illustration\">"
                                (math-visual-build-test--read target)))))

(ert-deftest math-visual-build-tampered-image-omits-image ()
  (math-visual-build-test--with-image-fixture
    (math-visual-build-test--write image (concat png "changed") t)
    (math-visual-build-site source target)
    (should-not (string-match-p "<figure class=\"entry-illustration\">"
                                (math-visual-build-test--read target)))))

(ert-deftest math-visual-build-pending-and-wrong-article-are-not-guessed ()
  (math-visual-build-test--with-image-fixture
    (setf (alist-get 'approved entry) :json-false)
    (math-visual-build-test--write-manifest manifest (list entry))
    (math-visual-build-site source target)
    (should-not (string-match-p "<figure class=\"entry-illustration\">"
                                (math-visual-build-test--read target)))
    (setf (alist-get 'approved entry) t
          (alist-get 'article entry) "./math-c/space-vector-decomposition-with-reference.html")
    (math-visual-build-test--write-manifest manifest (list entry))
    (math-visual-build-site source target)
    (should-not (string-match-p "<figure class=\"entry-illustration\">"
                                (math-visual-build-test--read target)))))

(ert-deftest math-visual-build-duplicate-image-binding-is-rejected ()
  (math-visual-build-test--with-image-fixture
    (math-visual-build-test--write-manifest manifest (list entry entry entry))
    (math-visual-build-site source target)
    (should-not (string-match-p "<figure class=\"entry-illustration\">"
                                (math-visual-build-test--read target)))))

(ert-deftest math-visual-build-malformed-manifest-falls-back-without-leaking-contents ()
  (math-visual-build-test--with-image-fixture
    (math-visual-build-test--write manifest "not-json PRIVATE-MARKER")
    (math-visual-build-site source target)
    (let ((html (math-visual-build-test--read target)))
      (should-not (string-match-p "PRIVATE-MARKER" html))
      (should-not (string-match-p "<figure class=\"entry-illustration\">" html))
      (should (string-match-p "href=\"./math-i/De-morgan-visualizer.html\"" html)))))

(ert-deftest math-visual-build-image-alt-is-html-escaped ()
  (math-visual-build-test--with-image-fixture
    (setf (alist-get 'alt entry) "<img src=x onerror=\"alert(1)\"> & example")
    (math-visual-build-test--write-manifest manifest (list entry))
    (math-visual-build-site source target)
    (let ((html (math-visual-build-test--read target)))
      (should (string-match-p "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; example" html))
      (should-not (string-match-p "alt=\"<img" html)))))

(ert-deftest math-visual-build-safe-path-rejects-traversal-and-symlinks ()
  (math-visual-build-test--with-image-fixture
    (should-not (math-visual-build--safe-local-file root "./math-i/../math-i/De-morgan-visualizer.html" "html"))
    (should-not (math-visual-build--safe-local-file root "https://example.test/image.png" "png"))
    (should-not (math-visual-build--safe-local-file root "./math-i//De-morgan-visualizer.html" "html"))
    (make-symbolic-link (expand-file-name "math-i" root) (expand-file-name "alias" root))
    (should-not (math-visual-build--safe-local-file root "./alias/De-morgan-visualizer.html" "html"))
    (delete-file image)
    (make-symbolic-link article image)
    (math-visual-build-site source target)
    (should-not (string-match-p "<figure class=\"entry-illustration\">"
                                (math-visual-build-test--read target)))))

(ert-deftest math-visual-build-template-preserves-pick-up-and-is-idempotent ()
  (math-visual-build-test--with-image-fixture
    (let* ((shell (expand-file-name "index.html" root))
           (site (math-visual-build--parse-org-file source))
           (featured "    <section class=\"featured-section\" aria-label=\"注目教材\"><a href=\"./pick-up.html\">Pick Up unchanged</a></section>\n")
           (original (replace-regexp-in-string
                      "    </header>\n" (concat "    </header>\n" featured)
                      (math-visual-build--render-document site) t t)))
      (math-visual-build-test--write shell original)
      (math-visual-build-site source target)
      (let ((first (math-visual-build-test--read target)))
        (should (string-match-p (regexp-quote featured) first))
        (should (string-prefix-p (substring original 0 (string-match "    <section class=\"subject-section\">" original))
                                first))
        (math-visual-build-site source target target)
        (should (equal first (math-visual-build-test--read target)))))))

(ert-deftest math-visual-build-refuses-unknown-shell-before-writing ()
  (math-visual-build-test--with-image-fixture
    (let ((shell (expand-file-name "index.html" root)))
      (math-visual-build-test--write shell "<html>Private custom shell without owned sections</html>")
      (math-visual-build-test--write target "keep-preview")
      (should-error (math-visual-build-site source target))
      (should (equal "keep-preview" (math-visual-build-test--read target))))))

(ert-deftest math-visual-build-refuses-custom-content-between-subjects ()
  (math-visual-build-test--with-image-fixture
    (let* ((shell (expand-file-name "index.html" root))
           (html (math-visual-build--render-document (math-visual-build--parse-org-file source))))
      (math-visual-build-test--write
       shell (replace-regexp-in-string
              "    </section>\n    <section" "    </section>\n<p>Keep this custom content</p>\n    <section"
              html t t))
      (should-error (math-visual-build-site source target))
      (should-not (file-exists-p target)))))

(ert-deftest math-visual-build-inventory-is-public-metadata-and-hashes-only ()
  (math-visual-build-test--with-image-fixture
    (let ((inventory (expand-file-name "inventory.json" root)))
      (math-visual-build-image-inventory source inventory)
      (let* ((text (math-visual-build-test--read inventory))
             (data (json-parse-string text :object-type 'alist :array-type 'list))
             (first (car (alist-get 'articles data))))
        (should (equal (alist-get 'schema data) "math-visual-image-inventory/v1"))
        (should (= 2 (length (alist-get 'articles data))))
        (should (equal (alist-get 'article_sha256 first) (math-visual-build--file-sha256 article)))
        (should (equal (alist-get 'subject first) "数I"))
        (should (equal (alist-get 'published first) "2026-04-15"))
        (should-not (string-match-p "PRIVATE-NOTE-DO-NOT-EXPORT\\|Anonymous article" text))))))

(ert-deftest math-visual-build-inventory-refuses-unsafe-or-missing-source ()
  (math-visual-build-test--with-image-fixture
    (delete-file article)
    (let ((inventory (expand-file-name "inventory.json" root)))
      (should-error (math-visual-build-image-inventory source inventory))
      (should-not (file-exists-p inventory)))))

;;; math-visual-build-test.el ends here
