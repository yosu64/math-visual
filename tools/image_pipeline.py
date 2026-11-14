"""Small, reusable, explicitly approved image-generation engine.

This module has no knowledge of Org, websites, SVG owners, or publication.
Only OpenAITransport sends a request. Nothing retries a request.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import datetime as dt
import decimal
import hashlib
import http.client
import fcntl
import io
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import subprocess
import sys
import time
import warnings


MODEL = "gpt-image-2.5-flare-2026-09-08"
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 30 * 1024 * 1024
MAX_PROMPT_BYTES = 12000
QUALITIES = ("low", "medium", "high")
SIZES = ("1024x1024", "1536x1024", "1024x1536")
PRICE_SOURCE = "https://developers.openai.com/api/docs/guides/image-generation#calculating-costs"
KEYCHAIN_SERVICE = "org.yosu.openai.images"
CHECKS = ("viewed_image", "matches_article", "math_not_misleading",
          "no_private_or_textbook_material", "alt_checked")
HEX = re.compile(r"[a-f0-9]{64}\Z")
SECRET = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
D = decimal.Decimal


class PipelineError(Exception):
    """A fixed, safe code: never interpolate a provider error or a secret."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SendError(PipelineError):
    def __init__(self, code, status=None, request_id=None):
        super().__init__(code)
        self.status = status
        self.request_id = request_id


def require(condition, code):
    if not condition:
        raise PipelineError(code)


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def day(value):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise PipelineError("invalid_date") from None


def money(value):
    require(isinstance(value, (str, int)) and not isinstance(value, bool), "invalid_money")
    try:
        result = D(value)
    except decimal.InvalidOperation:
        raise PipelineError("invalid_money") from None
    require(result.is_finite() and 0 < result <= 1000, "invalid_money")
    return result


def usd(value):
    return str(value.quantize(D("0.000001"), rounding=decimal.ROUND_CEILING))


def text_field(value, limit=4000):
    require(isinstance(value, str) and 0 < len(value) <= limit, "invalid_text")
    require(not SECRET.search(value), "secret_like_text")
    require(all(ord(c) >= 32 or c in "\n\t" for c in value), "invalid_text")
    return value


def no_symlinks(path: Path):
    path = path.absolute()
    for part in (path, *path.parents):
        require(not part.is_symlink(), "symlink_refused")


def private_dir(path: Path):
    no_symlinks(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(path.is_dir() and path.stat().st_uid == os.getuid(), "private_directory_required")
    require(path.stat().st_mode & 0o077 == 0, "private_directory_permissions")


def fsync_directory(path: Path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_bytes(path: Path, data: bytes, *, exclusive=False, mode=0o600):
    """Durable create/replace; never follow symlinks or truncate another file."""
    no_symlinks(path)
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        temporary = path.with_name("." + path.name + "." + secrets.token_hex(8))
        try:
            write_bytes(temporary, data, exclusive=True, mode=mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    fsync_directory(path.parent)


@contextmanager
def file_lock(path: Path):
    """Local macOS/Linux process lock; no stale PID-based lock recovery."""
    no_symlinks(path)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise PipelineError("operation_busy") from None
        yield
    finally:
        os.close(fd)


def write_json(path: Path, value, **kwargs):
    write_bytes(path, canonical(value) + b"\n", **kwargs)


def read_json(path: Path, limit=1024 * 1024):
    no_symlinks(path)
    require(path.is_file() and path.stat().st_size <= limit, "json_file_invalid")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(_):
        raise PipelineError("invalid_json_number")

    try:
        return json.loads(path.read_bytes(), object_pairs_hook=pairs,
                          parse_constant=invalid_constant)
    except (ValueError, UnicodeError):
        raise PipelineError("invalid_json") from None


def workspace(path: Path, repo: Path | None = None):
    path = path.expanduser().absolute()
    no_symlinks(path)
    path = path.resolve()
    if repo:
        require(not path.is_relative_to(repo.resolve()), "workspace_inside_repository")
    require(not any((p / ".git").exists() for p in (path, *path.parents)),
            "workspace_inside_repository")
    private_dir(path)
    identity = path / "workspace.json"
    if not identity.exists():
        try:
            write_json(identity, {"schema": "image-workspace/v1",
                                 "id": secrets.token_hex(32)}, exclusive=True)
        except FileExistsError:
            pass
    record = read_json(identity)
    require(record.get("schema") == "image-workspace/v1" and
            HEX.fullmatch(record.get("id", "")), "invalid_workspace")
    for name in ("plans", "runs", "reviews", "previews"):
        private_dir(path / name)
    return path, record["id"]


def validate_settings(settings):
    fields = {"schema", "project_id", "textbook_project_id", "same_project_confirmed",
              "dedicated_image_key_confirmed", "key_source", "keychain_account",
              "keychain_service"}
    require(isinstance(settings, dict) and set(settings) <= fields, "settings_fields")
    require(settings.get("schema") == "image-settings/v1", "settings_schema")
    project = settings.get("project_id")
    require(isinstance(project, str) and
            re.fullmatch(r"proj_[A-Za-z0-9_-]{8,100}", project), "project_required")
    require(project == settings.get("textbook_project_id") and
            settings.get("same_project_confirmed") is True, "same_project_not_confirmed")
    require(settings.get("dedicated_image_key_confirmed") is True,
            "dedicated_image_key_not_confirmed")
    require(settings.get("key_source") in ("environment", "keychain"), "key_source")
    if settings["key_source"] == "keychain":
        require(settings.get("keychain_service") == KEYCHAIN_SERVICE,
                "dedicated_keychain_service_required")
        account = settings.get("keychain_account")
        require(isinstance(account, str) and re.fullmatch(r"[A-Za-z0-9_.@-]{1,100}", account),
                "keychain_account")
    return digest(settings)


def load_key(settings):
    """Read only after charge approval. Never create or change a Keychain item."""
    validate_settings(settings)
    if settings["key_source"] == "environment":
        value = os.environ.get("OPENAI_IMAGE_API_KEY", "")
    else:
        require(sys.platform == "darwin", "keychain_requires_macos")
        try:
            result = subprocess.run(
                ["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
                 "-a", settings["keychain_account"], "-w"],
                capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise PipelineError("keychain_unavailable") from None
        require(result.returncode == 0, "keychain_unavailable")
        try:
            value = result.stdout.decode("ascii").strip()
        except UnicodeError:
            raise PipelineError("key_invalid") from None
    require(isinstance(value, str) and re.fullmatch(r"sk-[A-Za-z0-9_-]{16,500}", value),
            "dedicated_key_missing_or_invalid")
    return value


def quote(profile, prompt, count, quality, size, *, today=None):
    """An estimate, not an API-enforced dollar ceiling."""
    require(isinstance(profile, dict) and profile.get("schema") == "image-price-quote/v1",
            "price_schema")
    require(set(profile) == {
        "schema", "model", "quality", "size", "output_format", "background",
        "text_input_usd_per_million", "image_output_usd_per_million",
        "output_image_estimate_usd", "source_url", "verified_at", "valid_until",
        "operator_verified",
    }, "price_fields")
    require(profile.get("model") == MODEL and profile.get("quality") == quality
            and profile.get("size") == size and profile.get("output_format") == "png"
            and profile.get("background") == "opaque", "price_parameters_mismatch")
    require(profile.get("operator_verified") is True, "price_not_verified")
    require(profile.get("source_url") == PRICE_SOURCE, "price_source")
    today = today or dt.datetime.now(dt.timezone.utc).date()
    verified, expiry = day(profile.get("verified_at")), day(profile.get("valid_until"))
    require(verified <= today <= expiry and (expiry - verified).days <= 14,
            "price_expired_or_invalid")
    input_rate = money(profile.get("text_input_usd_per_million"))
    output_rate = money(profile.get("image_output_usd_per_million"))
    output = money(profile.get("output_image_estimate_usd"))
    # UTF-8 bytes plus an allowance is a deliberately conservative allocation,
    # not a claim that the server's tokenization is known exactly.
    input_allocation = len(prompt.encode("utf-8")) + 1024
    input_estimate = D(input_allocation) * input_rate / D(1000000)
    per_image = input_estimate + output
    return {
        "status": "verified_estimate", "currency": "USD", "image_count": count,
        "input_token_allocation_per_request": input_allocation,
        "input_estimate_per_request_usd": usd(input_estimate),
        "output_estimate_per_image_usd": usd(output),
        "total_estimate_usd": usd(per_image * count),
        "reserved_estimate_usd": usd(per_image * count * D("1.25")),
        "contingency_factor": "1.25",
        "is_enforced_billing_cap": False,
        "text_input_usd_per_million": str(input_rate),
        "image_output_usd_per_million": str(output_rate),
        "profile_sha256": digest(profile),
    }


def make_plan(*, workspace_id, subject, prompt, review_checks, count=1,
              quality="low", size="1536x1024", price_profile=None,
              budget_usd=None, settings=None):
    require(HEX.fullmatch(workspace_id or ""), "invalid_workspace")
    require(type(count) is int and 1 <= count <= MAX_IMAGES, "image_count_limit")
    require(quality in QUALITIES and size in SIZES, "unsupported_parameters")
    text_field(prompt, MAX_PROMPT_BYTES)
    require(len(prompt.encode("utf-8")) <= MAX_PROMPT_BYTES, "prompt_too_large")
    require(isinstance(subject, dict) and subject.get("adapter") and subject.get("id"),
            "subject_required")
    require(not SECRET.search(canonical(subject).decode("utf-8")), "secret_like_text")
    require(isinstance(review_checks, list) and 1 <= len(review_checks) <= 12,
            "review_checks_required")
    for item in review_checks:
        text_field(item, 1000)
    cost = {"status": "unverified", "currency": "USD", "image_count": count,
            "total_estimate_usd": None, "reserved_estimate_usd": None,
            "is_enforced_billing_cap": False}
    if price_profile:
        cost = quote(price_profile, prompt, count, quality, size)
    if budget_usd is not None:
        budget = money(budget_usd)
        if cost["reserved_estimate_usd"] is not None:
            require(budget >= D(cost["reserved_estimate_usd"]), "budget_below_estimate")
        budget_usd = usd(budget)
    plan = {
        "schema": "image-plan/v1", "created_at": now(),
        "nonce": secrets.token_hex(16), "workspace_id": workspace_id,
        "subject": subject, "prompt": prompt, "review_checks": review_checks,
        "model": MODEL, "quality": quality, "size": size, "output_format": "png",
        "background": "opaque", "count": count, "requests": count, "n_per_request": 1,
        "price_profile": price_profile, "cost": cost, "budget_usd": budget_usd,
        "settings_sha256": validate_settings(settings) if settings else None,
    }
    plan["plan_id"] = digest(plan)
    return plan


def validate_plan(plan):
    require(isinstance(plan, dict) and plan.get("schema") == "image-plan/v1", "plan_schema")
    body = {k: v for k, v in plan.items() if k != "plan_id"}
    require(HEX.fullmatch(plan.get("plan_id", "")) and
            digest(body) == plan["plan_id"], "plan_hash_mismatch")
    require(plan.get("model") == MODEL and plan.get("quality") in QUALITIES
            and plan.get("size") in SIZES and plan.get("background") == "opaque"
            and plan.get("output_format") == "png", "unsupported_parameters")
    require(type(plan.get("count")) is int and 1 <= plan["count"] <= MAX_IMAGES
            and plan.get("requests") == plan["count"] and plan.get("n_per_request") == 1,
            "image_count_limit")
    require(len(text_field(plan.get("prompt"), MAX_PROMPT_BYTES).encode("utf-8"))
            <= MAX_PROMPT_BYTES, "prompt_too_large")
    return plan["plan_id"]


def safe_request_id(value):
    if (isinstance(value, str) and re.fullmatch(r"req_[A-Za-z0-9_-]{8,120}", value)
            and not SECRET.search(value)):
        return value
    return None


class OpenAITransport:
    """One TLS POST, fixed origin, no proxy, redirect, SDK retry, or URL download."""

    def __call__(self, body, key, project, client_id):
        connection = http.client.HTTPSConnection(
            "api.openai.com", timeout=180, context=ssl.create_default_context())
        request_id = None
        deadline = time.monotonic() + 180
        try:
            connection.request("POST", "/v1/images/generations", body=canonical(body),
                               headers={"Content-Type": "application/json",
                                        "Authorization": "Bearer " + key,
                                        "OpenAI-Project": project,
                                        "X-Client-Request-Id": client_id})
            response = connection.getresponse()
            request_id = safe_request_id(response.getheader("x-request-id"))
            if response.status != 200:
                # Do not read, store, print, or propagate the provider error body.
                raise SendError("provider_http_error", response.status, request_id)
            data = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                if connection.sock:
                    connection.sock.settimeout(min(remaining, 30))
                chunk = response.read(min(65536, MAX_RESPONSE_BYTES + 1 - len(data)))
                data.extend(chunk)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise SendError("response_too_large", 200, request_id)
                if not chunk:
                    break
            result = json.loads(data)
            require(isinstance(result, dict), "response_invalid")
            return result, request_id
        except SendError:
            raise
        except (TimeoutError, OSError, http.client.HTTPException):
            raise SendError("transport_outcome_unknown", request_id=request_id) from None
        except (ValueError, PipelineError):
            raise SendError("response_invalid", request_id=request_id) from None
        finally:
            connection.close()


def image_decoder_available():
    try:
        from PIL import Image
        return Image
    except ImportError:
        raise PipelineError("pillow_required_before_generation") from None


def normalize_png(encoded, size):
    """Validate pixels, bound dimensions, and omit incidental PNG text metadata."""
    Image = image_decoder_available()
    require(isinstance(encoded, str) and len(encoded) <= MAX_IMAGE_BYTES * 4 // 3 + 8,
            "image_payload_invalid")
    try:
        raw = base64.b64decode(encoded, validate=True)
        require(len(raw) <= MAX_IMAGE_BYTES and raw.startswith(b"\x89PNG\r\n\x1a\n"),
                "image_format_invalid")
        expected = tuple(map(int, size.split("x")))
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with Image.open(io.BytesIO(raw)) as source:
                require(source.format == "PNG" and source.size == expected,
                        "image_dimensions_or_format")
                source.verify()
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                pixels = source.convert("RGB")
                pixels.info.clear()
                output = io.BytesIO()
                pixels.save(output, format="PNG")
                clean = output.getvalue()
        require(len(clean) <= MAX_IMAGE_BYTES, "image_too_large")
        return clean, sha256(raw)
    except PipelineError:
        raise
    except Exception:
        raise PipelineError("image_decode_failed") from None


def usage_summary(response, profile):
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return None, None
    details = usage.get("input_tokens_details")
    if not isinstance(details, dict):
        return None, None
    numbers = [details.get("text_tokens"), details.get("image_tokens"),
               usage.get("output_tokens")]
    if not all(type(n) is int and 0 <= n <= 10000000 for n in numbers):
        return None, None
    if numbers[1] != 0:
        return None, None  # No input images are sent by this version.
    cost = (D(numbers[0]) * money(profile["text_input_usd_per_million"])
            + D(numbers[2]) * money(profile["image_output_usd_per_million"])) / D(1000000)
    return dict(zip(("text_input_tokens", "image_input_tokens", "output_tokens"), numbers)), usd(cost)


def generate(plan, root, workspace_id, settings, confirm_plan, approve_charge, *,
             transport=None, key_loader=load_key, source_check=None):
    """Execute a plan ONCE. A started directory is never reused or auto-removed."""
    plan_id = validate_plan(plan)
    require(confirm_plan == plan_id and approve_charge is True, "charge_approval_required")
    require(plan["workspace_id"] == workspace_id, "workspace_mismatch")
    require(plan["settings_sha256"] == validate_settings(settings), "settings_binding_mismatch")
    expected_cost = quote(plan["price_profile"], plan["prompt"], plan["count"],
                          plan["quality"], plan["size"])
    require(expected_cost == plan["cost"], "cost_changed")
    budget = money(plan.get("budget_usd"))
    require(budget >= D(expected_cost["reserved_estimate_usd"]), "budget_below_estimate")
    image_decoder_available()
    if source_check:
        source_check(plan)
    root, actual_workspace = workspace(root)
    require(workspace_id == actual_workspace, "workspace_mismatch")
    run = root / "runs" / plan_id
    no_symlinks(run)
    require(not run.exists(), "plan_already_attempted_inspect_receipt")
    key = key_loader(settings)
    try:
        run.mkdir(mode=0o700)  # atomic claim, before any request
    except FileExistsError:
        raise PipelineError("plan_already_attempted_inspect_receipt") from None
    fsync_directory(run.parent)
    receipt = {
        "schema": "image-run/v1", "plan_id": plan_id, "started_at": now(),
        "provider": "openai", "status": "prepared", "attempts": [],
        "reserved_estimate_usd": expected_cost["reserved_estimate_usd"],
        "budget_usd": plan["budget_usd"], "billing_total_known": False,
    }
    write_json(run / "receipt.json", receipt)
    sender = transport or OpenAITransport()
    known_cost = D(0)
    for index in range(1, plan["count"] + 1):
        attempt = {"index": index, "client_request_id": secrets.token_hex(16),
                   "state": "dispatch_started", "started_at": now(),
                   "possible_charge": True, "candidate": None}
        receipt["attempts"].append(attempt)
        receipt["status"] = "dispatch_started"
        write_json(run / "receipt.json", receipt)  # durable BEFORE network
        try:
            body = {key: plan[key] for key in ("model", "prompt", "quality", "size",
                                               "output_format", "background")}
            body["n"] = 1
            response, request_id = sender(body, key, settings["project_id"],
                                          attempt["client_request_id"])
            attempt["request_id"] = safe_request_id(request_id)
            data = response.get("data")
            require(isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict),
                    "response_image_count")
            for field in ("size", "quality", "output_format", "background"):
                if field in response:
                    require(response[field] == plan[field], "response_parameters_mismatch")
            clean, original_hash = normalize_png(data[0].get("b64_json"), plan["size"])
            filename = f"candidate-{index}.png"
            write_bytes(run / filename, clean, exclusive=True)
            usage, actual_cost = usage_summary(response, plan["price_profile"])
            attempt.update(state="candidate_received", finished_at=now(),
                           candidate=filename, sha256=sha256(clean),
                           received_image_sha256=original_hash, usage=usage,
                           usage_estimate_usd=actual_cost)
            if actual_cost is None:
                receipt["status"] = "stopped_usage_unknown"
            else:
                known_cost += D(actual_cost)
                receipt["known_usage_estimate_usd"] = usd(known_cost)
                per_image_reserve = D(expected_cost["reserved_estimate_usd"]) / plan["count"]
                if D(actual_cost) > per_image_reserve or known_cost > budget:
                    receipt["status"] = "stopped_cost_overrun"
                else:
                    receipt["status"] = "in_progress"
            write_json(run / "receipt.json", receipt)
            if receipt["status"].startswith("stopped_"):
                break
        except BaseException as error:
            # Includes a Ctrl-C after a POST and a failure while saving its result.
            attempt["state"] = "outcome_unknown"
            attempt["finished_at"] = now()
            attempt["error_code"] = error.code if isinstance(error, PipelineError) else "interrupted_or_local_error"
            if isinstance(error, SendError):
                attempt["http_status"] = error.status
                attempt["request_id"] = safe_request_id(error.request_id)
            receipt["status"] = "outcome_unknown"
            try:
                write_json(run / "receipt.json", receipt)
            except OSError:
                pass  # The durable dispatch_started record still bars a retry.
            raise PipelineError("outcome_unknown_inspect_receipt_no_retry") from None
    if receipt["status"] == "in_progress":
        receipt["status"] = "candidates_received"
        receipt["billing_total_known"] = False  # Usage is not a billing receipt.
    receipt["finished_at"] = now()
    receipt["unattempted_images"] = plan["count"] - len(receipt["attempts"])
    write_json(run / "receipt.json", receipt)
    return receipt


def candidate(root, plan, index):
    plan_id = validate_plan(plan)
    identity = read_json(root / "workspace.json")
    require(identity.get("id") == plan["workspace_id"], "workspace_mismatch")
    require(type(index) is int and 1 <= index <= plan["count"], "candidate_index")
    receipt = read_json(root / "runs" / plan_id / "receipt.json")
    require(receipt.get("schema") == "image-run/v1" and receipt.get("plan_id") == plan_id,
            "receipt_binding")
    records = [x for x in receipt.get("attempts", []) if x.get("index") == index]
    require(len(records) == 1 and records[0].get("state") == "candidate_received",
            "candidate_not_received")
    record = records[0]
    name = f"candidate-{index}.png"
    require(record.get("candidate") == name, "candidate_path")
    path = root / "runs" / plan_id / name
    no_symlinks(path)
    require(path.is_file() and path.stat().st_size <= MAX_IMAGE_BYTES, "candidate_missing")
    data = path.read_bytes()
    require(sha256(data) == record.get("sha256"), "candidate_changed")
    return record, data


def review_candidate(root, plan, index, image_sha256, decision, checks, alt):
    record, data = candidate(root, plan, index)
    require(image_sha256 == record["sha256"], "review_image_mismatch")
    require(decision in ("approve", "reject"), "review_decision")
    require(isinstance(checks, dict) and set(checks) == set(CHECKS), "review_checks")
    if decision == "approve":
        require(all(checks[k] is True for k in CHECKS), "human_checks_required")
    review = {
        "schema": "image-review/v1", "plan_id": plan["plan_id"],
        "candidate_index": index, "image_sha256": sha256(data),
        "subject_sha256": digest(plan["subject"]), "decision": decision,
        "checks": checks, "alt": text_field(alt, 240), "reviewed_at": now(),
    }
    review["review_id"] = digest(review)
    with file_lock(review_lock_path(root, plan, index)):
        write_json(root / "reviews" / (review["review_id"] + ".json"), review, exclusive=True)
        write_json(review_current_path(root, plan, index),
                   {"review_id": review["review_id"]})
    return review


def review_lock_path(root, plan, index):
    return root / "reviews" / f"{plan['plan_id']}-{index}.lock"


def review_current_path(root, plan, index):
    return root / "reviews" / f"{plan['plan_id']}-{index}-current.json"


def validate_review(root, plan, review):
    require(review.get("schema") == "image-review/v1" and
            review.get("review_id") == digest({k: v for k, v in review.items()
                                               if k != "review_id"}), "review_hash")
    require(review.get("plan_id") == plan["plan_id"] and
            review.get("subject_sha256") == digest(plan["subject"]), "review_binding")
    require(review.get("decision") == "approve" and
            all(review.get("checks", {}).get(k) is True for k in CHECKS), "review_not_approved")
    current = read_json(review_current_path(root, plan, review.get("candidate_index")))
    require(current.get("review_id") == review["review_id"], "review_superseded")
    record, data = candidate(root, plan, review.get("candidate_index"))
    require(record["sha256"] == review.get("image_sha256"), "review_image_mismatch")
    text_field(review.get("alt"), 240)
    return data
