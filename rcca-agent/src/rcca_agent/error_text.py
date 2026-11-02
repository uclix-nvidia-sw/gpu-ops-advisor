"""Separate a documented Fleet catalog cross-reference from reported Xid codes."""

import re


# Fleet embeds the NVIDIA 171/172 description in the reason. Its reference to
# Xid 48 is explanatory text, not a second event. Do not suppress arbitrary
# secondary codes or choose the first code from a genuinely ambiguous message.
ECC_DESCRIPTION = re.compile(
    r"\bAdditional\s+to\s+Xid\s+48\s+providing\s+more\s+details\s+on\s+"
    r"particulars\s+of\s+fault\s+to\s+differentiate\s+DRAM/SRAM\b",
    re.IGNORECASE,
)
ECC_PRIMARY = re.compile(
    r"^(?:\s*\[[^\]\r\n]+\]\s*(?:[\w.-]+:)?)*\s*XID\s+(171|172)\b",
    re.IGNORECASE,
)


def event_code_text(text):
    """Return search text only; retain the original reason in stored evidence."""
    if ECC_PRIMARY.match(text):
        return ECC_DESCRIPTION.sub("ECC memory-type detail", text)
    return text
