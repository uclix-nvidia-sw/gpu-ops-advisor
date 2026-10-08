# Remaining Runbook transition / 잔여 Runbook 전환

## 2026-10-08 batch publication completed

The remaining **254** revisions were reviewed and published through the Backend
Knowledge API. Together with the previous 13, all **267 logical Runbooks** now have
a published transition revision. Each latest revision was reread: repository
content and reviewed hashes match, runtime contract validation passes, and missing
required facts remain pending in local checks using the persisted records.
[The publication audit](publication-audit-20261008.json) records the content hashes
and source checks without operational credentials or incident data.

잔여 254개를 일괄 검토·발행했다. 기존 13개를 포함한 267개 최신 발행본 모두
저장소 본문·검토 해시·런타임 계약을 통과했다. 이전 258개 발행본은 다시 읽어
상태·버전·본문·검토 해시·호환성 보존을 확인했다. SQL, schema, Job/slot, 클러스터
설정 변경은 없다. 새 작업이 새 revision을 고정하며 과거 실행 기록은 그대로다.

### Review scope

- NVIDIA Xid catalog, Fabric Manager guide and both pinned GPUd catalogs were
  fetched again; all four source hashes match the original review material.
- 95 NVLink decoder rows match the NVIDIA table field by field.
- Per-code definitions, source conflicts, product/version limits, application
  versus hardware distinctions, and conditional operator actions were reviewed.
  Source-only and legacy definitions remain explicitly conditional; publishing
  them does not assert that the deployed Fleet recognizes those codes.
- All plans remain investigation-only. D09 is required; D02 cannot replace missing
  topology, ECC, application, firmware or recovery evidence. Unsupported hardware
  attribution and remediation eligibility are not enabled by publication.
- This was user-authorized automated review, not independent human approval or
  live validation of every error code. Missing-fact and revision-selection checks
  used the actual persisted bodies locally, not new production RCA executions.

### Operational limits and recovery

Old published revisions are preserved. Their D05-related `invalid_contract`
diagnostics may still appear in candidate/history records; the latest 267
revisions have zero contract failures in this audit. Do not suppress old failures
or rewrite historical results to make the display look successful.

Recovery uses the Backend retirement lifecycle for an affected **new** revision
with its current version/hash receipt. An old D05 revision is not a valid fallback
under the new D contract. Preserve its history and prepare a corrected new revision
if necessary; do not mutate SQL or undo unrelated publications.

The SXID injection test still has a separate producer-side gap: Fleet's own
`/v1/states` returned Healthy and `/v1/events` returned no events in the queried
window. A successful injection response or kernel line is not proof of Fleet
recognition, an Unhealthy report, a Grafana notification or a new RCA. No post-test
RCA was found at the final job-list check. Watcher/process inspection remains
pending; this audit does not claim the final editor repair is live-verified.

## Earlier 2026-10-08 snapshot (superseded counts)


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
