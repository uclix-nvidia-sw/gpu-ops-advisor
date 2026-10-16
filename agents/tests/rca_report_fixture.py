"""Deterministic prose fixture; exercises transport/contracts, not model quality."""


def report_reply(data):
    return {
        "sections": [
            {
                "id": section,
                "text": " ".join(
                    row["text"]
                    for row in data["source_items"]
                    if row["section"] == section
                ),
                "source_ids": [
                    row["id"]
                    for row in data["source_items"]
                    if row["section"] == section
                ],
            }
            for section in data["sections"]
        ]
    }
