"""Select proven-independent changes; uncertain dependencies keep the full suite."""

import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def changed_paths(env, event, root=ROOT):
    if env["GITHUB_EVENT_NAME"] == "pull_request":
        base = event.get("pull_request", {}).get("base", {}).get("sha", "")
    elif env["GITHUB_EVENT_NAME"] == "push" and env["GITHUB_REF"] == "refs/heads/main":
        base = event.get("before", "")
    else:
        return None
    head = env.get("GITHUB_SHA", "")
    if any(
        not re.fullmatch(r"[0-9a-f]{40}", sha) or sha == "0" * 40
        for sha in (base, head)
    ):
        return None
    try:
        # No rename detection: both the removed and added paths affect the plan.
        result = subprocess.run(
            ["git", "diff", "--name-only", "--no-renames", "-z", base, head, "--"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        return (
            result.stdout.decode("utf-8").rstrip("\0").split("\0")
            if result.stdout
            else []
        )
    except (subprocess.CalledProcessError, UnicodeError):
        return None


def plan(paths, event, components):
    frontend = False
    full = event != "pull_request" or paths is None or not paths
    for name in paths or []:
        path = PurePosixPath(name)
        if name.startswith("frontend/"):
            frontend = True
        elif (name.startswith("docs/") and path.suffix == ".md") or (
            path.name in {"README.md", "QA.md"}
            and (
                len(path.parts) == 1
                or (
                    len(path.parts) == 2
                    and path.parts[0]
                    in {
                        "backend",
                        "incident",
                        "job-controller",
                        "rcca-agent",
                        "ops-agent",
                        "agents",
                        "shared",
                        "grafana-mcp",
                    }
                )
            )
        ):
            continue
        else:
            full = True
    selected = (
        components
        if full or event != "pull_request"
        else [row for row in components if frontend and row["component"] == "frontend"]
    )
    return {
        "backend": full,
        "frontend": full or frontend,
        "matrix": {"include": selected},
        "images": bool(selected),
        "package": len(selected) == len(components),
        "reason": "full-or-uncertain"
        if full
        else "frontend-only"
        if frontend
        else "documentation-only",
    }


def main():
    event = json.loads(
        Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")
    )
    components = json.loads((ROOT / "tools/ci/components.json").read_text())
    result = plan(
        changed_paths(os.environ, event), os.environ["GITHUB_EVENT_NAME"], components
    )
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for key, value in result.items():
            print(
                f"{key}={json.dumps(value, separators=(',', ':')) if not isinstance(value, str) else value}",
                file=output,
            )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
