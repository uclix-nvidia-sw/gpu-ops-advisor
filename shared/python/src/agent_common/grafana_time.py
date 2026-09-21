"""Time formatting for Grafana MCP's Prometheus datemath parser."""

from datetime import datetime, timedelta, timezone


def prometheus_time(value, *, ceiling=False):
    """Use UTC milliseconds at the MCP boundary; never change stored evidence.

    MCP 1.4.2 uses Grafana datemath, which rejects RFC3339 microseconds.
    Prometheus samples have millisecond precision. Round a discovery start up
    and an end down so the request does not expand the authorized interval.
    Loki uses a different parser and keeps its original precision.
    """
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    dt = dt.astimezone(timezone.utc)
    remainder = dt.microsecond % 1000
    if ceiling and remainder:
        dt += timedelta(microseconds=1000 - remainder)
    precision = "milliseconds" if dt.microsecond else "seconds"
    return dt.isoformat(timespec=precision).replace("+00:00", "Z")
