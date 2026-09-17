"""Produce one version/image matrix for every reusable workflow (stdlib only)."""

import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def metadata(env, chart_version):
    sha = env["GITHUB_SHA"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("GITHUB_SHA must be a full commit SHA")
    event = env["GITHUB_EVENT_NAME"]
    ref = env["GITHUB_REF"]
    tagged = event == "push" and ref.startswith("refs/tags/v")
    publish_images = event == "push" and (ref == "refs/heads/main" or tagged)
    if tagged:
        version = ref.removeprefix("refs/tags/v")
        if not re.fullmatch(r"\d+\.\d+\.\d+", version) or version != chart_version:
            raise ValueError(
                "Release tag must equal Chart.yaml version (vMAJOR.MINOR.PATCH)"
            )
    else:
        run = env["GITHUB_RUN_NUMBER"]
        attempt = env.get("GITHUB_RUN_ATTEMPT", "1")
        if not run.isdigit() or not attempt.isdigit():
            raise ValueError("Invalid GitHub run number")
        version = f"{chart_version}-ci.{run}.{attempt}"
    return {
        "chart_version": version,
        "image_tag": ref.removeprefix("refs/tags/") if tagged else f"sha-{sha}",
        "namespace": env["GITHUB_REPOSITORY_OWNER"].lower(),
        "publish_images": str(publish_images).lower(),
        "publish_chart": str(tagged).lower(),
    }


def main():
    chart = (ROOT / "charts/gpu-ops-advisor/Chart.yaml").read_text(encoding="utf-8")
    version = re.search(r"^version: (\d+\.\d+\.\d+)$", chart, re.M).group(1)
    app_version = re.search(
        r'^appVersion: ["\']?(\d+\.\d+\.\d+)["\']?$', chart, re.M
    ).group(1)
    if version != app_version:
        raise ValueError("Chart version and appVersion must match this product release")
    result = metadata(os.environ, version)
    result["matrix"] = json.dumps(
        {"include": json.loads((ROOT / "tools/ci/components.json").read_text())},
        separators=(",", ":"),
    )
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for key, value in result.items():
            print(f"{key}={value}", file=output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
