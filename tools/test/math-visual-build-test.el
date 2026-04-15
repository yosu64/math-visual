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
:PATH: ./数I/De-morgan-visualizer.html
:PAGE: 90
:APP: HTML
:PUBLISHED: 2026-04-15
:UPDATED: 2026-04-15
:END:
ベン図を用いて \\(A \\cup B\\) の関係を理解する教材。

* 数C

** 空間ベクトル分解
:PROPERTIES:
:PATH: ./数C/space-vector-decomposition-with-reference.html
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
              (should (string-match-p "href=\"\\./数I/De-morgan-visualizer.html\"" html))
              (should (string-match-p "class=\"item-head\"" html))
              (should (string-match-p "深進数学C p\\.45" html))
              (should (string-match-p (regexp-quote "\\(\\vec{p}\\)") html))
              (should-not (string-match-p (regexp-quote "\\\\(\\\\vec{p}\\\\)") html))
              (should (string-match-p "<p class=\"item-meta-inline\"><a class=\"external-link\" href=\"https://threejs.org/\"" html)))))
      (delete-file input-file)
      (delete-file output-file))))

;;; math-visual-build-test.el ends here
