#!/usr/bin/env python3
"""Local CLI and math-visual adapter for the reusable image pipeline."""
from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path, PurePosixPath
import re
import secrets
import subprocess
import sys

import image_pipeline as engine


DEFAULT_REPO = Path(__file__).resolve().parent.parent
STYLE = (
    "Create an original editorial illustration for a Japanese high-school mathematics "
    "article entry card. It is an invitation to explore the article, never a mathematical "
    "explanation or a proof. Warm ivory background, restrained teal and amber, tactile "
    "paper or ceramic forms, a clear subject, calm lighting, generous margins. "
    "No text, letters, numerals, equations, coordinate axes, labeled graphs, textbook "
    "pages, screenshots, logos, people, or watermarks. Do not depict exact mathematical "
    "claims or invent data. Do not imitate an existing textbook illustration.\n"
)


def article_file(repo, name):
    engine.require(isinstance(name, str) and name.startswith("./"), "article_path")
    parts = PurePosixPath(name[2:]).parts
    engine.require(len(parts) >= 2 and parts[0] in
                   ("math-i", "math-ii", "math-iii", "math-a", "math-b", "math-c")
                   and name == "./" + "/".join(parts)
                   and all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) and p not in (".", "..")
                           for p in parts) and parts[-1].endswith(".html"), "article_path")
    path = repo.joinpath(*parts)
    engine.no_symlinks(path)
    engine.require(path.is_file() and path.resolve().is_relative_to(repo.resolve()),
                   "article_missing")
    return path


def repository(repo):
    repo = Path(repo).expanduser().absolute()
    engine.no_symlinks(repo)
    repo = repo.resolve()
    engine.no_symlinks(repo / "index.org")
    engine.no_symlinks(repo / "tools/math-visual-build.el")
    engine.require((repo / "index.org").is_file() and
                   (repo / "tools/math-visual-build.el").is_file(), "repository_required")
    return repo


def index_hash(repo):
    source = repo / "index.org"
    engine.no_symlinks(source)
    return engine.sha256(source.read_bytes())


def export_inventory(repo, root, emacs):
    """Use the existing Org AST parser. Do not parse notes or crawl article HTML."""
    output = root / "inventory.json"
    temporary = root / ("inventory-" + secrets.token_hex(12) + ".json")
    source = repo / "index.org"
    engine.no_symlinks(repo / "tools/math-visual-build.el")
    before = index_hash(repo)
    engine.no_symlinks(output)
    expression = "(math-visual-build-image-inventory %s %s)" % (
        json.dumps(str(source), ensure_ascii=False), json.dumps(str(temporary), ensure_ascii=False))
    try:
        result = subprocess.run(
            [emacs, "-Q", "--batch", "-L", str(repo / "tools"),
             "-l", str(repo / "tools/math-visual-build.el"), "--eval", expression],
            capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise engine.PipelineError("emacs_inventory_unavailable") from None
    engine.require(result.returncode == 0, "inventory_export_failed")
    after = index_hash(repo)
    engine.require(before == after, "source_changed_during_inventory")
    inventory = engine.read_json(temporary)
    engine.require(inventory.get("schema") == "math-visual-image-inventory/v1",
                   "inventory_schema")
    inventory["index_sha256"] = after
    engine.write_json(output, inventory)
    temporary.unlink()
    return inventory


def load_briefs(repo):
    return engine.read_json(repo / "tools/imagegen-config/math-visual-briefs.json")


def source_check(repo, plan):
    subject = plan.get("subject", {})
    engine.require(subject.get("adapter") == "math-visual", "adapter_not_supported")
    article = article_file(repo, subject.get("id"))
    engine.require(engine.sha256(article.read_bytes()) == subject.get("article_sha256"),
                   "article_changed_replan_and_review")
    engine.require(index_hash(repo) == subject.get("index_sha256"),
                   "index_changed_replan_and_review")
    briefs = load_briefs(repo)
    matches = [x for x in briefs.get("articles", []) if x.get("path") == subject["id"]]
    engine.require(len(matches) == 1 and engine.digest(matches[0]) == subject.get("brief_sha256"),
                   "brief_changed_replan_and_review")


def make_math_plan(repo, inventory, briefs, article, workspace_id, **options):
    engine.require(inventory.get("schema") == "math-visual-image-inventory/v1"
                   and briefs.get("schema") == "math-visual-image-briefs/v1", "adapter_schema")
    engine.require(inventory.get("index_sha256") == index_hash(repo), "inventory_stale")
    metadata = [x for x in inventory.get("articles", []) if x.get("path") == article]
    proposals = [x for x in briefs.get("articles", []) if x.get("path") == article]
    engine.require(len(metadata) == 1 and len(proposals) == 1, "article_mapping_not_unique")
    item, brief = metadata[0], proposals[0]
    actual_hash = engine.sha256(article_file(repo, article).read_bytes())
    engine.require(item.get("article_sha256") == brief.get("article_sha256") == actual_hash,
                   "article_changed_replan_and_review")
    engine.require(item.get("title") == brief.get("title"), "brief_title_mismatch")
    subject = {
        "adapter": "math-visual", "id": article, "article_sha256": actual_hash,
        "index_sha256": inventory["index_sha256"], "brief_sha256": engine.digest(brief),
        "title": engine.text_field(item["title"], 300),
        "public_summary": engine.text_field(brief["public_summary"]),
        "alt_suggestion": engine.text_field(brief["alt"], 240),
    }
    prompt = STYLE + "Article theme: " + subject["public_summary"] + "\nVisual concept: " + (
        engine.text_field(brief["visual_brief"]))
    return engine.make_plan(workspace_id=workspace_id, subject=subject, prompt=prompt,
                            review_checks=brief["review_checks"], **options)


def review_page(root, plan, repo):
    source_check(repo, plan)
    title = html.escape(plan["subject"]["title"])
    summary = html.escape(plan["subject"]["public_summary"])
    cards = []
    for index in range(1, plan["count"] + 1):
        try:
            record, data = engine.candidate(root, plan, index)
        except engine.PipelineError as error:
            if error.code in ("candidate_not_received", "json_file_invalid"):
                continue
            raise
        encoded = base64.b64encode(data).decode("ascii")
        cards.append(
            '<section><h2>候補 %d</h2><img src="data:image/png;base64,%s" '
            'alt="未確認の候補画像 %d"><p>画像 SHA-256</p><code>%s</code></section>'
            % (index, encoded, index, record["sha256"]))
    engine.require(cards, "no_candidates_to_review")
    checks = "".join("<li>" + html.escape(c) + "</li>" for c in plan["review_checks"])
    document = """<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>画像候補の確認 — %s</title>
<style>body{font:17px/1.7 system-ui,sans-serif;max-width:1000px;margin:auto;padding:24px;background:#faf8f2;color:#243438}
section{border:1px solid #ccd4cf;border-radius:18px;padding:20px;margin:24px 0;background:white}
img{display:block;max-width:100%%;height:auto;margin:auto}code{overflow-wrap:anywhere;font-size:13px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}a{color:#075b69}h1{line-height:1.3}</style>
<h1>%s</h1><p>未採用の画像候補です。教材の説明図として使えるかを保証するものではありません。</p>
<p>%s</p><p><a href="%s" target="_blank" rel="noopener">対象の記事を開いて比較する</a></p>
<h2>本人の確認項目</h2><ul>%s</ul>
<p>実画像を見て、記事との対応、数学的な誤解、教科書・教師用注記・私的情報の混入、代替テキストを確認してください。</p>
%s<h2>計画</h2><p>計画 ID: <code>%s</code></p><p>モデル: %s / 品質: %s / サイズ: %s / 予定枚数: %d</p>
<p>事前見積り（USD）: %s。請求額の保証上限ではありません。</p>
<details><summary>送信する画像案</summary><pre>%s</pre></details>
<p>この画面を開くだけでは採用されません。確認後に review コマンドで採否を記録し、adopt コマンドで採用します。</p>
</html>""" % (
        title, title, summary, html.escape(article_file(repo, plan["subject"]["id"]).as_uri(), quote=True),
        checks, "".join(cards), plan["plan_id"], html.escape(plan["model"]),
        plan["quality"], plan["size"], plan["count"],
        html.escape(str(plan["cost"]["total_estimate_usd"])), html.escape(plan["prompt"]))
    output = root / "previews" / (plan["plan_id"] + ".html")
    engine.write_bytes(output, document.encode("utf-8"))
    return output


def adopt_math_image(root, repo, plan, review, confirm_review, replace_image_sha=None):
    """Stage only a reviewed PNG and its minimal manifest; no HTML/Git/deploy action."""
    engine.require(confirm_review == review.get("review_id"), "adoption_confirmation_required")
    source_check(repo, plan)
    destination = repo / "images/entries"
    engine.no_symlinks(destination)
    destination.mkdir(parents=True, exist_ok=True)
    manifest_file = destination / "manifest.json"
    # Shared lock prevents two different candidates losing each other's manifest edit.
    with engine.file_lock(destination / ".adopt.lock"):
        with engine.file_lock(engine.review_lock_path(root, plan, review.get("candidate_index"))):
            data = engine.validate_review(root, plan, review)
            source_check(repo, plan)
            engine.no_symlinks(manifest_file)
            previous_bytes = manifest_file.read_bytes() if manifest_file.exists() else None
            manifest = engine.read_json(manifest_file) if manifest_file.exists() else {
                "schema": "math-visual-entry-images/v1", "images": []}
            engine.require(manifest.get("schema") == "math-visual-entry-images/v1"
                           and isinstance(manifest.get("images"), list), "manifest_schema")
            rows = manifest["images"]
            engine.require(all(isinstance(x, dict) and isinstance(x.get("article"), str)
                               for x in rows), "manifest_rows")
            engine.require(len({x["article"] for x in rows}) == len(rows), "manifest_duplicates")
            previous = [x for x in rows if x["article"] == plan["subject"]["id"]]
            if previous:
                engine.require(engine.HEX.fullmatch(previous[0].get("sha256", ""))
                               and replace_image_sha is not None
                               and replace_image_sha == previous[0]["sha256"],
                               "existing_image_requires_exact_replace_confirmation")
            else:
                engine.require(replace_image_sha is None, "replace_target_missing")
            image_hash = engine.sha256(data)
            target = destination / (image_hash + ".png")
            engine.no_symlinks(target)
            if target.exists():
                engine.require(target.read_bytes() == data, "existing_asset_mismatch")
            else:
                engine.write_bytes(target, data, exclusive=True, mode=0o644)
            row = {
                "article": plan["subject"]["id"],
                "article_sha256": plan["subject"]["article_sha256"],
                "image": "./images/entries/" + target.name, "sha256": image_hash,
                "alt": review["alt"], "role": "entry-illustration", "approved": True,
                "reviewed_at": review["reviewed_at"], "review_id": review["review_id"],
            }
            # Do not copy prompts, request IDs, project IDs, candidate inventories,
            # teacher notes, generation receipts, or settings into the public tree.
            new_rows = [row if x["article"] == row["article"] else x for x in rows]
            if not previous:
                new_rows.append(row)
            engine.require((manifest_file.read_bytes() if manifest_file.exists() else None)
                           == previous_bytes, "manifest_changed_during_adoption")
            engine.write_json(manifest_file, {"schema": manifest["schema"], "images": new_rows},
                              mode=0o644)
            engine.write_json(root / "runs" / plan["plan_id"] / ("adopted-" + review["review_id"] + ".json"),
                              {"schema": "image-adoption/v1", "plan_id": plan["plan_id"],
                               "review_id": review["review_id"], "image_sha256": image_hash,
                               "article": row["article"], "staged_at": engine.now(),
                               "published": False})
    return row


def load_plan(root, plan_id):
    engine.require(engine.HEX.fullmatch(plan_id or ""), "plan_id")
    result = engine.read_json(root / "plans" / (plan_id + ".json"))
    engine.validate_plan(result)
    engine.require(result["plan_id"] == plan_id, "plan_filename_mismatch")
    return result


def public_plan_summary(plan):
    return {k: plan[k] for k in ("plan_id", "subject", "model", "quality", "size",
                                 "count", "cost", "budget_usd", "settings_sha256")}


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal message echoes unknown arguments and invalid values.
        # Someone accidentally passing a key must not put it in stderr/logs.
        raise engine.PipelineError("invalid_arguments_see_help")


def parser():
    p = SafeArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True,
                   help="Private directory outside every Git checkout and web root.")
    sub = p.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory", help="Export public metadata with the existing Org parser.")
    inv.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    inv.add_argument("--emacs", default="emacs")
    plan = sub.add_parser("plan", help="Offline proposal; no key access and no API request.")
    plan.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    plan.add_argument("--article", required=True)
    plan.add_argument("--candidates", type=int, default=1)
    plan.add_argument("--quality", choices=engine.QUALITIES, default="low")
    plan.add_argument("--size", choices=engine.SIZES, default="1536x1024")
    plan.add_argument("--price", type=Path)
    plan.add_argument("--budget-usd")
    plan.add_argument("--settings", type=Path)
    for command in ("show-plan", "status", "generate", "review-page", "review", "adopt"):
        child = sub.add_parser(command)
        child.add_argument("--plan", required=True)
        if command in ("generate", "review-page", "adopt"):
            child.add_argument("--repo", type=Path, default=DEFAULT_REPO)
        if command == "generate":
            child.add_argument("--settings", type=Path, required=True)
            child.add_argument("--confirm-plan", required=True)
            child.add_argument("--approve-charge", action="store_true")
        elif command == "review":
            child.add_argument("--candidate", type=int, required=True)
            child.add_argument("--image-sha256", required=True)
            child.add_argument("--decision", choices=("approve", "reject"), required=True)
            child.add_argument("--alt", required=True)
            for check in engine.CHECKS:
                child.add_argument("--" + check.replace("_", "-"), action="store_true")
        elif command == "adopt":
            child.add_argument("--review-id", required=True)
            child.add_argument("--confirm-review", required=True)
            child.add_argument("--replace-image-sha256")
    return p


def run(args):
    repo = repository(getattr(args, "repo", DEFAULT_REPO))
    root, workspace_id = engine.workspace(args.workspace, repo)
    if args.command == "inventory":
        inventory = export_inventory(repo, root, args.emacs)
        return {"status": "inventory_saved", "articles": len(inventory["articles"]),
                "output": str(root / "inventory.json"), "api_calls": 0}
    if args.command == "plan":
        profile = engine.read_json(args.price) if args.price else None
        settings = engine.read_json(args.settings) if args.settings else None
        plan = make_math_plan(
            repo, engine.read_json(root / "inventory.json"), load_briefs(repo), args.article,
            workspace_id, count=args.candidates, quality=args.quality, size=args.size,
            price_profile=profile, budget_usd=args.budget_usd, settings=settings)
        engine.write_json(root / "plans" / (plan["plan_id"] + ".json"), plan, exclusive=True)
        return {"status": "plan_saved", "api_calls": 0, **public_plan_summary(plan)}
    plan = load_plan(root, args.plan)
    engine.require(plan["workspace_id"] == workspace_id, "workspace_mismatch")
    if args.command == "show-plan":
        return plan
    if args.command == "status":
        path = root / "runs" / plan["plan_id"] / "receipt.json"
        if not path.exists():
            claimed = path.parent.exists()
            return {"status": "claimed_outcome_unknown" if claimed else "not_attempted",
                    "plan_id": plan["plan_id"], "retry_allowed": not claimed}
        result = engine.read_json(path)
        if result.get("status") in ("dispatch_started", "in_progress", "prepared"):
            result["observation"] = "incomplete_receipt_outcome_unknown_do_not_resend"
        return result
    if args.command == "generate":
        return engine.generate(
            plan, root, workspace_id, engine.read_json(args.settings),
            args.confirm_plan, args.approve_charge, source_check=lambda p: source_check(repo, p))
    if args.command == "review-page":
        return {"status": "review_page_saved", "output": str(review_page(root, plan, repo))}
    if args.command == "review":
        return engine.review_candidate(
            root, plan, args.candidate, args.image_sha256, args.decision,
            {check: getattr(args, check) for check in engine.CHECKS}, args.alt)
    if args.command == "adopt":
        engine.require(engine.HEX.fullmatch(args.review_id or ""), "review_id")
        review = engine.read_json(root / "reviews" / (args.review_id + ".json"))
        row = adopt_math_image(root, repo, plan, review, args.confirm_review,
                               args.replace_image_sha256)
        return {"status": "adopted_locally", "published": False, "image": row}
    raise engine.PipelineError("unknown_command")


def main(argv=None):
    # These commands never echo argv or exception text (including API bodies).
    try:
        result = run(parser().parse_args(argv))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except engine.PipelineError as error:
        print(json.dumps({"status": "refused_or_incomplete", "code": error.code}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('{"status":"interrupted","action":"inspect_same_plan_no_resend"}', file=sys.stderr)
        return 130
    except Exception:
        print('{"status":"local_error","action":"inspect_same_plan_no_resend"}', file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
