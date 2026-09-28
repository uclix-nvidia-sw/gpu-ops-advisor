"""Recursively validate and import Runbook JSON files as Backend drafts."""

import argparse
import json
from pathlib import Path
import re
import sys
import time
from uuid import UUID

import httpx

from agent_common.contracts import content_hash
from .runbook_admin import backend_url, check, draft


def load_runbooks(folder, profile):
    rows = {}
    for path in sorted(folder.rglob("RB-*.json")):
        row = json.loads(path.read_text(encoding="utf-8-sig"))
        key = row.get("knowledge_key", "")
        if not isinstance(key, str) or not re.fullmatch(r"RB-[A-Z0-9-]+", key):
            raise ValueError("invalid knowledge_key")
        if key in rows:
            raise ValueError("duplicate knowledge_key: " + key)
        check(row, profile)
        rows[key] = row
    if not rows:
        raise ValueError("no RB-*.json files")
    return rows


def import_runbooks(client, rows, profile, batch_key, receipts, knowledge_ids=None):
    """Preflight all input, then checkpoint each idempotent draft creation."""
    if (
        not batch_key
        or len(batch_key) > 80
        or not re.fullmatch(r"[A-Za-z0-9_.-]+", batch_key)
    ):
        raise ValueError(
            "batch key: 1-80 ASCII letters, digits, dot, underscore or dash"
        )
    ids = knowledge_ids or {}
    if not isinstance(ids, dict) or set(ids) - rows.keys():
        raise ValueError("knowledge IDs must map selected knowledge keys to UUIDs")
    for value in ids.values():
        if not isinstance(value, str):
            raise ValueError("knowledge IDs must be UUID strings")
        UUID(value)
    url = backend_url(str(client.base_url))
    jobs = []
    skipped = 0
    for key, row in rows.items():
        check(row, profile)
        request_key = batch_key + ":" + key
        context = {
            "backend": url,
            "request_key": request_key,
            "request_hash": content_hash({"row": row, "knowledge_id": ids.get(key)}),
        }
        path = receipts / (key + ".json")
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("import_context") != context:
                raise ValueError("receipt/input mismatch: " + key)
            skipped += 1
        else:
            jobs.append((key, row, request_key, context, path))
    receipts.mkdir(parents=True, exist_ok=True)
    created = 0
    for key, row, request_key, context, path in jobs:
        for attempt in range(4):
            try:
                saved = draft(client, row, profile, request_key, ids.get(key))
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 429 or attempt == 3:
                    print(
                        "Failed: " + key + "; resume with the same inputs/batch key.",
                        file=sys.stderr,
                    )
                    raise
                delay = int(exc.response.headers.get("Retry-After", "60"))
                if not 0 < delay <= 300:
                    raise ValueError("unsupported Retry-After") from None
                print(f"Rate limited: waiting {delay}s for {key}.", file=sys.stderr)
                time.sleep(delay)
        saved["import_context"] = context
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temp.replace(path)
        created += 1
    return {"total": len(rows), "registered": created, "resumed": skipped}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate every file without HTTP calls"
    )
    parser.add_argument("--backend", help="Explicit Backend URL ending /api/v1")
    parser.add_argument(
        "--batch-key", help="Stable key for this import; preserve on resume"
    )
    parser.add_argument(
        "--receipts",
        type=Path,
        help="Dedicated response directory outside the input folder",
    )
    parser.add_argument(
        "--knowledge-ids",
        type=Path,
        help="Optional JSON mapping knowledge_key to existing knowledge_id for new revisions",
    )
    args = parser.parse_args(argv)
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
        rows = load_runbooks(args.folder, profile)
        if args.dry_run:
            result = {"valid": True, "total": len(rows), "writes": 0}
        else:
            url = backend_url(args.backend)
            if args.receipts is None or args.receipts.resolve().is_relative_to(
                args.folder.resolve()
            ):
                raise ValueError("--receipts must be outside the input folder")
            ids = (
                json.loads(args.knowledge_ids.read_text(encoding="utf-8-sig"))
                if args.knowledge_ids
                else None
            )
            with httpx.Client(
                base_url=url, timeout=30, follow_redirects=False
            ) as client:
                result = import_runbooks(
                    client, rows, profile, args.batch_key, args.receipts, ids
                )
        print(json.dumps(result, ensure_ascii=True))
    except httpx.HTTPStatusError as exc:
        parser.exit(
            1,
            f"Backend HTTP {exc.response.status_code}; keep receipts and reuse the same batch key.\n",
        )
    except (OSError, ValueError, KeyError, TypeError, httpx.RequestError) as exc:
        parser.exit(
            1,
            f"Import failed ({type(exc).__name__}); check inputs and preserve receipts/batch key.\n",
        )


if __name__ == "__main__":
    main()
