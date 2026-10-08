# Remaining Runbook transition / 잔여 Runbook 전환

## 2026-10-08 status

The remaining 258 repository investigation plans now state their query limits by
evidence group. D09 preserves producer, code and normalized-health requirements;
D02 is supporting utilization, not a substitute for application, ECC, link,
firmware, topology or recovery evidence. Original code-specific sources, guidance,
conditions and recommendations remain intact. Synthetic origin is not inferred
from an error code or an example PCI address. No cluster-specific branching was added.

기존 9개 외 258개를 Backend Knowledge API로 기존 지식의 새 draft revision으로
등록했다. 모두 재조회해 본문 일치와 기존 revision의 상태·버전·본문/검토 해시·
호환성 보존을 확인했다. SQL, DB schema, Job/slot 변경은 없다.

## Individually reviewed publication

XID13, XID31, XID43 and XID45 revision 2 were reviewed and published through the
Backend API under user authorization. This is automated review, not a claim of
independent human review. The published content and reviewed hashes match the
repository inputs. Recovery retires only the new revision through the same API.

| Code | Review boundary |
|---|---|
| XID13 | Application/engine exception; PID/CUDA/reproduction and device identity needed before software versus hardware attribution. |
| XID31 | MMU/page fault; address and application evidence required, not proof of defective GPU memory. |
| XID43 | Application termination is distinct from GPU-wide unhealthy state; utilization does not prove recovery. |
| XID45 | Cleanup can follow an earlier fault or operator action; standalone FM guidance requires FM and event-order evidence. |

The [NVIDIA Xid catalog](https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html)
was consulted for these distinctions. Product/version applicability remains conditional.
All four are investigation-only with `producer_contract=fleet-component-log-v1`;
missing required facts remain pending. No hardware action is executed.

Total transitioned publication: 13 logical Runbooks. Remaining: 254 draft revisions,
not approved or published. Their catalog source labels (documented, legacy,
conflicting or source-only) are review inputs, not production approvals.
The original 267 legacy revisions remain preserved; historical invalid-contract
records are not rewritten or hidden.

## Verification and limits

- Full non-E2E Agent suite: 658 passed, 35 deselected.
- Isolated PostgreSQL/Backend/JC/Worker integration: 4 passed, 21 deselected;
  Grafana and model responses were fixtures, not production RCA evidence.
- Each of the 258 proposed plans passed runtime-contract checks with a fixture
  compatibility declaration. Code-specific retrieval passed; missing facts kept
  all 258 pending. These fixture declarations were not bulk applied to production.
- All 258 registered drafts were reread and compared with their input content;
  prior revision identity/state/hash/compatibility remained unchanged.
- The four new published revisions were reread and passed runtime validation.
- Actual error-specific RCA verification of these four remains unverified.

## SXID live-test boundary

The 2026-10-08 13:30 KST injection API returned success. The examined Loki window
contained Healthy SXID component summaries for the target after injection and no
new matching Incident/RCA was found. The supplied kernel buffer contains SXID11001
messages, but its reconstructed wall-clock timestamp differs from the injection
command time. Kernel writing, Fleet event recognition, state evolution, log
export, alert evaluation and RCA execution must be checked separately.

Do not replace Healthy with Unhealthy, bypass the alert rule, infer a physical
NVSwitch fault, or publish an unrelated RCA as proof of this test. The exact
producer-side cause remains unconfirmed. Old RCA results remain unchanged.
