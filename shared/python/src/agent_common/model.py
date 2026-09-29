"""Apply immutable GUI model profiles without putting credentials in job data."""

import asyncio
from dataclasses import replace
import ipaddress
import os
import socket
from urllib.parse import urlsplit

import httpx


def model_settings(settings, snapshot):
    if snapshot is None:
        return settings
    config = snapshot["config"]
    ref = snapshot.get("secret_ref") or ""
    if ref not in ("", "env:LLM_API_KEY"):
        raise ValueError("unsupported model authentication reference")
    key = os.getenv("LLM_API_KEY", "") if ref else ""
    if ref and not key:
        raise ValueError("model authentication key is not configured")
    base = config["endpoint_url"].rstrip("/")
    model = config["model_name"].strip()
    if not base or not model:
        raise ValueError("incomplete model profile")
    return replace(
        settings,
        llm_base_url=base,
        llm_model=model,
        llm_api_key=key,
        llm_routed=True,
    )


async def model_destination(raw):
    """Validate all DNS answers and connect to a pinned IP with original TLS SNI."""
    url = urlsplit(raw)
    allowed = os.getenv("DSX_MODEL_HOSTS", "").split(",")
    if (
        url.scheme not in ("https", "http")
        or not url.hostname
        or url.username is not None
        or url.query
        or url.fragment
        or url.netloc not in allowed
    ):
        raise ValueError("model endpoint is not allowed")
    networks = [
        ipaddress.ip_network(value.strip())
        for value in os.getenv("DSX_MODEL_CIDRS", "").split(",")
        if value.strip()
    ]
    try:
        ipaddress.ip_address(url.hostname)
        literal = True
    except ValueError:
        literal = False
    records = await asyncio.get_running_loop().getaddrinfo(
        url.hostname,
        url.port or (443 if url.scheme == "https" else 80),
        type=socket.SOCK_STREAM,
    )
    addresses = [ipaddress.ip_address(record[4][0]) for record in records]
    if not addresses:
        raise ValueError("model DNS has no addresses")
    for ip in addresses:
        approved = literal or any(ip in network for network in networks)
        if (
            ip.is_unspecified
            or ip.is_multicast
            or ip.is_link_local
            or ((ip.is_private or ip.is_loopback) and not approved)
        ):
            raise ValueError("model destination is not allowed")
    return (
        httpx.URL(raw).copy_with(host=str(addresses[0])),
        {"Host": url.netloc},
        {"sni_hostname": url.hostname},
    )
