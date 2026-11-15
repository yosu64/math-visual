"""Anonymous offline integration tests for the math-visual image adapter.

Only temporary synthetic repositories and private workspaces are written.
HTTP, sockets, Keychain and external processes are blocked; the sole inventory
subprocess is replaced by an in-process fixture. No real generation or adoption
into the source repository occurs.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import imagegen as adapter
import image_pipeline as engine
import test_image_pipeline as fixtures


ARTICLE = "./math-i/anonymous-article.html"
OTHER_ARTICLE = "./math-ii/anonymous-other.html"
PRIVATE_NOTE = "ANONYMOUS_TEACHER_NOTE_NEVER_PUBLISH"


class ImageElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.meta = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.images.append(dict(attrs))
        elif tag == "meta":
            self.meta.append(dict(attrs))


class AdapterCase(fixtures.OfflineCase):
    def setUp(self):
        super().setUp()
        self.repo = self.tempdir / "anonymous-repository"
        (self.repo / "tools/imagegen-config").mkdir(parents=True)
        (self.repo / ".git").mkdir()
        (self.repo / "math-i").mkdir()
        (self.repo / "math-ii").mkdir()
        (self.repo / "index.org").write_text("* Anonymous subject\n** Anonymous article\n", encoding="utf-8")
        (self.repo / "index.html").write_text("<html>Anonymous existing public entrance.</html>", encoding="utf-8")
        (self.repo / "tools/math-visual-build.el").write_text(";; Never executed: anonymous inventory fixture.\n", encoding="utf-8")
        (self.repo / ARTICLE).write_text("<html><p>Anonymous mathematics theme.</p><!-- " + PRIVATE_NOTE + " --></html>", encoding="utf-8")
        (self.repo / OTHER_ARTICLE).write_text("<html>Another independent anonymous article.</html>", encoding="utf-8")
        article_hash = engine.sha256((self.repo / ARTICLE).read_bytes())
        self.inventory = {
            "schema": "math-visual-image-inventory/v1",
            "index_sha256": engine.sha256((self.repo / "index.org").read_bytes()),
            "articles": [{"path": ARTICLE, "title": "Anonymous article",
                          "description": "Existing public summary.", "subject": "Anonymous subject",
                          "textbook": "Anonymous book", "page": "12", "published": "2000-01-01",
                          "updated": "2000-01-02", "article_sha256": article_hash}],
        }
        self.briefs = {
            "schema": "math-visual-image-briefs/v1",
            "articles": [{"path": ARTICLE, "title": "Anonymous article",
                          "article_sha256": article_hash,
                          "public_summary": "An anonymous mathematical idea.",
                          "visual_brief": "Two abstract ceramic forms with generous margins.",
                          "alt": "Anonymous abstract illustration.",
                          "review_checks": ["Check the topic against the article.",
                                            "Check that no mathematical claim is implied."]}],
        }
        self.write_briefs()
        engine.write_json(self.root / "inventory.json", self.inventory)

    def write_briefs(self):
        engine.write_json(self.repo / "tools/imagegen-config/math-visual-briefs.json", self.briefs)

    def plan(self, **changes):
        kwargs = dict(count=1, quality="low", size="1536x1024",
                      price_profile=fixtures.synthetic_price(), budget_usd="1.00",
                      settings=self.settings)
        kwargs.update(changes)
        return adapter.make_math_plan(self.repo, self.inventory, self.briefs,
                                      ARTICLE, self.workspace_id, **kwargs)

    def run_plan(self, plan, **changes):
        changes.setdefault("source_check", lambda selected: adapter.source_check(self.repo, selected))
        return super().run_plan(plan, **changes)

    def approve(self, plan, index=1, **changes):
        record, _ = engine.candidate(self.root, plan, index)
        kwargs = dict(root=self.root, plan=plan, index=index,
                      image_sha256=record["sha256"], decision="approve",
                      checks={name: True for name in engine.CHECKS},
                      alt="Reviewed anonymous illustration.")
        kwargs.update(changes)
        return engine.review_candidate(**kwargs)

    def adopt(self, plan, review, **changes):
        return adapter.adopt_math_image(self.root, self.repo, plan, review,
                                        changes.pop("confirm_review", review["review_id"]),
                                        **changes)

    def generated(self, **changes):
        plan = self.plan(**changes)
        self.run_plan(plan)
        return plan

    def no_public_image(self):
        target = self.repo / "images/entries"
        self.assertFalse((target / "manifest.json").exists())
        self.assertEqual([], list(target.glob("*.png")))

    def source_snapshot(self):
        return {str(p.relative_to(self.repo)): p.read_bytes()
                for p in [self.repo / "index.org", self.repo / "index.html",
                          self.repo / ARTICLE, self.repo / OTHER_ARTICLE,
                          self.repo / "tools/math-visual-build.el",
                          self.repo / "tools/imagegen-config/math-visual-briefs.json"]}

    def fake_inventory_process(self, *, data=None, returncode=0, change_source=False):
        def fake(argv, **kwargs):
            self.assertEqual("anonymous-emacs", argv[0])
            self.assertEqual(["-Q", "--batch"], argv[1:3])
            self.assertTrue(kwargs["capture_output"])
            self.assertEqual(60, kwargs["timeout"])
            expression = argv[-1]
            prefix = "(math-visual-build-image-inventory "
            self.assertTrue(expression.startswith(prefix))
            decoder = json.JSONDecoder()
            source, position = decoder.raw_decode(expression[len(prefix):])
            remainder = expression[len(prefix) + position:].lstrip()
            output, _ = decoder.raw_decode(remainder)
            self.assertEqual(str(self.repo / "index.org"), source)
            output = Path(output)
            self.assertEqual(self.root, output.parent)
            content = copy.deepcopy(self.inventory if data is None else data)
            content.pop("index_sha256", None)
            engine.write_json(output, content)
            if change_source:
                (self.repo / "index.org").write_text("Changed while exporting.", encoding="utf-8")
            return types.SimpleNamespace(returncode=returncode,
                                         stdout=PRIVATE_NOTE.encode(), stderr=PRIVATE_NOTE.encode())
        return fake


class MathVisualAdapterTests(AdapterCase):
    def test_full_offline_generation_review_adoption_preserves_sources(self):
        before = self.source_snapshot()
        plan = self.generated(count=2)
        self.assertNotIn(PRIVATE_NOTE, plan["prompt"])
        self.assertEqual(2, self.sender.call_count)
        self.no_public_image()
        review = self.approve(plan, index=2)
        self.no_public_image()
        row = self.adopt(plan, review)
        public_manifest = engine.read_json(self.repo / "images/entries/manifest.json")
        self.assertEqual([row], public_manifest["images"])
        self.assertEqual(ARTICLE, row["article"])
        self.assertEqual(before, self.source_snapshot())
        _, candidate = engine.candidate(self.root, plan, 2)
        self.assertEqual(candidate, (self.repo / row["image"]).read_bytes())
        receipt = engine.read_json(self.root / "runs" / plan["plan_id"] /
                                   ("adopted-" + review["review_id"] + ".json"))
        self.assertFalse(receipt["published"])
        self.assertEqual(review["review_id"], receipt["review_id"])

    def test_public_manifest_has_only_adoption_metadata(self):
        plan = self.generated()
        row = self.adopt(plan, self.approve(plan))
        allowed = {"article", "article_sha256", "image", "sha256", "alt", "role",
                   "approved", "reviewed_at", "review_id"}
        self.assertEqual(allowed, set(row))
        manifest = (self.repo / "images/entries/manifest.json").read_text()
        for forbidden in (PRIVATE_NOTE, fixtures.PROJECT, fixtures.FAKE_KEY, plan["prompt"],
                          "client_request_id", "public_summary", "keychain", "price_profile",
                          "settings_sha256", "candidate_index"):
            self.assertNotIn(forbidden, manifest)
        with fixtures.Image.open(self.repo / row["image"]) as image:
            self.assertEqual((1536, 1024), image.size)
            self.assertEqual({}, image.info)
        self.assertEqual([], list((self.repo / "images/entries").glob("candidate-*")))

    def test_stale_inventory_and_wrong_article_hash_refuse_before_key(self):
        stale = copy.deepcopy(self.inventory)
        self.inventory["index_sha256"] = "0" * 64
        self.assert_code("inventory_stale", self.plan)
        self.inventory = stale
        self.inventory["articles"][0]["article_sha256"] = "0" * 64
        self.assert_code("article_changed_replan_and_review", self.plan)
        self.inventory["articles"][0]["article_sha256"] = engine.sha256((self.repo / ARTICLE).read_bytes())
        self.briefs["articles"][0]["article_sha256"] = "1" * 64
        self.assert_code("article_changed_replan_and_review", self.plan)
        self.loader.assert_not_called()
        self.sender.assert_not_called()

    def test_duplicate_or_wrong_brief_mapping_is_not_guessed(self):
        self.briefs["articles"].append(copy.deepcopy(self.briefs["articles"][0]))
        self.assert_code("article_mapping_not_unique", self.plan)
        self.briefs["articles"].pop()
        self.briefs["articles"][0]["path"] = OTHER_ARTICLE
        self.assert_code("article_mapping_not_unique", self.plan)
        self.sender.assert_not_called()

    def test_title_mismatch_requires_new_brief(self):
        self.briefs["articles"][0]["title"] = "A different title"
        self.assert_code("brief_title_mismatch", self.plan)

    def test_changed_article_blocks_dispatch_and_adoption(self):
        plan = self.generated()
        review = self.approve(plan)
        (self.repo / ARTICLE).write_text("<html>Changed content</html>", encoding="utf-8")
        self.assert_code("article_changed_replan_and_review", self.adopt, plan, review)
        unattempted = copy.deepcopy(plan)
        unattempted["nonce"] = "replacement-fixture"
        fixtures.rehash_plan(unattempted)
        self.loader.reset_mock()
        self.sender.reset_mock()
        self.assert_code("article_changed_replan_and_review", self.run_plan, unattempted)
        self.loader.assert_not_called()
        self.sender.assert_not_called()
        self.no_public_image()

    def test_index_change_requires_replanning_before_adoption(self):
        plan = self.generated()
        review = self.approve(plan)
        (self.repo / "index.org").write_text("* Changed public index", encoding="utf-8")
        self.assert_code("index_changed_replan_and_review", self.adopt, plan, review)
        self.no_public_image()

    def test_brief_change_requires_replanning_before_adoption(self):
        plan = self.generated()
        review = self.approve(plan)
        self.briefs["articles"][0]["visual_brief"] = "Different visual proposal."
        self.write_briefs()
        self.assert_code("brief_changed_replan_and_review", self.adopt, plan, review)
        self.no_public_image()

    def test_each_missing_human_check_refuses_approval(self):
        plan = self.generated()
        for missing in engine.CHECKS:
            with self.subTest(missing=missing):
                checks = {name: name != missing for name in engine.CHECKS}
                self.assert_code("human_checks_required", self.approve, plan, checks=checks)
        self.no_public_image()
        self.assertEqual([], list((self.root / "reviews").glob("*-current.json")))

    def test_rejected_candidate_cannot_be_adopted(self):
        plan = self.generated()
        rejection = self.approve(plan, decision="reject",
                                 checks={name: False for name in engine.CHECKS})
        self.assert_code("review_not_approved", self.adopt, plan, rejection)
        self.no_public_image()

    def test_later_rejection_invalidates_earlier_approval(self):
        plan = self.generated()
        approval = self.approve(plan)
        rejection = self.approve(plan, decision="reject", alt="Rejected after another look.")
        self.assertNotEqual(approval["review_id"], rejection["review_id"])
        self.assert_code("review_superseded", self.adopt, plan, approval)
        self.no_public_image()

    def test_candidate_changes_after_review_cannot_be_adopted(self):
        plan = self.generated()
        review = self.approve(plan)
        image = self.root / "runs" / plan["plan_id"] / "candidate-1.png"
        image.write_bytes(fixtures.png_bytes(color=(120, 30, 40)))
        self.assert_code("candidate_changed", self.adopt, plan, review)
        self.no_public_image()

    def test_wrong_review_plan_and_modified_review_are_rejected(self):
        first = self.generated()
        review = self.approve(first)
        second = self.generated()
        self.assert_code("review_binding", self.adopt, second, review)
        changed = copy.deepcopy(review)
        changed["alt"] = "Unreviewed alternative text."
        self.assert_code("review_hash", self.adopt, first, changed)
        self.assert_code("adoption_confirmation_required", self.adopt, first, review,
                         confirm_review="0" * 64)
        self.no_public_image()

    def test_existing_manifest_keeps_other_article_exactly(self):
        folder = self.repo / "images/entries"
        folder.mkdir(parents=True)
        other = {"article": OTHER_ARTICLE, "article_sha256": "1" * 64,
                 "image": "./images/entries/" + "2" * 64 + ".png", "sha256": "2" * 64,
                 "alt": "Existing independent approved image.", "role": "entry-illustration",
                 "approved": True, "reviewed_at": "2000-01-01T00:00:00Z", "review_id": "3" * 64}
        engine.write_json(folder / "manifest.json", {"schema": "math-visual-entry-images/v1", "images": [other]})
        plan = self.generated()
        row = self.adopt(plan, self.approve(plan))
        rows = engine.read_json(folder / "manifest.json")["images"]
        self.assertEqual([other, row], rows)

    def test_replacement_requires_the_exact_previous_image_hash(self):
        first = self.generated()
        original = self.adopt(first, self.approve(first))
        self.sender.return_value = (fixtures.response_for(fixtures.png_bytes(color=(160, 70, 20))),
                                    "req_anonymous_replacement")
        second = self.generated()
        review = self.approve(second)
        before = (self.repo / "images/entries/manifest.json").read_bytes()
        for prior in (None, "0" * 64):
            with self.subTest(previous=prior):
                self.assert_code("existing_image_requires_exact_replace_confirmation",
                                 self.adopt, second, review, replace_image_sha=prior)
                self.assertEqual(before, (self.repo / "images/entries/manifest.json").read_bytes())
        replacement = self.adopt(second, review, replace_image_sha=original["sha256"])
        self.assertNotEqual(original["sha256"], replacement["sha256"])
        self.assertTrue((self.repo / original["image"]).is_file())
        self.assertEqual([replacement], engine.read_json(self.repo / "images/entries/manifest.json")["images"])

    def test_article_aliases_and_external_paths_are_refused(self):
        for name in ("./math-i/./anonymous-article.html", "./math-i//anonymous-article.html",
                     "./math-i/../math-i/anonymous-article.html", "/math-i/anonymous-article.html",
                     "https://example.invalid/anonymous-article.html"):
            with self.subTest(path=name):
                self.assert_code("article_path", adapter.article_file, self.repo, name)

    def test_article_symlink_escape_is_refused(self):
        article = self.repo / ARTICLE
        target = self.tempdir / "outside-article.html"
        target.write_bytes(article.read_bytes())
        article.unlink()
        article.symlink_to(target)
        self.assert_code("symlink_refused", self.plan)

    def test_index_symlink_escape_is_refused(self):
        index = self.repo / "index.org"
        target = self.tempdir / "outside-index.org"
        target.write_bytes(index.read_bytes())
        index.unlink()
        index.symlink_to(target)
        self.assert_code("symlink_refused", self.plan)

    def test_generator_symlink_escape_is_refused(self):
        generator = self.repo / "tools/math-visual-build.el"
        target = self.tempdir / "outside-generator.el"
        target.write_bytes(generator.read_bytes())
        generator.unlink()
        generator.symlink_to(target)
        self.assert_code("symlink_refused", adapter.repository, self.repo)

    def test_candidate_symlink_escape_is_refused(self):
        plan = self.generated()
        review = self.approve(plan)
        image = self.root / "runs" / plan["plan_id"] / "candidate-1.png"
        target = self.tempdir / "outside-image.png"
        target.write_bytes(image.read_bytes())
        image.unlink()
        image.symlink_to(target)
        self.assert_code("symlink_refused", self.adopt, plan, review)
        self.no_public_image()

    def test_destination_and_manifest_symlinks_are_refused(self):
        plan = self.generated()
        review = self.approve(plan)
        outside = self.tempdir / "outside-images"
        outside.mkdir()
        (self.repo / "images").mkdir()
        destination = self.repo / "images/entries"
        destination.symlink_to(outside, target_is_directory=True)
        self.assert_code("symlink_refused", self.adopt, plan, review)
        self.assertEqual([], list(outside.iterdir()))
        destination.unlink()
        destination.mkdir()
        external_manifest = outside / "manifest.json"
        engine.write_json(external_manifest, {"schema": "math-visual-entry-images/v1", "images": []})
        original = external_manifest.read_bytes()
        (destination / "manifest.json").symlink_to(external_manifest)
        self.assert_code("symlink_refused", self.adopt, plan, review)
        self.assertEqual(original, external_manifest.read_bytes())


class ReviewPageAndCliTests(AdapterCase):
    def test_review_page_escapes_input_and_uses_a_restrictive_csp(self):
        title = '<script>alert("title")</script>'
        summary = '<img src="https://example.invalid/leak" onerror="alert(1)">'
        self.inventory["articles"][0]["title"] = title
        self.briefs["articles"][0]["title"] = title
        self.briefs["articles"][0]["public_summary"] = summary
        self.briefs["articles"][0]["visual_brief"] = "<script>prompt</script>"
        self.briefs["articles"][0]["review_checks"] = ["<script>check</script>"]
        self.write_briefs()
        plan = self.generated(count=3)
        output = adapter.review_page(self.root, plan, self.repo)
        text = output.read_text()
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)
        self.assertNotIn(summary, text)
        self.assertNotIn(PRIVATE_NOTE, text)
        elements = ImageElements()
        elements.feed(text)
        self.assertEqual(3, len(elements.images))
        self.assertTrue(all(image["src"].startswith("data:image/png;base64,") for image in elements.images))
        csp = next(item["content"] for item in elements.meta if item.get("http-equiv") == "Content-Security-Policy")
        for restriction in ("default-src 'none'", "img-src data:", "base-uri 'none'", "form-action 'none'"):
            self.assertIn(restriction, csp)
        self.assertIn("予定枚数: 3", text)
        self.assertIn("未採用", text)
        self.no_public_image()

    def test_review_page_shows_only_received_candidates_after_a_stop(self):
        response = fixtures.response_for(self.raw_png)
        response.pop("usage")
        self.sender.return_value = (response, "req_anonymous_no_usage")
        plan = self.generated(count=3)
        output = adapter.review_page(self.root, plan, self.repo)
        elements = ImageElements()
        elements.feed(output.read_text())
        self.assertEqual(1, len(elements.images))
        self.assertEqual(1, self.sender.call_count)

    def test_review_page_does_not_display_a_changed_candidate(self):
        plan = self.generated()
        image = self.root / "runs" / plan["plan_id"] / "candidate-1.png"
        image.write_bytes(b"not the reviewed image")
        self.assert_code("candidate_changed", adapter.review_page, self.root, plan, self.repo)
        self.assertFalse((self.root / "previews" / (plan["plan_id"] + ".html")).exists())

    def test_unattempted_plan_has_no_review_page(self):
        plan = self.plan()
        self.assert_code("no_candidates_to_review", adapter.review_page, self.root, plan, self.repo)
        self.sender.assert_not_called()

    def test_mistaken_key_in_arguments_is_not_echoed(self):
        secret = fixtures.FAKE_KEY
        cases = [
            ["--workspace", str(self.root), "plan", "--api-key", secret],
            ["--workspace", str(self.root), "plan", "--repo", str(self.repo),
             "--article", ARTICLE, "--candidates", secret],
            ["--workspace", str(self.root), "plan", "--repo", str(self.repo),
             "--article", ARTICLE, "--quality", secret],
            ["--workspace", str(self.root), secret],
        ]
        for argv in cases:
            with self.subTest(argument_shape=argv[2] if len(argv) > 2 else "short"):
                output, errors = io.StringIO(), io.StringIO()
                with redirect_stdout(output), redirect_stderr(errors):
                    code = adapter.main(argv)
                self.assertEqual(2, code)
                self.assertNotIn(secret, output.getvalue() + errors.getvalue())
                self.assertEqual("invalid_arguments_see_help", json.loads(errors.getvalue())["code"])
        self.sender.assert_not_called()
        self.loader.assert_not_called()


class InventoryExportTests(AdapterCase):
    def test_successful_inventory_export_uses_org_and_binds_current_index(self):
        with mock.patch.object(adapter.subprocess, "run", side_effect=self.fake_inventory_process()) as process:
            inventory = adapter.export_inventory(self.repo, self.root, "anonymous-emacs")
        self.assertEqual(1, process.call_count)
        self.assertEqual(engine.sha256((self.repo / "index.org").read_bytes()), inventory["index_sha256"])
        self.assertEqual(inventory, engine.read_json(self.root / "inventory.json"))
        self.assertEqual([], list(self.root.glob("inventory-*.json")))
        self.assertNotIn(PRIVATE_NOTE, (self.root / "inventory.json").read_text())

    def test_process_failure_preserves_previous_inventory(self):
        old = (self.root / "inventory.json").read_bytes()
        with mock.patch.object(adapter.subprocess, "run",
                               side_effect=self.fake_inventory_process(returncode=1)):
            self.assert_code("inventory_export_failed", adapter.export_inventory,
                             self.repo, self.root, "anonymous-emacs")
        self.assertEqual(old, (self.root / "inventory.json").read_bytes())

    def test_timeout_preserves_previous_inventory(self):
        old = (self.root / "inventory.json").read_bytes()
        with mock.patch.object(adapter.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("anonymous-emacs", 60,
                                                                    output=PRIVATE_NOTE.encode())):
            self.assert_code("emacs_inventory_unavailable", adapter.export_inventory,
                             self.repo, self.root, "anonymous-emacs")
        self.assertEqual(old, (self.root / "inventory.json").read_bytes())

    def test_invalid_export_schema_preserves_previous_inventory(self):
        old = (self.root / "inventory.json").read_bytes()
        with mock.patch.object(adapter.subprocess, "run",
                               side_effect=self.fake_inventory_process(data={"schema": "not-inventory"})):
            self.assert_code("inventory_schema", adapter.export_inventory,
                             self.repo, self.root, "anonymous-emacs")
        self.assertEqual(old, (self.root / "inventory.json").read_bytes())

    def test_source_change_during_export_preserves_previous_inventory(self):
        old = (self.root / "inventory.json").read_bytes()
        with mock.patch.object(adapter.subprocess, "run",
                               side_effect=self.fake_inventory_process(change_source=True)):
            self.assert_code("source_changed_during_inventory", adapter.export_inventory,
                             self.repo, self.root, "anonymous-emacs")
        self.assertEqual(old, (self.root / "inventory.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
