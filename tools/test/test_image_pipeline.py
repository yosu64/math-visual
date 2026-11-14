"""Anonymous, offline contract tests for the image engine.

All images, prices, project identifiers, credentials, dates, and responses are
synthetic.  The prices below are test inputs, not quotes for the real service.
No HTTP, socket connection, or Keychain subprocess is permitted in these tests.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
import copy
import datetime
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest import mock

from PIL import Image, PngImagePlugin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import image_pipeline as engine


TEST_DATE = datetime.date(2026, 11, 14)
REAL_DATETIME = datetime.datetime
FAKE_KEY = "sk-" + "anonymous-fixture-" + "0" * 24
PROJECT = "proj_anonymous_fixture"


class FrozenDateTime(REAL_DATETIME):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 11, 14, 12, 0, tzinfo=datetime.timezone.utc)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)


def synthetic_settings(**changes):
    settings = {
        "schema": "image-settings/v1", "project_id": PROJECT,
        "textbook_project_id": PROJECT, "same_project_confirmed": True,
        "dedicated_image_key_confirmed": True, "key_source": "environment",
    }
    settings.update(changes)
    return settings


def synthetic_price(**changes):
    profile = {
        "schema": "image-price-quote/v1", "model": engine.MODEL,
        "quality": "low", "size": "1536x1024", "output_format": "png",
        "background": "opaque", "operator_verified": True,
        "source_url": engine.PRICE_SOURCE,
        "verified_at": TEST_DATE.isoformat(),
        "valid_until": (TEST_DATE + datetime.timedelta(days=7)).isoformat(),
        "text_input_usd_per_million": "5",
        "image_output_usd_per_million": "30",
        "output_image_estimate_usd": "0.05",
    }
    profile.update(changes)
    return profile


def png_bytes(size=(1536, 1024), *, metadata=False, color=(24, 61, 90)):
    image = Image.new("RGB", size, color)
    target = io.BytesIO()
    kwargs = {}
    if metadata:
        info = PngImagePlugin.PngInfo()
        info.add_text("Comment", "ANONYMOUS_PRIVATE_COMMENT")
        info.add_text("Software", "ANONYMOUS_SOURCE_TOOL")
        kwargs["pnginfo"] = info
        kwargs["icc_profile"] = b"ANONYMOUS_PRIVATE_ICC_METADATA"
        exif = Image.Exif()
        exif[0x010E] = "ANONYMOUS_PRIVATE_EXIF"
        kwargs["exif"] = exif.tobytes()
    image.save(target, format="PNG", **kwargs)
    return target.getvalue()


def response_for(raw, **changes):
    response = {
        "data": [{"b64_json": base64.b64encode(raw).decode("ascii")}],
        "size": "1536x1024", "quality": "low", "output_format": "png",
        "background": "opaque",
        "usage": {
            "input_tokens_details": {"text_tokens": 200, "image_tokens": 0},
            "output_tokens": 1000,
        },
    }
    response.update(changes)
    return response


def rehash_plan(plan):
    plan["plan_id"] = engine.digest({k: v for k, v in plan.items() if k != "plan_id"})
    return plan


class OfflineCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_png = png_bytes()

    def setUp(self):
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(engine.dt, "datetime", FrozenDateTime).start()
        mock.patch.dict(os.environ, {}, clear=True).start()
        self.network_guard = mock.patch.object(
            socket, "create_connection", side_effect=AssertionError("network forbidden")
        ).start()
        self.socket_guard = mock.patch.object(
            socket.socket, "connect", side_effect=AssertionError("network forbidden")
        ).start()
        self.process_guard = mock.patch.object(
            engine.subprocess, "run", side_effect=AssertionError("Keychain/process forbidden")
        ).start()
        self.https_guard = mock.patch.object(
            engine.http.client, "HTTPSConnection",
            side_effect=AssertionError("real HTTP transport forbidden")
        ).start()
        self.temporary = tempfile.TemporaryDirectory(prefix="anonymous-image-test-")
        self.addCleanup(self.temporary.cleanup)
        self.tempdir = Path(self.temporary.name).resolve()
        self.root, self.workspace_id = engine.workspace(self.tempdir / "private")
        self.settings = synthetic_settings()
        self.loader = mock.Mock(return_value=FAKE_KEY)
        self.sender = mock.Mock(return_value=(response_for(self.raw_png), "req_anonymous_fixture"))

    def tearDown(self):
        self.network_guard.assert_not_called()
        self.socket_guard.assert_not_called()
        self.process_guard.assert_not_called()
        self.https_guard.assert_not_called()

    def plan(self, **changes):
        kwargs = dict(
            workspace_id=self.workspace_id,
            subject={"adapter": "anonymous-test", "id": "fixture-article"},
            prompt="An abstract illustration for an anonymous mathematics article.",
            review_checks=["Check the mathematical meaning against the article."],
            count=1, quality="low", size="1536x1024",
            price_profile=synthetic_price(), budget_usd="1.00", settings=self.settings,
        )
        kwargs.update(changes)
        return engine.make_plan(**kwargs)

    def run_plan(self, plan, **changes):
        kwargs = dict(
            plan=plan, root=self.root, workspace_id=self.workspace_id,
            settings=self.settings, confirm_plan=plan["plan_id"], approve_charge=True,
            transport=self.sender, key_loader=self.loader,
        )
        kwargs.update(changes)
        return engine.generate(**kwargs)

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(engine.PipelineError) as caught:
            function(*args, **kwargs)
        self.assertEqual(code, caught.exception.code)
        return caught.exception

    def receipt(self, plan):
        return engine.read_json(self.root / "runs" / plan["plan_id"] / "receipt.json")


class PlanningTests(OfflineCase):
    def test_no_approval_reads_no_key_and_sends_nothing(self):
        plan = self.plan()
        for changes in ({"approve_charge": False}, {"confirm_plan": "0" * 64}):
            with self.subTest(changes=changes):
                self.assert_code("charge_approval_required", self.run_plan, plan, **changes)
        self.loader.assert_not_called()
        self.sender.assert_not_called()

    def test_modified_plan_is_not_covered_by_previous_approval(self):
        plan = self.plan()
        plan["prompt"] += " A changed instruction."
        self.assert_code("plan_hash_mismatch", self.run_plan, plan)
        self.loader.assert_not_called()
        self.sender.assert_not_called()

    def test_unknown_price_allows_planning_but_not_generation(self):
        plan = self.plan(price_profile=None)
        self.assertIsNone(plan["cost"]["total_estimate_usd"])
        self.assertFalse(plan["cost"]["is_enforced_billing_cap"])
        self.assert_code("price_schema", self.run_plan, plan)
        self.loader.assert_not_called()
        self.sender.assert_not_called()

    def test_unverified_expired_future_or_mismatched_prices_are_rejected(self):
        cases = [
            ({"operator_verified": False}, "price_not_verified"),
            ({"valid_until": "2026-11-13"}, "price_expired_or_invalid"),
            ({"verified_at": "2026-11-15"}, "price_expired_or_invalid"),
            ({"valid_until": "2026-12-01"}, "price_expired_or_invalid"),
            ({"quality": "high"}, "price_parameters_mismatch"),
            ({"model": "anonymous-other-model"}, "price_parameters_mismatch"),
            ({"source_url": "https://example.invalid/prices"}, "price_source"),
            ({"output_image_estimate_usd": None}, "invalid_money"),
            ({"api_key": FAKE_KEY}, "price_fields"),
        ]
        for changes, code in cases:
            with self.subTest(changes=changes):
                self.assert_code(code, self.plan, price_profile=synthetic_price(**changes))
        self.sender.assert_not_called()

    def test_price_expiring_after_plan_creation_prevents_dispatch(self):
        plan = self.plan()
        class AfterExpiry(REAL_DATETIME):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 11, 22, 12, 0, tzinfo=datetime.timezone.utc)
        with mock.patch.object(engine.dt, "datetime", AfterExpiry):
            self.assert_code("price_expired_or_invalid", self.run_plan, plan)
        self.loader.assert_not_called()
        self.sender.assert_not_called()

    def test_budget_below_reservation_or_missing_prevents_dispatch(self):
        self.assert_code("budget_below_estimate", self.plan, budget_usd="0.001")
        plan = self.plan(budget_usd=None)
        self.assert_code("invalid_money", self.run_plan, plan)
        self.loader.assert_not_called()
        self.sender.assert_not_called()

    def test_project_and_dedicated_key_confirmation_are_required(self):
        cases = [
            ({"same_project_confirmed": False}, "same_project_not_confirmed"),
            ({"textbook_project_id": "proj_other_fixture"}, "same_project_not_confirmed"),
            ({"dedicated_image_key_confirmed": False}, "dedicated_image_key_not_confirmed"),
        ]
        for changes, code in cases:
            with self.subTest(changes=changes):
                self.assert_code(code, self.plan, settings=synthetic_settings(**changes))
        self.sender.assert_not_called()

    def test_different_settings_are_not_covered_by_approved_plan(self):
        plan = self.plan()
        altered = synthetic_settings(project_id="proj_other_fixture",
                                     textbook_project_id="proj_other_fixture")
        self.assert_code("settings_binding_mismatch", self.run_plan, plan, settings=altered)
        self.loader.assert_not_called()
        self.sender.assert_not_called()

    def test_counts_are_bounded_and_each_request_is_exactly_one_image(self):
        for count in (0, 5, -1, True, "2"):
            with self.subTest(count=count):
                self.assert_code("image_count_limit", self.plan, count=count)
        plan = self.plan(count=4)
        receipt = self.run_plan(plan)
        self.assertEqual(4, self.sender.call_count)
        self.assertEqual(4, len(receipt["attempts"]))
        for call in self.sender.call_args_list:
            self.assertEqual(1, call.args[0]["n"])
            self.assertNotIn("response_format", call.args[0])
            self.assertEqual(engine.MODEL, call.args[0]["model"])

    def test_modified_limit_cannot_be_bypassed_by_rehashing(self):
        plan = self.plan()
        plan.update(count=5, requests=5)
        rehash_plan(plan)
        self.assert_code("image_count_limit", self.run_plan, plan)
        self.sender.assert_not_called()

    def test_changed_cost_is_recomputed_before_dispatch(self):
        plan = self.plan()
        plan["cost"]["reserved_estimate_usd"] = "0.000001"
        rehash_plan(plan)
        self.assert_code("cost_changed", self.run_plan, plan)
        self.loader.assert_not_called()
        self.sender.assert_not_called()

    def test_source_check_failure_prevents_key_read_and_dispatch(self):
        plan = self.plan()
        def changed_source(_):
            raise engine.PipelineError("source_changed")
        self.assert_code("source_changed", self.run_plan, plan, source_check=changed_source)
        self.loader.assert_not_called()
        self.sender.assert_not_called()


class CredentialTests(OfflineCase):
    def test_textbook_key_is_never_a_fallback(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": FAKE_KEY}):
            self.assert_code("dedicated_key_missing_or_invalid", engine.load_key, self.settings)
            self.assert_code("dedicated_key_missing_or_invalid", self.run_plan, self.plan(),
                             key_loader=engine.load_key)
        self.sender.assert_not_called()

    def test_missing_dedicated_key_sends_nothing(self):
        self.assert_code("dedicated_key_missing_or_invalid", self.run_plan, self.plan(),
                         key_loader=engine.load_key)
        self.sender.assert_not_called()

    def test_anonymous_dedicated_environment_key_is_used_only_after_approval(self):
        with mock.patch.dict(os.environ, {"OPENAI_IMAGE_API_KEY": FAKE_KEY}):
            self.run_plan(self.plan(), key_loader=engine.load_key)
        self.assertEqual(FAKE_KEY, self.sender.call_args.args[1])
        self.assertEqual(PROJECT, self.sender.call_args.args[2])

    def test_keychain_is_read_only_fixed_and_fully_mocked(self):
        settings = synthetic_settings(key_source="keychain",
                                      keychain_service=engine.KEYCHAIN_SERVICE,
                                      keychain_account="anonymous-fixture")
        completed = mock.Mock(returncode=0, stdout=FAKE_KEY.encode(), stderr=b"")
        with mock.patch.object(engine.sys, "platform", "darwin"), \
                mock.patch.object(engine.subprocess, "run", return_value=completed) as run:
            self.assertEqual(FAKE_KEY, engine.load_key(settings))
        self.assertEqual(["/usr/bin/security", "find-generic-password", "-s",
                          engine.KEYCHAIN_SERVICE, "-a", "anonymous-fixture", "-w"],
                         run.call_args.args[0])
        self.assertEqual(30, run.call_args.kwargs["timeout"])

    def test_keychain_failure_does_not_disclose_stdout_or_stderr(self):
        settings = synthetic_settings(key_source="keychain",
                                      keychain_service=engine.KEYCHAIN_SERVICE,
                                      keychain_account="anonymous-fixture")
        completed = mock.Mock(returncode=1, stdout=FAKE_KEY.encode(), stderr=FAKE_KEY.encode())
        output = io.StringIO()
        with mock.patch.object(engine.sys, "platform", "darwin"), \
                mock.patch.object(engine.subprocess, "run", return_value=completed), \
                redirect_stdout(output), redirect_stderr(output):
            error = self.assert_code("keychain_unavailable", engine.load_key, settings)
        self.assertNotIn(FAKE_KEY, output.getvalue() + str(error))


class ExecutionTests(OfflineCase):
    def test_claim_and_dispatch_record_exist_before_network_seam(self):
        plan = self.plan()
        def observe_before_send(*_):
            receipt = self.receipt(plan)
            self.assertEqual("dispatch_started", receipt["status"])
            self.assertTrue(receipt["attempts"][0]["possible_charge"])
            return response_for(self.raw_png), "req_anonymous_fixture"
        self.sender.side_effect = observe_before_send
        receipt = self.run_plan(plan)
        self.assertEqual("candidates_received", receipt["status"])
        self.assertFalse(receipt["billing_total_known"])

    def test_unknown_attempt_never_retries_or_dispatches_remaining_images(self):
        failures = [
            TimeoutError("ANONYMOUS_PROVIDER_SECRET"),
            engine.SendError("provider_http_error", 429, "req_anonymous_fixture"),
            engine.SendError("provider_http_error", 500, "req_anonymous_fixture"),
            KeyboardInterrupt("ANONYMOUS_PROVIDER_SECRET"),
        ]
        for failure in failures:
            with self.subTest(error=type(failure).__name__):
                plan = self.plan(count=4)
                sender = mock.Mock(side_effect=failure)
                error = self.assert_code("outcome_unknown_inspect_receipt_no_retry",
                                         self.run_plan, plan, transport=sender)
                self.assertEqual(1, sender.call_count)
                receipt = self.receipt(plan)
                self.assertEqual("outcome_unknown", receipt["status"])
                self.assertEqual(1, len(receipt["attempts"]))
                self.assertEqual("outcome_unknown", receipt["attempts"][0]["state"])
                self.assertTrue(receipt["attempts"][0]["possible_charge"])
                self.assertNotIn("ANONYMOUS_PROVIDER_SECRET", json.dumps(receipt) + str(error))
                self.assert_code("plan_already_attempted_inspect_receipt", self.run_plan,
                                 plan, transport=sender)
                self.assertEqual(1, sender.call_count)

    def test_bad_base64_wrong_count_and_changed_dimensions_are_unknown(self):
        responses = [
            response_for(self.raw_png, data=[{"b64_json": "!not-base64!"}]),
            response_for(self.raw_png, data=[]),
            response_for(self.raw_png, data=[{}, {}]),
            response_for(self.raw_png, size="1024x1024"),
        ]
        for response in responses:
            with self.subTest(response_keys=list(response)):
                plan = self.plan(count=3)
                sender = mock.Mock(return_value=(response, "req_anonymous_fixture"))
                self.assert_code("outcome_unknown_inspect_receipt_no_retry", self.run_plan,
                                 plan, transport=sender)
                self.assertEqual(1, sender.call_count)
                self.assertEqual("outcome_unknown", self.receipt(plan)["status"])

    def test_candidate_save_failure_keeps_attempt_and_no_retry(self):
        plan = self.plan(count=3)
        original_write = engine.write_bytes
        def disk_failure(path, data, **kwargs):
            if path.name == "candidate-1.png":
                raise OSError("ANONYMOUS_DISK_FAILURE")
            return original_write(path, data, **kwargs)
        with mock.patch.object(engine, "write_bytes", side_effect=disk_failure):
            self.assert_code("outcome_unknown_inspect_receipt_no_retry", self.run_plan, plan)
        self.assertEqual(1, self.sender.call_count)
        self.assertEqual("outcome_unknown", self.receipt(plan)["status"])
        self.assert_code("plan_already_attempted_inspect_receipt", self.run_plan, plan)
        self.assertEqual(1, self.sender.call_count)

    def test_receipt_save_failure_after_post_keeps_durable_dispatch_claim(self):
        plan = self.plan(count=3)
        original_write = engine.write_json
        def disk_failure(path, data, **kwargs):
            if path.name == "receipt.json" and data["status"] != "prepared":
                if data["attempts"][0]["state"] != "dispatch_started":
                    raise OSError("ANONYMOUS_RECEIPT_DISK_FAILURE")
            return original_write(path, data, **kwargs)
        with mock.patch.object(engine, "write_json", side_effect=disk_failure):
            self.assert_code("outcome_unknown_inspect_receipt_no_retry", self.run_plan, plan)
        self.assertEqual("dispatch_started", self.receipt(plan)["status"])
        self.assertEqual(1, self.sender.call_count)
        self.assert_code("plan_already_attempted_inspect_receipt", self.run_plan, plan)
        self.assertEqual(1, self.sender.call_count)

    def test_successful_plan_cannot_be_sent_again(self):
        plan = self.plan()
        self.run_plan(plan)
        self.assert_code("plan_already_attempted_inspect_receipt", self.run_plan, plan)
        self.assertEqual(1, self.sender.call_count)
        self.assertEqual(1, self.loader.call_count)

    def test_missing_or_inconsistent_usage_stops_remaining_images(self):
        for usage in (None, {}, {"input_tokens_details": {"text_tokens": 1,
                       "image_tokens": 1}, "output_tokens": 2}):
            with self.subTest(usage=usage):
                plan = self.plan(count=4)
                sender = mock.Mock(return_value=(response_for(self.raw_png, usage=usage), None))
                receipt = self.run_plan(plan, transport=sender)
                self.assertEqual("stopped_usage_unknown", receipt["status"])
                self.assertEqual(3, receipt["unattempted_images"])
                self.assertEqual(1, sender.call_count)
                self.assertIsNone(receipt["attempts"][0]["usage_estimate_usd"])

    def test_observed_cost_overrun_stops_remaining_images(self):
        plan = self.plan(count=4)
        response = response_for(self.raw_png)
        response["usage"]["output_tokens"] = 100000
        self.sender.return_value = response, None
        receipt = self.run_plan(plan)
        self.assertEqual("stopped_cost_overrun", receipt["status"])
        self.assertEqual(3, receipt["unattempted_images"])
        self.assertEqual(1, self.sender.call_count)
        self.assertFalse(receipt["billing_total_known"])

    def test_concurrent_claim_allows_only_one_dispatch(self):
        plan = self.plan()
        barrier = threading.Barrier(2)
        def simultaneous_key_read(_):
            barrier.wait(timeout=10)
            return FAKE_KEY
        def invoke():
            try:
                return self.run_plan(plan, key_loader=simultaneous_key_read)["status"]
            except engine.PipelineError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: invoke(), range(2)))
        self.assertCountEqual(["candidates_received", "plan_already_attempted_inspect_receipt"],
                              results)
        self.assertEqual(1, self.sender.call_count)


class ImageAndReviewTests(OfflineCase):
    def test_normalization_checks_real_pixel_dimensions(self):
        encoded = base64.b64encode(png_bytes((64, 64))).decode()
        self.assert_code("image_dimensions_or_format", engine.normalize_png,
                         encoded, "1536x1024")

    def test_normalization_removes_text_exif_and_icc_metadata(self):
        raw = png_bytes(metadata=True)
        clean, original_hash = engine.normalize_png(base64.b64encode(raw).decode(),
                                                    "1536x1024")
        self.assertEqual(engine.sha256(raw), original_hash)
        with Image.open(io.BytesIO(clean)) as image:
            self.assertEqual((1536, 1024), image.size)
            self.assertEqual("RGB", image.mode)
            self.assertEqual({}, image.info)
        for marker in (b"ANONYMOUS_PRIVATE_COMMENT", b"ANONYMOUS_PRIVATE_EXIF",
                       b"ANONYMOUS_PRIVATE_ICC_METADATA"):
            self.assertNotIn(marker, clean)

    def approved_review(self, plan):
        self.run_plan(plan)
        record, _ = engine.candidate(self.root, plan, 1)
        return engine.review_candidate(self.root, plan, 1, record["sha256"], "approve",
                                       dict.fromkeys(engine.CHECKS, True),
                                       "Abstract anonymous article illustration")

    def test_incomplete_human_checks_do_not_approve(self):
        plan = self.plan()
        self.run_plan(plan)
        record, _ = engine.candidate(self.root, plan, 1)
        for missing in engine.CHECKS:
            with self.subTest(missing=missing):
                checks = dict.fromkeys(engine.CHECKS, True)
                checks[missing] = False
                self.assert_code("human_checks_required", engine.review_candidate,
                                 self.root, plan, 1, record["sha256"], "approve", checks,
                                 "Anonymous fixture")

    def test_candidate_change_invalidates_review_and_adoption_gate(self):
        plan = self.plan()
        review = self.approved_review(plan)
        self.assertTrue(engine.validate_review(self.root, plan, review).startswith(b"\x89PNG"))
        target = self.root / "runs" / plan["plan_id"] / "candidate-1.png"
        target.write_bytes(png_bytes(color=(190, 19, 39)))
        self.assert_code("candidate_changed", engine.validate_review, self.root, plan, review)
        self.assert_code("candidate_changed", engine.review_candidate, self.root, plan, 1,
                         review["image_sha256"], "approve", dict.fromkeys(engine.CHECKS, True),
                         "Anonymous fixture")

    def test_review_image_must_be_exactly_the_viewed_candidate(self):
        plan = self.plan()
        self.run_plan(plan)
        self.assert_code("review_image_mismatch", engine.review_candidate, self.root, plan,
                         1, "0" * 64, "approve", dict.fromkeys(engine.CHECKS, True),
                         "Anonymous fixture")

    def test_rejected_or_modified_review_cannot_pass_adoption_gate(self):
        plan = self.plan()
        review = self.approved_review(plan)
        changed = copy.deepcopy(review)
        changed["alt"] = "Changed after confirmation"
        self.assert_code("review_hash", engine.validate_review, self.root, plan, changed)
        record, _ = engine.candidate(self.root, plan, 1)
        rejected = engine.review_candidate(self.root, plan, 1, record["sha256"], "reject",
                                           dict.fromkeys(engine.CHECKS, False), "Rejected")
        self.assert_code("review_not_approved", engine.validate_review, self.root, plan, rejected)
        self.assert_code("review_superseded", engine.validate_review, self.root, plan, review)

    def test_candidate_cannot_move_to_another_workspace(self):
        plan = self.plan()
        self.run_plan(plan)
        identity = engine.read_json(self.root / "workspace.json")
        identity["id"] = "1" * 64
        engine.write_json(self.root / "workspace.json", identity)
        self.assert_code("workspace_mismatch", engine.candidate, self.root, plan, 1)


class WorkspaceTests(OfflineCase):
    def test_repository_workspace_is_refused(self):
        repo = self.tempdir / "anonymous-repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        self.assert_code("workspace_inside_repository", engine.workspace, repo / "private")
        explicit_repo = self.tempdir / "source-without-git"
        explicit_repo.mkdir()
        self.assert_code("workspace_inside_repository", engine.workspace,
                         explicit_repo / "private", explicit_repo)

    def test_lexical_parent_traversal_does_not_hide_repository_workspace(self):
        repo = self.tempdir / "source-without-git"
        repo.mkdir()
        outside = self.tempdir / "outside"
        outside.mkdir()
        ambiguous = outside / ".." / repo.name / "private"
        self.assert_code("workspace_inside_repository", engine.workspace, ambiguous, repo)

    def test_workspace_and_candidate_symlinks_are_refused(self):
        link = self.tempdir / "linked-private"
        link.symlink_to(self.root, target_is_directory=True)
        self.assert_code("symlink_refused", engine.workspace, link)
        plan = self.plan()
        self.run_plan(plan)
        target = self.root / "runs" / plan["plan_id"] / "candidate-1.png"
        elsewhere = self.tempdir / "anonymous.png"
        elsewhere.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(elsewhere)
        self.assert_code("symlink_refused", engine.candidate, self.root, plan, 1)


class TransportTests(OfflineCase):
    def fake_connection(self, status=200, payload=None, request_id="req_anonymous_fixture"):
        connection = mock.Mock()
        connection.sock = mock.Mock()
        response = mock.Mock(status=status)
        response.getheader.return_value = request_id
        raw = engine.canonical(payload if payload is not None else {"data": []})
        source = io.BytesIO(raw)
        response.read.side_effect = source.read
        connection.getresponse.return_value = response
        return connection, response

    def test_real_transport_uses_fixed_tls_origin_and_single_post(self):
        connection, _ = self.fake_connection()
        with mock.patch.object(engine.http.client, "HTTPSConnection", return_value=connection) as create:
            result, request_id = engine.OpenAITransport()({"n": 1}, FAKE_KEY, PROJECT,
                                                        "anonymous-attempt")
        self.assertEqual("api.openai.com", create.call_args.args[0])
        self.assertEqual(180, create.call_args.kwargs["timeout"])
        self.assertEqual(1, connection.request.call_count)
        call = connection.request.call_args
        self.assertEqual(("POST", "/v1/images/generations"), call.args)
        self.assertEqual("Bearer " + FAKE_KEY, call.kwargs["headers"]["Authorization"])
        self.assertEqual(PROJECT, call.kwargs["headers"]["OpenAI-Project"])
        self.assertEqual({"data": []}, result)
        self.assertEqual("req_anonymous_fixture", request_id)
        connection.close.assert_called_once()

    def test_redirect_429_and_500_never_follow_or_read_provider_error_body(self):
        for status in (301, 302, 307, 308, 429, 500):
            with self.subTest(status=status):
                connection, response = self.fake_connection(status, {"error": FAKE_KEY})
                output = io.StringIO()
                with mock.patch.object(engine.http.client, "HTTPSConnection", return_value=connection), \
                        redirect_stdout(output), redirect_stderr(output):
                    error = self.assert_code("provider_http_error", engine.OpenAITransport(),
                                             {"n": 1}, FAKE_KEY, PROJECT, "anonymous-attempt")
                self.assertEqual(status, error.status)
                connection.request.assert_called_once()
                response.read.assert_not_called()
                connection.close.assert_called_once()
                self.assertNotIn(FAKE_KEY, str(error) + output.getvalue())

    def test_transport_timeout_and_malformed_json_are_sanitized(self):
        for phase in ("timeout", "json"):
            with self.subTest(phase=phase):
                connection, response = self.fake_connection()
                if phase == "timeout":
                    connection.getresponse.side_effect = TimeoutError(FAKE_KEY)
                    expected = "transport_outcome_unknown"
                else:
                    response.read.side_effect = [FAKE_KEY.encode(), b""]
                    expected = "response_invalid"
                output = io.StringIO()
                with mock.patch.object(engine.http.client, "HTTPSConnection", return_value=connection), \
                        redirect_stdout(output), redirect_stderr(output):
                    error = self.assert_code(expected, engine.OpenAITransport(),
                                             {"n": 1}, FAKE_KEY, PROJECT, "anonymous-attempt")
                connection.request.assert_called_once()
                self.assertNotIn(FAKE_KEY, str(error) + output.getvalue())
                connection.close.assert_called_once()

    def test_secret_like_request_identifier_is_not_retained(self):
        for invalid_id in (FAKE_KEY, "req_" + FAKE_KEY):
            with self.subTest(prefix=invalid_id[:3]):
                connection, _ = self.fake_connection(request_id=invalid_id)
                with mock.patch.object(engine.http.client, "HTTPSConnection", return_value=connection):
                    _, request_id = engine.OpenAITransport()({"n": 1}, FAKE_KEY, PROJECT,
                                                            "anonymous-attempt")
                self.assertIsNone(request_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
