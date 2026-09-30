# rcca-agent

## 2026-09-30 Fleet RCA 수집·분석 보완

- Loki 경계를 밀리초로 안쪽 정규화한 경우 원본 기간의 `complete=false`와 실제 `request_time_range`를 보존한다. 조회 성공·미잘림·경고 없음이면 `observation_usable=true`로 실제 구간 안의 개별 health 관측을 Synthesis에 전달한다. 기간 전체의 오류 부재·지속 시간·집계가 완전하다는 뜻은 아니다. 다른 partial 사유는 허용하지 않는다.
- 기본 프로필 `builtin-grafana-v3`의 D05/D09는 등록된 `fleet-component-log-v1` adapter로 `attributes.health/component/reason`, `resources["machine.id"]`, `resources["k8s.node.name"]`, Loki ns timestamp와 XID/SXID 코드를 정규화한다. `log_type=component_data`, 알려진 component, 대상과 유효 시각이 필요하다. `Unhealthy`만 등록했으며 미등록 상태는 unknown이다.
- Loki 시각은 기본적으로 로그 기록 시각이다. `fact_eligible=false`인 보고 관측은 모델 입력으로 쓰지만 현재 장비 상태·runbook 실행 조건으로 승격하지 않는다. 운영 producer의 시각 의미를 검증해 `loki_timestamp_is_observed_at=true`를 명시하고 query의 `max_hold_seconds`를 등록한 경우에만 동일 대상·단일 cluster·사건 이전 freshness 검사 후 health/error_code fact로 승격할 수 있다. 기본 설정은 이 승격을 켜지 않는다.
- `degraded`여도 승인된 미실행 query와 예산·deadline이 남으면 최대 한 번 독립 후속 조회를 실행한다. 실패한 query를 재시도하는 루프는 추가하지 않는다.
- 승인 Runbook이 선택됐고 R02/R03가 요청되면 D08/D06을 계획에 포함한다. `purpose_plan`에 계획과 대상 식별 상태를 남긴다. GPU UUID 또는 Pod UID와 사건 시각 매핑을 확인하지 못하면 `incident_mapping`은 여전히 부족하다. 같은 노드의 Pod만으로 직접 GPU 사용 관계를 단정하지 않는다. 미실행·source 불가·대상 불명·당시 관계 부재를 구분한다.
- Incident의 새 입력 target에는 `machine_id/component/k8s_node_name`을 투영한다. 기존 event key와 의미 증거 hash는 유지해 투영만으로 중복 incident/RCA를 만들지 않는다. 기존 snapshot/hash/공개 결과는 재작성하지 않고 DB migration도 없다. Worker는 구형 snapshot의 alert 단서로 실행용 target만 보완하며 식별 충돌 시 fact/관계 승격을 막는다.

검증은 [Agent QA](../agents/QA.md)의 fixture 범위다. 운영 배포·실제 producer 시각 계약·실제 모델 원인 분석 품질은 별도 검수 대상이다.

## 2026-09-30 최종 보고서

유효 입력으로 판단 결과 구성까지 도달한 RCA는 `report.py`에서 감지된 문제·원인 판단·권고 조치와 조건·추가 확인·분석 한계의 다섯 섹션을 항상 만든다. 근거 없음, 승인 Runbook 없음, 결정적 fast path도 포함한다. 모델이 구성돼 있으면 기존 `explain()`을 한 번 호출해 코드가 만든 문장 ID의 우선순위를 선택하며 새 사실·조치·자유 문장을 생성하지 않는다. 선택되지 않은 문장도 남겨 부족 근거와 실행 조건이 누락되지 않게 한다.

`narrative`에 보고서를 저장하고 공개 RCA 화면에 표시한다. `narrative_status=complete/failed/omitted`는 모델 편집 상태이며 `quality.report.status=complete`는 보고서 구성 완료다. 원인 Synthesis 상태인 `quality.analysis`, 목적별 assessment와 `result_status`는 변경하지 않는다. 원천 `REBOOT_SYSTEM` 등은 미검증·미수행 제안으로 표시한다.

모델 미설정·확정된 HTTP 오류·잘못된 응답·예산 소진으로 편집을 못 하면 코드 기본 보고서를 남긴다. 실제 네트워크 호출 횟수는 모델 설정·남은 token/deadline·전송 재시도에 따라 달라진다. 원격 추론 종료 불명, 취소·lease 상실·실행 deadline 초과는 기존 fail/격리 계약이 우선이며 보고서로 우회 공개하지 않는다. 입력 검증·저장 등 기술 실패까지 공개 보고서를 보장하지 않는다.

DB migration·결과 스키마 버전 변경은 없고 기존 snapshot/hash와 공개 결과는 재작성하지 않는다. 재배포 후 새 실행에 적용하며 운영 검증 상태는 [Agent QA](../agents/QA.md)를 따른다.

다른 PC나 새 세션에서 이어받을 때는 [RCA·Runbook 개발 인수인계](HANDOFF.md)를 먼저 읽습니다. 구현 파일, 검증 범위, 미완료 항목과 다음 작업을 연결했습니다.

`11_RCA_Agent_모듈_설계서.md`에 따른 Incident 전용 RCA Worker입니다. JC kind는 `rca`입니다.

`src/rcca_agent/workflow.py`에 snapshot 검사·호환 Runbook·조건 검사·등록 조사·근거/원인 후보/권고가 있고, `procedures.py`에 GPU 접근 이상·GPU와 Pod·작업 진행 이상·다중 장치 사건 네 절차를 등록했습니다. 저장/발행은 LLM 도구가 아니며 Worker가 처리합니다. NAT 설정과 프롬프트를 보고서 Agent와 분리했습니다.

2026-09-28 구현은 하나의 NAT workflow 안에서 **Orchestrator → 병렬 Observation Sub-agent → 코드 충분성 판정 → 최대 1회 재조사 → 도구 없는 Synthesis → 결과 검증·저장 → JC 공개**로 동작합니다. `observation_agents.py`는 query별 독립 상태·예약 예산으로 수집하고 형제 실패를 격리하며 취소 시 task를 회수합니다. `synthesis.py`는 실제 수집 근거를 해석하되 모델 원인은 항상 candidate로 유지합니다. 충분한 기존 증거와 적용 Runbook이 있으면 MCP 수집·원인 Synthesis는 생략하지만 최종 보고서 편집은 수행합니다.

Runbook 조회·검색·조건 검사는 코드로 수행합니다. 전용 Runbook이 없으면 `rca.general_runbook_key`의 승인·고정 일반 Runbook을 사용합니다. 일반 Runbook까지 없으면 `approved_runbook` 부족을 저장하고 조사하지 않습니다. 기본 key `RB-GENERAL-GPU-NODE`는 콘텐츠를 자동 생성·발행하지 않으며, [Runbook 초안](runbooks/README.md)도 운영 발행본이 아닙니다. `limits.max_concurrency` 기본값은 3이며 전체 query/discovery 예산을 공유합니다.

실제 로컬 LLM endpoint는 추후 연결합니다. 미구성이면 유효 근거를 보존하고 `synthesis_unconfigured`를 기록합니다. Fleet adapter는 error_code를 추출하지만 기본 설정에서는 보고 관측으로만 사용하며 fact 승격에는 운영 producer/binding/freshness 계약이 필요합니다. 현재 Worker 입력은 **1.3**입니다. 1.4 목적 자동 선택·이력 고정·선택 trace와 운영 분석 품질 검수는 [보완 계획](../docs/specs/rca-agent/implementation-plan-20260928.md)의 후속 단계입니다.

설치·환경 설정·Docker·최소 테스트/E2E: [공통 실행 안내](../agents/README.md), [검증 기록](../agents/QA.md).

```powershell
.venv/Scripts/python.exe -m rcca_agent.main
```

저장소 루트에서 실행합니다. `incident_id`가 없는 임의 증상 요청은 받지 않습니다.

Incident가 생성한 `incident_snapshot.alert`를 원본 알람 증거로 읽습니다. 기존 `incident_snapshot.evidence` 형식도 지원합니다. 원본 snapshot과 hash는 변경하지 않으며, 알람의 필드를 `verified_facts`로 승격하지 않습니다. `alert` 형식은 등록된 purpose에 따라 조사 절차를 선택하고 실제 수집 증거로 판단합니다. 두 증거 필드가 모두 없거나 `alert`가 객체가 아니면 Worker 입력 검증 단계에서 거부합니다.
