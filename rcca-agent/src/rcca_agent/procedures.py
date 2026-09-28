from dataclasses import dataclass


@dataclass(frozen=True)
class Procedure:
    procedure_id: str
    version: str
    accepted_symptoms: tuple
    required_queries: tuple
    optional_queries: tuple
    allowed_next_steps: tuple
    stop_conditions: tuple = (
        "evidence_sufficient",
        "missing_data",
        "conflicting_evidence",
        "unsupported_source",
        "budget_exhausted",
        "query_failed",
    )
    limits: str = "deployment.C07"


PROCEDURES = {
    "gpu_access": Procedure(
        "gpu_access",
        "1.1",
        ("gpu_access", "xid", "health"),
        ("D09", "D05"),
        ("D02", "D08", "D06"),
        ("D09", "D05", "D02", "D08", "D06"),
    ),
    "gpu_pod": Procedure(
        "gpu_pod",
        "1.2",
        ("gpu_pod", "mapping"),
        ("D08", "D06"),
        ("D09", "D05", "D02"),
        ("D08", "D06", "D09", "D05", "D02"),
    ),
    "work_progress": Procedure(
        "work_progress",
        "1.2",
        ("work_progress", "stalled"),
        ("D09", "D08", "D06"),
        ("D05", "D02", "D13"),
        ("D09", "D08", "D06", "D05", "D02", "D13"),
    ),
    "multi_device": Procedure(
        "multi_device",
        "1.2",
        ("multi_device", "node"),
        ("D01", "D09"),
        ("D08", "D06", "D05", "D02"),
        ("D01", "D09", "D08", "D06", "D05", "D02"),
    ),
}


def select_procedure(data, evidence):
    symptom = evidence.get("symptom", "") if isinstance(evidence, dict) else ""
    for procedure in PROCEDURES.values():
        if symptom in procedure.accepted_symptoms:
            return procedure
    if "R07" in data["purpose_ids"]:
        return PROCEDURES["multi_device"]
    if set(data["purpose_ids"]) & {"R02", "R03", "R08"}:
        return PROCEDURES["gpu_pod"]
    if "R04" in data["purpose_ids"]:
        return PROCEDURES["work_progress"]
    return PROCEDURES["gpu_access"]
