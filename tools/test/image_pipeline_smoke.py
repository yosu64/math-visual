#!/usr/bin/env python3
"""Run the complete image workflow with real Emacs and synthetic offline inputs.

The only subprocess allowed is the selected Emacs loading the copied product
builder. Every repository write, image adoption and simulated human decision is
confined to a new temporary fixture. No API, key lookup or publication occurs.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import ExitStack
import datetime as dt
import hashlib
from html.parser import HTMLParser
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from unittest import mock

from PIL import Image, PngImagePlugin


PRODUCT_FILES = ("tools/image_pipeline.py", "tools/imagegen.py", "tools/math-visual-build.el")
ARTICLE = "./math-i/earlier.html"
OTHER_ARTICLE = "./math-i/later.html"
TEACHER_SENTINEL = "ANONYMOUS_PRIVATE_TEACHER_SENTINEL"
TEXTBOOK_SENTINEL = "ANONYMOUS_PRIVATE_TEXTBOOK_SENTINEL"
FAKE_KEY = "sk-" + "anonymous-smoke-fixture-" + "0" * 24
PROJECT = "proj_anonymous_smoke_fixture"
FEATURED = '''    <section class="featured-section" aria-label="Anonymous Pick Up">
      <a class="featured-card" href="./math-i/later.html">Pick Up — anonymous unchanged feature</a>
    </section>'''
SHELL = '''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Anonymous entrance</title>
<style>
body { color: #243438; }
</style></head><body><main class="page">
<header class="hero"><h1>Anonymous entrance</h1></header>
''' + FEATURED + '''
    <section class="subject-section">
      <p>Owned subject placeholder.</p>
    </section>
</main></body></html>
'''
ORG = '''* サイト情報
:PROPERTIES:
:TITLE: Anonymous entrance
:DESCRIPTION: Anonymous public article list.
:END:
* Anonymous subject
:PROPERTIES:
:TEXTBOOK: Anonymous book
:END:
** Anonymous later
:PROPERTIES:
:PATH: ./math-i/later.html
:PAGE: 20
:APP: HTML
:PUBLISHED: 2001-02-01
:UPDATED: 2001-02-02
:TEACHER_NOTE: ANONYMOUS_PRIVATE_TEACHER_SENTINEL
:TEXTBOOK_REFERENCE: ../private-sources/textbook.png
:END:
A different public mathematical theme.
** Anonymous earlier
:PROPERTIES:
:PATH: ./math-i/earlier.html
:PAGE: 10
:APP: HTML
:PUBLISHED: 2001-01-01
:UPDATED: 2001-01-02
:END:
An anonymous public mathematical theme.
'''


class SmokeError(Exception):
    pass


def check(condition, code):
    if not condition:
        raise SmokeError(code)


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def png_bytes(*, comment=None):
    output = io.BytesIO()
    image = Image.new("RGB", (1536, 1024), (30, 100, 110))
    metadata = PngImagePlugin.PngInfo()
    if comment:
        metadata.add_text("Comment", comment)
    image.save(output, format="PNG", pnginfo=metadata)
    return output.getvalue()


class Cards(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.cards = []
        self.card = None
        self.field = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "article" and "material-card" in classes:
            check(self.card is None, "nested_fixture_card")
            self.card = {"href": None, "title": "", "page": "", "dates": "", "images": []}
        if self.card is None:
            return
        if tag == "h3" and "item-title" in classes:
            self.field = "title"
        elif tag == "p" and "item-book-page" in classes:
            self.field = "page"
        elif tag == "p" and "item-meta-inline" in classes:
            self.field = "dates"
        elif tag == "a" and self.field == "title":
            self.card["href"] = attrs.get("href")
        elif tag == "img" and "entry-image" in classes:
            self.card["images"].append(attrs)

    def handle_data(self, data):
        if self.card is not None and self.field:
            self.card[self.field] += data

    def handle_endtag(self, tag):
        if tag in ("h3", "p"):
            self.field = None
        if tag == "article" and self.card is not None:
            self.cards.append(self.card)
            self.card = None
            self.field = None

    def signature(self):
        return [{k: value[k] for k in ("href", "title", "page", "dates")} for value in self.cards]


def import_product(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    check(spec is not None and spec.loader is not None, "product_import")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def resolve_emacs(value):
    executable = shutil.which(value)
    if executable is None and Path(value).is_file():
        executable = value
    check(executable is not None, "emacs_required")
    result = Path(executable).expanduser().resolve()
    check(result.is_file() and os.access(result, os.X_OK), "emacs_required")
    return str(result)


def smoke(emacs):
    source_repo = Path(__file__).resolve().parents[2]
    snapshot = {name: (source_repo / name).read_bytes() for name in PRODUCT_FILES}
    source_hashes = {name: hash_bytes(data) for name, data in snapshot.items()}
    real_run = subprocess.run
    saved_modules = {name: sys.modules.get(name) for name in ("image_pipeline", "imagegen")}
    try:
        with tempfile.TemporaryDirectory(prefix="anonymous-image-smoke-") as temporary:
            # macOS /var is a symlink; use a physical temp root for ordinary fixtures.
            base = Path(temporary).resolve()
            repo = base / "anonymous-repository"
            (repo / "tools/imagegen-config").mkdir(parents=True)
            (repo / "math-i").mkdir()
            (repo / ".git").mkdir()
            for name, data in snapshot.items():
                (repo / name).write_bytes(data)
                check(hash_bytes((repo / name).read_bytes()) == source_hashes[name], "copied_source_hash")
            (repo / "index.org").write_text(ORG, encoding="utf-8")
            (repo / "index.html").write_text(SHELL, encoding="utf-8")
            (repo / ARTICLE).write_text("<html><h1>Anonymous earlier</h1><p>Public theme A.</p></html>", encoding="utf-8")
            (repo / OTHER_ARTICLE).write_text("<html><h1>Anonymous later</h1><p>Public theme B.</p></html>", encoding="utf-8")
            private_sources = base / "private-sources"
            private_sources.mkdir(mode=0o700)
            (private_sources / "teacher-notes.txt").write_text(TEACHER_SENTINEL, encoding="utf-8")
            (private_sources / "textbook.png").write_bytes(png_bytes(comment=TEXTBOOK_SENTINEL))
            preserved = {name: (repo / name).read_bytes() for name in
                         ("index.org", ARTICLE, OTHER_ARTICLE, *PRODUCT_FILES)}
            engine = import_product("image_pipeline", repo / "tools/image_pipeline.py")
            adapter = import_product("imagegen", repo / "tools/imagegen.py")
            repo = adapter.repository(repo)
            root, workspace_id = engine.workspace(base / "private-workspace", repo)
            brief = {
                "path": ARTICLE, "title": "Anonymous earlier",
                "article_sha256": engine.sha256((repo / ARTICLE).read_bytes()),
                "public_summary": "An anonymous public mathematical theme.",
                "visual_brief": "Abstract ceramic forms on an ivory background; no diagram or labels.",
                "alt": "Anonymous solid-color fixture; not an API image.",
                "review_checks": ["Verify the subject against the article.", "Check that the illustration implies no false mathematics."],
            }
            briefs = {"schema": "math-visual-image-briefs/v1", "articles": [brief]}
            engine.write_json(repo / "tools/imagegen-config/math-visual-briefs.json", briefs)
            emacs_calls = []
            fake_calls = []
            fake_key_reads = []
            raw = png_bytes()

            def only_emacs(argv, **kwargs):
                prefix = [emacs, "-Q", "--batch", "-L", str(repo / "tools"),
                          "-l", str(repo / "tools/math-visual-build.el"), "--eval"]
                check(isinstance(argv, list) and argv[:8] == prefix and len(argv) == 9,
                      "unexpected_subprocess")
                expression = argv[-1]
                check(expression.startswith("(math-visual-build-image-inventory ") or
                      expression.startswith("(math-visual-build-site "), "unexpected_emacs_operation")
                check(kwargs.get("capture_output") is True and kwargs.get("timeout") == 60
                      and kwargs.get("check") is False and not kwargs.get("shell"),
                      "unexpected_subprocess_options")
                emacs_calls.append("inventory" if "image-inventory" in expression else "site-build")
                # The decoder gets no API key, including one accidentally present in the caller environment.
                environment = {key: value for key, value in os.environ.items()
                               if key not in ("OPENAI_API_KEY", "OPENAI_IMAGE_API_KEY")}
                return real_run(argv, env=environment, **kwargs)

            def build():
                expression = "(math-visual-build-site %s %s)" % (
                    json.dumps(str(repo / "index.org")), json.dumps(str(repo / "index.html")))
                result = subprocess.run([emacs, "-Q", "--batch", "-L", str(repo / "tools"),
                                         "-l", str(repo / "tools/math-visual-build.el"),
                                         "--eval", expression], capture_output=True, timeout=60, check=False)
                check(result.returncode == 0, "emacs_build_failed")
                text = (repo / "index.html").read_text(encoding="utf-8")
                check(FEATURED in text, "pickup_changed")
                for sentinel in (TEACHER_SENTINEL, TEXTBOOK_SENTINEL):
                    check(sentinel not in text, "private_source_in_public_html")
                return text, Cards(text)

            def fake_loader(_settings):
                fake_key_reads.append(True)
                return FAKE_KEY

            def fake_transport(body, key, project, client_id):
                check(key == FAKE_KEY and project == PROJECT, "synthetic_settings_binding")
                check(body.get("n") == 1 and body.get("model") == engine.MODEL, "unexpected_fake_request")
                check(set(body) == {"model", "prompt", "quality", "size", "output_format", "background", "n"},
                      "unexpected_payload_fields")
                encoded = engine.canonical(body)
                for sentinel in (TEACHER_SENTINEL, TEXTBOOK_SENTINEL):
                    check(sentinel.encode() not in encoded, "private_source_in_payload")
                fake_calls.append({"n": body["n"], "model": body["model"]})
                return {
                    "data": [{"b64_json": base64.b64encode(raw).decode("ascii")}],
                    "size": "1536x1024", "quality": "low", "output_format": "png", "background": "opaque",
                    "usage": {"input_tokens_details": {"text_tokens": 200, "image_tokens": 0}, "output_tokens": 1000},
                }, "req_anonymous_smoke_fixture"

            with ExitStack() as guards:
                forbidden = []
                for target, attribute in ((socket, "create_connection"), (socket.socket, "connect"),
                                          (socket.socket, "connect_ex"), (http.client, "HTTPSConnection"),
                                          (http.client, "HTTPConnection"), (engine, "load_key"), (os, "system")):
                    forbidden.append(guards.enter_context(mock.patch.object(
                        target, attribute, side_effect=AssertionError("forbidden external operation"))))
                allowed_process = guards.enter_context(mock.patch.object(subprocess, "run", side_effect=only_emacs))
                inventory = adapter.export_inventory(repo, root, emacs)
                check([x["path"] for x in inventory["articles"]] == [ARTICLE, OTHER_ARTICLE], "inventory_page_order")
                check([x["page"] for x in inventory["articles"]] == ["10", "20"], "inventory_pages")
                inventory_bytes = engine.canonical(inventory)
                for sentinel in (TEACHER_SENTINEL, TEXTBOOK_SENTINEL):
                    check(sentinel.encode() not in inventory_bytes, "private_source_in_inventory")
                initial_html, initial = build()
                check(len(initial.cards) == 2 and all(not card["images"] for card in initial.cards), "initial_fallback")
                expected = [
                    {"href": ARTICLE, "title": "Anonymous earlier", "page": "Anonymous book p.10",
                     "dates": "HTML / 2001-01-01（公開）・2001-01-02（更新）"},
                    {"href": OTHER_ARTICLE, "title": "Anonymous later", "page": "Anonymous book p.20",
                     "dates": "HTML / 2001-02-01（公開）・2001-02-02（更新）"},
                ]
                check(initial.signature() == expected, "initial_links_pages_dates")
                today = dt.datetime.now(dt.timezone.utc).date()
                price = {
                    "schema": "image-price-quote/v1", "model": engine.MODEL, "quality": "low", "size": "1536x1024",
                    "output_format": "png", "background": "opaque", "operator_verified": True,
                    "source_url": engine.PRICE_SOURCE, "verified_at": today.isoformat(),
                    "valid_until": (today + dt.timedelta(days=1)).isoformat(),
                    "text_input_usd_per_million": "5", "image_output_usd_per_million": "30",
                    "output_image_estimate_usd": "0.05",
                }
                settings = {"schema": "image-settings/v1", "project_id": PROJECT,
                            "textbook_project_id": PROJECT, "same_project_confirmed": True,
                            "dedicated_image_key_confirmed": True, "key_source": "environment"}
                plan = adapter.make_math_plan(repo, inventory, briefs, ARTICLE, workspace_id,
                                              count=1, price_profile=price, budget_usd="1.00", settings=settings)
                engine.write_json(root / "plans" / (plan["plan_id"] + ".json"), plan, exclusive=True)
                check(not (repo / "images/entries/manifest.json").exists(), "unreviewed_manifest")
                receipt = engine.generate(plan, root, workspace_id, settings, plan["plan_id"], True,
                                          transport=fake_transport, key_loader=fake_loader,
                                          source_check=lambda selected: adapter.source_check(repo, selected))
                check(receipt["status"] == "candidates_received", "fake_generation_result")
                adapter.review_page(root, plan, repo)
                record, _ = engine.candidate(root, plan, 1)
                review = engine.review_candidate(root, plan, 1, record["sha256"], "approve",
                                                 {name: True for name in engine.CHECKS},
                                                 "Anonymous smoke fixture, not an API-generated image.")
                row = adapter.adopt_math_image(root, repo, plan, review, review["review_id"])
                adopted_html, adopted = build()
                check(adopted.signature() == expected, "adopted_links_pages_dates")
                check([len(card["images"]) for card in adopted.cards] == [1, 0], "approved_and_fallback_counts")
                check(adopted.cards[0]["images"][0]["src"] == row["image"], "adopted_image_binding")
                check("教材をイメージしたイラスト" in adopted_html, "illustration_caption")
                check("object-fit: contain" in adopted_html, "illustration_no_crop")
                repeated_html, repeated = build()
                check(repeated_html == adopted_html, "rebuild_not_idempotent")
                check(repeated.signature() == expected, "repeated_links_pages_dates")
                manifest_bytes = (repo / "images/entries/manifest.json").read_bytes()
                image_bytes = (repo / row["image"]).read_bytes()
                for forbidden_value in (TEACHER_SENTINEL, TEXTBOOK_SENTINEL, FAKE_KEY, PROJECT,
                                        plan["prompt"], "client_request_id", "price_profile"):
                    check(forbidden_value.encode() not in manifest_bytes + image_bytes, "private_data_in_adopted_assets")
                check((repo / row["image"]).read_bytes() == engine.candidate(root, plan, 1)[1], "adopted_png_changed")
                for name, before in preserved.items():
                    check((repo / name).read_bytes() == before, "source_changed_by_workflow")
                (repo / ARTICLE).write_text("<html><h1>Anonymous earlier</h1><p>Intentionally changed source.</p></html>", encoding="utf-8")
                stale_html, stale = build()
                check(stale.signature() == expected, "stale_links_pages_dates")
                check(all(not card["images"] for card in stale.cards), "stale_image_not_omitted")
                check((repo / "images/entries/manifest.json").read_bytes() == manifest_bytes, "fallback_mutated_manifest")
                check(len(fake_calls) == 1 and len(fake_key_reads) == 1, "unexpected_fake_call_count")
                check(emacs_calls == ["inventory", "site-build", "site-build", "site-build", "site-build"],
                      "unexpected_emacs_call_count")
                check(allowed_process.call_count == 5, "unexpected_subprocess_count")
                for operation in forbidden:
                    operation.assert_not_called()
            return {
                "schema": "image-pipeline-smoke/v1", "status": "passed",
                "product_files_sha256": source_hashes,
                "fixture": "anonymous-temporary-repository-and-private-workspace",
                "temporary_files_removed": True,
                "image_origin": "Pillow solid-color synthetic fixture; no API generation",
                "price_profile": "synthetic test input; not a service quote",
                "human_review": "simulated fixture checks; no real candidate approval",
                "api_calls": 0, "fake_transport_calls": len(fake_calls), "keychain_calls": 0,
                "network_calls": 0, "emacs_calls": emacs_calls,
                "article_count": 2, "page_order": [10, 20],
                "links_preserved": True, "teaching_dates_preserved": True,
                "pickup_preserved": True, "initial_without_images": 2,
                "approved_images": 1, "fallback_articles": 1,
                "rebuild_idempotent": True, "stale_image_fallback": True,
                "private_sources_excluded_from_inventory_payload_and_public_output": True,
                "published": False, "real_repository_adoption": False,
                "browser_visual_verification": "not performed by this smoke test",
            }
    finally:
        for name, previous in saved_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emacs", default="emacs", help="Installed Emacs executable or scratch wrapper.")
    parser.add_argument("--output", type=Path, help="New JSON file for anonymous evidence; never overwrite.")
    args = parser.parse_args(argv)
    try:
        if args.output:
            check(args.output.suffix == ".json" and not args.output.exists()
                  and not args.output.is_symlink() and args.output.parent.is_dir(),
                  "new_json_output_required")
        result = smoke(resolve_emacs(args.emacs))
        data = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if args.output:
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        print(data.decode("utf-8"), end="")
        return 0
    except SmokeError as error:
        print(json.dumps({"status": "failed", "code": str(error)}), file=sys.stderr)
        return 1
    except Exception:
        print('{"status":"failed","code":"smoke_operation_failed"}', file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
