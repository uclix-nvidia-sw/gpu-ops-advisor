# XID 79 / SXID 11001 단계별 점검 결과

**접수 → JC 작업 생성 → Runbook 검색·계획 → 실패 결과 저장·발행까지 이어졌다. D09·D05 수집은 두 사례 모두 `JSONDecodeError`로 실패했으며, LLM 원인 분석은 실행되지 않았다.** `jobs.status=succeeded`는 결과 발행 완료를 뜻한다. 이번 본문의 `result_status=blocked`를 분석 성공으로 읽으면 안 된다.

## 조회 범위와 증거 수준

- 점검 시각: 2026-09-28 16:17 KST. 이미 실행된 XID 79 / SXID 11001 사례를 읽기 전용 Backend API로 재조회했다.
- 사용자가 Incident의 Grafana webhook에 직접 테스트 payload를 보냈다. Grafana 규칙 평가·실제 GPU 장애·Grafana firing/resolved 이력은 검증하지 않았다.
- `incidents`, `jobs/job_attempts`의 공개 필드, `evidence` 16행, 선택된 `knowledge_revisions` 10건, 공개된 `result_candidates.body`를 확인했다. **PostgreSQL에 직접 SQL을 실행한 결과는 아니다.**
- 운영 주소·노드명·실제 UUID·원본 응답은 공유본에서 제외했다. XID/SXID는 사례 별칭이다. 원본 조회 자료는 점검자 로컬에만 보관되어 이 문서만으로 재현할 수는 없다.
- 아래 SQL 번호는 [verify-flow.sql](verify-flow.sql)의 출력 구간이다. 직접 DB 점검 시 사용할 위치이며, 이번에 실행했다는 뜻은 아니다.

## 한눈에 보는 데이터 흐름

| 과정 | 테이블·조회 조건 / SQL 번호 | 실제 확인값: 두 사례 공통, 차이는 별도 표기 | 판정 |
|---|---|---|---|
| 접수·전달 | `incidents.id=I`, `jobs.incident_id=I`; 01~03 | accepted=1 / invalid=0 응답, 사건 revision=1, policy=`gpu-alert-v1`, 사건당 RCA job 1개 연결 | **연결 정상**. Outbox 행 상태는 미확인 |
| 01 Claim·입력 | `job_attempts(job_id=J,attempt_no=1)`, `evidence.query_id=incident_snapshot`; 02,04,05 | attempt=1 시작·종료 기록, 원문 cluster/node/machine/reason 보존, Worker snapshot input과 공개 job input 일치, knowledge 267개 고정 참조 | **공개된 입력·참조 정상**. 원본 snapshot hash/lease 직접 대조는 미확인 |
| 02 Runbook·계획 | `evidence`의 `alert_clues/runbook_selection/observation_plan`; 06 | `xid:79` 또는 `sxid:11001` 인식, 원문 노드를 runtime target.node에 반영, 해당 Runbook 검색 1위, 필수 D09·D05 계획 | **검색·계획 정상**. 검색 단서가 원인 확정은 아님 |
| 03 Observation | `evidence`의 `D09/D05`: `tool_status/quality/snapshot`; 06 | 각 2행, 합계 4행 모두 `unavailable`, `complete=false`, `reason=query_failed`, `error_type=JSONDecodeError`, `snapshot={}` | **첫 실패 지점**. 실제 관측 미확보 |
| 04 충분성·재조사 | `evidence.query_id=sufficiency`; 06 | round=0, decision=`degraded`, remaining_queries=[D02], followups=0 | **부족 상태 처리**. 현행 degraded 분기는 재조사하지 않음 |
| 05 Synthesis | `evidence.query_id=rca_synthesis`, candidate `body.llm_usage`; 06,07 | `no_usable_evidence`, input_evidence_refs=[], hypotheses=[], calls=0, narrative_status=`omitted` | **LLM 분석 미실행**. 연결 상태 판정 불가 |
| 06 저장 | `evidence(job_id,attempt_no)`, `result_candidates.body`; 06~08 | 각 결과에 evidence 8개, 모두 조회됨. 16개 snapshot checksum 및 job/attempt/scope 일치. body=`blocked`, termination_reason=`query_failed` | **실패 근거·결과 저장 정상**. 원자성/lease fencing의 현장 실증은 아님 |
| 07 JC 발행 | `jobs.published_result_id`, `job_attempts.ended_at`, 연결 candidate; 05,07~09 | jobs=`succeeded`, 공개 결과 ID와 본문 존재, attempt 종료. 본문은 blocked 유지 | **발행 정상 / 분석 차단**. 완료 receipt·개별 슬롯 행 미확인 |

`evidence`의 02~05 과정 기록은 메모리에서 누적한 뒤 06에서 일괄 저장된다. 실행 중 행이 없다고 즉시 고장으로 판단하지 않는다. `evidence.created_at`도 각 내부 단계 실행 시각이 아니다.

## 사례별 차이와 저장 내용

| 항목 | XID 79 | SXID 11001 |
|---|---|---|
| 사건 생성 시각 (KST) | 15:53:51.738391 | 15:54:37.434397 |
| Job 생성 시각 (KST) | 15:53:54.381480 | 15:54:39.380546 |
| Attempt 시작 → 종료 (KST) | 15:53:54.536728 → 15:53:55.170680 | 15:54:39.560780 → 15:54:39.974153 |
| 검색 후보 (순서대로) | RB-XID-79, RB-XID-18, RB-XID-54, RB-XID-115, RB-XID-116 | RB-SXID-11001, RB-SXID-11004, RB-SXID-11009, RB-SXID-23008, RB-XID-58 |
| 필수 수집 결과 | D09 실패 / D05 실패 | D09 실패 / D05 실패 |
| LLM 호출 / 최종 본문 | 0회 / blocked | 0회 / blocked |

- 각 8개 evidence: `incident_snapshot`, `alert_clues`, `runbook_selection`, `observation_plan`, `D05`, `D09`, `sufficiency`, `rca_synthesis`.
- 선택된 Runbook은 조회 당시 모두 published. 본문 hash·reviewed hash·직접 계산한 hash가 일치하고 작업의 고정 knowledge 참조와 맞았다. 공통 compatibility는 현재 두 CPC를 명시한 범위이며 향후 모든 클러스터를 자동 허용하는 설정은 아니다.
- `general_available`도 기록됐지만 전용 후보가 있어 결과에는 전용 후보 5개가 남았다. 이 후보들이 원인으로 확인된 것은 아니다.
- 충분성 부족 항목: `error_code`, `producer_contract`, `incident_mapping`, `causal_confirmation_evidence`. 원문 reason에서 추출한 검색 단서와 검증된 error_code fact는 다르다.
- 원문의 `REBOOT_SYSTEM` 권고는 execution=`not_performed`, eligibility=`withheld`. 최종 recommendations는 빈 배열이며 하드웨어 조치는 수행하지 않았다.
- 로컬 점검의 저장 일관성 검사 40개는 통과했다. 이는 참조·hash·입력 대조 결과이며 관측 성공률이나 RCA 정확도 점수가 아니다.

## 아직 확인하지 못한 항목

| 항목 | 현재 근거 | 추가 확인 |
|---|---|---|
| Receipt·Alert 원장 | 사용자 accepted 응답과 Worker 보존 alert | `incident_webhook_receipts`와 `alert_events`의 receipt 연결 / SQL 01 |
| 원본 immutable snapshot | Worker evidence 복사본과 공개 input 일치 | `incident_evidence_versions.snapshot/content_hash` 직접 대조 / SQL 02,03 |
| Outbox 전달 상태 | 응답의 Outbox ID, 연결된 실제 Job | `enqueue_outbox.status/attempts/job_id` / SQL 03 |
| Candidate 검증 | 공개 candidate body 조회 성공 | `result_candidates.validation_status/content_hash` / SQL 07,08 |
| Complete·슬롯 반환 | job succeeded, attempt 종료 | `job_attempts.completion_response`, 해당 `slot_reservations` / SQL 05,08 |
| 수집 실패 원인 | D09/D05의 JSONDecodeError | 당시 Worker/MCP 로그, 원본 MCP 응답·HTTP 상태·스택 |

공개 evidence에는 원본 MCP 오류 응답과 실패 스택이 없다. `JSONDecodeError`만으로 Loki/Grafana/MCP 설정 문제인지 Worker 해석 문제인지 확정하지 않았다.

## LLM 연결 후 다음 확인

LLM 설정만으로 기존 수집 실패가 해결되지는 않는다. 새 사건의 D09/D05 응답, usable evidence, Synthesis 호출·응답 검증, 결과 저장·발행을 순서대로 확인한다. 기존 blocked 결과나 고정 snapshot을 덮어쓰지 않는다.

[재시험 보고서 양식](llm-retest-report.ko.md)에 단계별 조회값과 근거를 기록한다. LLM 연결 및 새 시험 결과는 이 점검 시점에 **미검증**이다.
