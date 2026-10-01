"""Generate the frontend label artifact from the packaged canonical dictionary."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "rcca-agent/src/rcca_agent/report_labels.json"
destination = root / "frontend/src/lib/rcaLabels.json"
destination.write_bytes(source.read_bytes())
print(destination)
