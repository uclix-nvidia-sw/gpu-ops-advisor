"""Validate and register Runbooks through the owning Backend API; never write SQL."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from agent_common.contracts import content_hash
from .runbook_contract import validate_runbook


def check(row, profile, *, runtime=False):
    if row.get("kind") != "runbook":
        raise ValueError("kind must be runbook")
    allowed = set(profile["queries"])
    return validate_runbook(row, profile["queries"], allowed, authoring=not runtime)


def backend_url(value):
    u = urlsplit(value or "")
    if (
        u.scheme not in ("http", "https")
        or not u.hostname
        or u.username
        or u.password
        or u.query
        or u.fragment
        or u.path.rstrip("/") != "/api/v1"
    ):
        raise ValueError("provide a credential-free Backend URL ending /api/v1")
    return value.rstrip("/")


def reference(row):
    return {
        key: row[key]
        for key in (
            "knowledge_id",
            "revision",
            "revision_id",
            "knowledge_key",
            "state",
            "version",
            "content_hash",
        )
    }


def draft(client, row, profile, request_key, knowledge_id=None):
    check(row, profile)
    path = "/knowledge"
    if knowledge_id:
        path += f"/{UUID(knowledge_id)}/revisions"
    response = client.post(path, json=row, headers={"Idempotency-Key": request_key})
    response.raise_for_status()
    saved = response.json()
    if saved["content_hash"] != content_hash(row["content"]):
        raise ValueError("stored content hash mismatch")
    return reference(saved)


def transition(client, receipt, profile, action, request_key, comment):
    path = f"/knowledge/{UUID(receipt['knowledge_id'])}/revisions/{int(receipt['revision'])}"
    response = client.get(path)
    response.raise_for_status()
    saved = response.json()
    # A receipt pins exactly the content the operator reviewed; version preconditions
    # and idempotent replay are enforced atomically by Backend, not a read/write race.
    if saved["content_hash"] != receipt["content_hash"]:
        raise ValueError("content changed; review a new receipt")
    if action not in ("retire", "request_changes"):
        check(saved, profile, runtime=action in ("approve", "publish"))
    if action == "publish":
        endpoint, body = "publish", {}
    elif action == "retire":
        endpoint, body = "retire", {"reason": comment}
    else:
        endpoint, body = "review", {"action": action, "comment": comment}
    response = client.post(
        path + "/" + endpoint,
        json=body,
        headers={"Idempotency-Key": request_key, "If-Match": str(receipt["version"])},
    )
    response.raise_for_status()
    return reference(response.json())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "check",
            "draft",
            "request",
            "approve",
            "request_changes",
            "publish",
            "retire",
        ),
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Runbook JSON for check/draft; prior response receipt for transitions",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        required=True,
        help="Actual Agent profile; queries validated locally",
    )
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="Require nonempty compatibility during check",
    )
    parser.add_argument("--backend", help="Explicit Backend URL ending /api/v1")
    parser.add_argument(
        "--request-key",
        help="Reuse this key and input for an uncertain/retried mutation",
    )
    parser.add_argument(
        "--knowledge-id", help="Create a new revision of an existing knowledge ID"
    )
    parser.add_argument("--comment", default="", help="Required for review/retire")
    parser.add_argument(
        "--output",
        type=Path,
        help="Save returned reference; use as input to the next explicit transition",
    )
    args = parser.parse_args(argv)
    try:
        row = json.loads(args.file.read_text(encoding="utf-8-sig"))
        profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
        if args.action == "check":
            result = {
                "valid": True,
                "runtime": args.runtime,
                "plan": check(row, profile, runtime=args.runtime),
            }
        else:
            url = backend_url(args.backend)
            if not args.request_key:
                raise ValueError("--request-key required; preserve it when retrying")
            if args.action not in ("draft", "publish") and not args.comment.strip():
                raise ValueError("--comment required")
            with httpx.Client(
                base_url=url, timeout=30, follow_redirects=False
            ) as client:
                if args.action == "draft":
                    result = draft(
                        client, row, profile, args.request_key, args.knowledge_id
                    )
                else:
                    result = transition(
                        client,
                        row,
                        profile,
                        args.action,
                        args.request_key,
                        args.comment,
                    )
        output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        print(output, end="")
    except httpx.HTTPStatusError as exc:
        parser.exit(
            1,
            f"Backend HTTP {exc.response.status_code}; no automatic retry or approval\n",
        )
    except (OSError, ValueError, KeyError, TypeError, httpx.RequestError) as exc:
        # Never emit credential-bearing URLs, server response bodies or raw transport exceptions.
        parser.exit(
            1,
            f"Runbook operation failed ({type(exc).__name__}); check inputs. For uncertain writes, reuse the same key and input.\n",
        )


if __name__ == "__main__":
    main()
