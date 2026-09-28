# LLM 연결 후 RCA 재시험 보고서 양식

**상태: 미실행.** 아래는 다음 시험의 기록 양식이며 성공 결과를 미리 적은 문서가 아니다. [이전 점검](2026-09-28-flow-review.ko.md)의 D09/D05 실패와 비교한다.

## 시험 정보

| 항목 | 기록값 |
|---|---|
| 시험·조회 시각과 시간대 | 미기록 |
| 배포 이미지/커밋, input/result 계약 버전 | 미확인 |
| 케이스 / 클러스터·대상 별칭 | 미기록 |
| 알람 발생 방식 | 실제 Grafana 평가 / Incident webhook 직접 주입 중 실제 방식 기록 |
| Incident / evidence revision / Job / attempt / candidate | 원본은 접근 제한된 점검 기록에 보관, 공유본은 별칭으로 연결 |
| 조회 방식 | 직접 SQL / Backend GET / Worker·MCP 로그별로 구분 |
| LLM 설정 변경 | 모델·연결 방식·변경 시각만 기록, 키·인증 헤더 제외 |
| 이전 시험 이후 변경 사항 | LLM 설정, MCP 응답 처리, query binding 등의 실제 변경만 기록 |

## 단계별 결과

판정은 **정상 / 문제 / 미실행 / 미확인**으로 기록한다. “정상”에는 실제 값과 근거가 필요하다. 실패가 발생해도 뒤 단계의 차단 처리·저장·발행 여부를 따로 확인한다.

| 과정 | 조회할 테이블·필드 (verify-flow.sql 구간) | 판정 기준 | 실제 조회값·근거 | 판정 |
|---|---|---|---|---|
| 접수·전달 | receipt/alert_events, incidents, enqueue_outbox, jobs (01~03) | accepted, 사건 revision, Outbox→Job 연결 확인 | 미조회 | 미확인 |
| 01 Claim·snapshot | job_attempts, incident_evidence_versions, jobs.input_snapshot/versions (02~05) | 동일 사건·revision·고정 hash, 현재 attempt 연결 | 미조회 | 미확인 |
| 02 Runbook·계획 | evidence: alert_clues/runbook_selection/observation_plan; knowledge_revisions (04,06) | 실제 코드 단서·대상·고정 Runbook과 계획이 일치 | 미조회 | 미확인 |
| 03 수집 | evidence: D09/D05 및 추가 query의 input/snapshot/tool_status/quality (06) | 응답 해석 성공, 대상·시간 범위 일치, 완전성/producer 의미 확인. empty는 원인 입증 아님 | 미조회 | 미확인 |
| 04 충분성 | evidence: sufficiency (06) | decision·gaps·추가 query 선택/미실행 이유가 실제 관측과 일치 | 미조회 | 미확인 |
| 05 LLM 분석 | evidence: rca_synthesis, candidate body.llm_usage/quality.analysis (06,07) | usable evidence와 input_evidence_refs 존재, 실제 호출·응답 검증, 근거에 맞는 후보/한계. 호출 수만으로 성공 판정 금지 | 미조회 | 미확인 |
| 06 결과 저장 | evidence, result_candidates (06~08) | 같은 job/attempt, 참조 누락 없음, validation_status/hash, result_status·missing_inputs가 실제 결과와 일치 | 미조회 | 미확인 |
| 07 JC 발행 | jobs.published_result_id/status, job_attempts.completion_response, slot_reservations (05,08,09) | 발행 포인터·attempt·hash 일치, 완료·슬롯 반환, Backend에서 같은 결과 조회 | 미조회 | 미확인 |

## 조회 방법과 보완 확인

[verify-flow.sql](verify-flow.sql)을 사용한다. 실행 예시와 DBeaver 적용 방법은 [README](README.md)의 “조회 SQL 실행”에 있다. 실제 ID를 지정하고 읽기 전용 연결로 실행한다. SQL은 이번 문서 업데이트에서 새로 실행하지 않았다.

기존 SQL 06은 D-query metadata/input/quality와 내부 과정 snapshot을 출력한다. D09/D05 원문 snapshot은 해당 evidence ID로 별도 조회하고, LLM 호출 수는 candidate body에서 추가 확인한다. 아래 UUID는 실제 조회값으로 교체한다.

```sql
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '10s';

SELECT id, job_id, attempt_no, query_id, tool_status, quality, snapshot
FROM evidence
WHERE id = '00000000-0000-0000-0000-000000000000'::uuid;

SELECT id, job_id, attempt_no,
       body->'llm_usage' AS llm_usage,
       body->>'narrative_status' AS narrative_status,
       body->'quality'->'analysis' AS analysis
FROM result_candidates
WHERE id = '00000000-0000-0000-0000-000000000000'::uuid;

COMMIT;
```

직접 DB 접근 없이 Backend API로만 확인했다면, 숨겨진 hash/validation_status/receipt/슬롯 필드를 정상으로 추정하지 않고 미확인으로 남긴다. 아직 실행 중이면 jobs/attempts의 상태를 기록하고, 06 저장 전의 evidence 부재와 실제 수집 실패를 구분한다.

## 최종 판정에 반드시 남길 내용

- **연결·저장·발행:** 어느 단계까지 어떤 식별자로 연결됐는지.
- **관측·분석:** 유효 관측 확보 여부, LLM 실제 호출·응답 검증, 최종 result_status와 남은 한계.
- **첫 문제 지점:** 테이블/필드의 실제 오류값, 영향받은 후속 단계, 추가로 필요한 로그.
- **이전 시험과 비교:** D09/D05 JSONDecodeError, usable evidence, LLM 0회, blocked 상태가 각각 어떻게 바뀌었는지.
- **미확인 범위:** 직접 DB 미조회, 배포 버전 미확인, 실제 Grafana firing/resolved 미시험 등을 구체적으로 기록.

Grafana 이력까지 검증하려면 실제 규칙에서 firing/resolved가 전송되는 별도 사례가 필요하다. 직접 webhook 주입은 Grafana 이력을 만들지 않는다. resolved 수신, Incident 알람 상태, 수동 종결 상태, RCA 결과는 각각 구분해 확인한다. 재부팅 등 실제 복구 조치는 이 점검에 포함하지 않는다.
