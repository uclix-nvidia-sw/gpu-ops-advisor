"""Execution-time code decisions; diagnostic evidence, never model observations."""


def check(trace, rule, expression, value, inputs):
    if trace is not None:
        trace.append(
            dict(rule=rule, expression=expression, value=bool(value), inputs=inputs)
        )
    return value


def record_decision(obs, period, phase, source, checks, inputs, outputs, refs):
    return obs._evidence(
        phase,
        None,
        period,
        {
            "schema": "rca-code-decision/1",
            "workflow": "single_collection",
            "source": source,
            "checks": checks,
            "inputs": inputs,
            "outputs": outputs,
            "evidence_refs": list(dict.fromkeys(refs)),
            "execution_status": "complete",
        },
        "ok",
        {"workflow": "single_collection", "execution_status": "complete"},
    )["id"]
