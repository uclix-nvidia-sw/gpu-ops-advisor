"""Read-only scheduler source preflight; never expose credentials or change ports."""

import json
import socket
import subprocess


def kubectl(*args):
    result = subprocess.run(
        ["kubectl", "--request-timeout=20s", *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout)


def selected_settings(pods):
    output = []
    for pod in pods.get("items", []):
        for container in pod.get("spec", {}).get("containers", []):
            tokens = container.get("command", []) + container.get("args", [])
            settings = {}
            for index, token in enumerate(tokens):
                key, separator, value = token.partition("=")
                if key not in ("--bind-address", "--secure-port"):
                    continue
                if not separator:
                    value = tokens[index + 1] if index + 1 < len(tokens) else None
                    if value is not None and value.startswith("--"):
                        value = None
                settings[key[2:]] = value
            output.append(
                {
                    "pod": pod.get("metadata", {}).get("name"),
                    "node": pod.get("spec", {}).get("nodeName"),
                    "image": container.get("image"),
                    "host_network": pod.get("spec", {}).get("hostNetwork", False),
                    "explicit_settings": settings,
                }
            )
    return output


def main():
    output = {
        "scope": "Read-only configured facts; no D07 activation or metric availability asserted"
    }
    errors = []
    for name, args in (
        ("version", ("version", "-o", "json")),
        (
            "scheduler",
            (
                "-n",
                "kube-system",
                "get",
                "pods",
                "-l",
                "component=kube-scheduler",
                "-o",
                "json",
            ),
        ),
    ):
        try:
            result = kubectl(*args)
            output[name] = (
                result.get("serverVersion", {}).get("gitVersion")
                if name == "version"
                else selected_settings(result)
            )
        except (subprocess.SubprocessError, OSError, ValueError):
            # Upstream error text may contain sensitive endpoint details.
            errors.append(name + "_read_failed")
    try:
        with socket.create_connection(("127.0.0.1", 10259), timeout=2):
            output["local_10259_tcp"] = "connected"
    except OSError:
        output["local_10259_tcp"] = "not_connected"
    output["local_probe_scope"] = (
        "Only the machine running this script; not other scheduler replicas. TCP only, not authentication or metric verification."
    )
    output["errors"] = errors
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
