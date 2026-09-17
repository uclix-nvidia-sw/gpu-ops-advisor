"""Package a staged chart with exact image metadata; never edit source values."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]


def bind_images(values, records, namespace, tag):
    expected = set(values["components"])
    if set(records) != expected:
        raise ValueError("Expected exactly one image record for every chart component")
    values["global"]["imageNamespace"] = namespace
    for name, component in values["components"].items():
        record = records[name]
        image = component["image"]
        reference = f"{values['global']['imageRegistry']}/{namespace}/{image['repository']}:{tag}"
        if record["component"] != name or record["image"] != reference:
            raise ValueError(f"Image identity mismatch: {name}")
        if record["published"] not in ("true", "false"):
            raise ValueError(f"Invalid publication status: {name}")
        digest = record["digest"]
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError(f"Invalid digest: {name}")
        image["tag"] = tag
        # PR builds are not in a registry: keep a tag for inspection packages.
        image["digest"] = digest if record["published"] == "true" else ""
    return values


def main(root=ROOT):
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    namespace, tag, version = (
        os.environ[k] for k in ("IMAGE_NAMESPACE", "IMAGE_TAG", "CHART_VERSION")
    )
    records = {}
    for path in (dist / "images").glob("*.json"):
        record = json.loads(path.read_text())
        if record["component"] in records:
            raise ValueError("Duplicate image record")
        records[record["component"]] = record
    source = root / "charts/gpu-ops-advisor"
    values = bind_images(
        yaml.safe_load((source / "values.yaml").read_text()), records, namespace, tag
    )
    helm = os.getenv("HELM_BINARY", "helm")
    with tempfile.TemporaryDirectory() as temp:
        chart = Path(temp) / "gpu-ops-advisor"
        shutil.copytree(source, chart)
        (chart / "values.yaml").write_text(
            yaml.safe_dump(values, sort_keys=False), encoding="utf-8"
        )
        info = yaml.safe_load((chart / "Chart.yaml").read_text())
        info["version"] = version
        (chart / "Chart.yaml").write_text(
            yaml.safe_dump(info, sort_keys=False), encoding="utf-8"
        )
        subprocess.run([helm, "lint", "--strict", str(chart)], check=True)
        subprocess.run(
            [helm, "package", str(chart), "--destination", str(dist)], check=True
        )
    package = dist / f"gpu-ops-advisor-{version}.tgz"
    with (dist / "rendered.yaml").open("w", encoding="utf-8") as output:
        subprocess.run(
            [helm, "template", "gpu-ops", str(package), "--namespace", "gpu-ops"],
            stdout=output,
            check=True,
        )
    checksum = hashlib.sha256(package.read_bytes()).hexdigest()
    (dist / (package.name + ".sha256")).write_text(f"{checksum}  {package.name}\n")
    (dist / "release-manifest.json").write_text(
        json.dumps(
            {
                "chart": package.name,
                "sha256": checksum,
                "commit": os.getenv("GITHUB_SHA", "local"),
                "images": records,
                "deployable_images": all(
                    r["published"] == "true" for r in records.values()
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
