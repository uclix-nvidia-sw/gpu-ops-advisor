# D binding RCA 연결 — 2026-10-06

RCA와 Report는 공통 `agents/config.example.json`의 query/binding registry를 검증한다. Runbook의 D는 이 registry에서만 실행하며, 미선택 후보·생산 불가능한 fact 요구를 실행하지 않는다. 267개 작성 원본의 D05 요구를 D09와 필수 fact로 병합하고 일반 패키지 사본을 맞췄다. D02의 관측 연결은 D06 UID/시간과 함께 확인한다. [구현·적용 순서와 남은 범위](../docs/specs/common/d-binding-runtime.md). 개별 추가 분석·비코드 Runbook과 DB 등록/발행은 미완료다.

# rcca-agent

## Runbook-first RCA — 2026-10-02

신규 실행은 R01~R09, `purpose_ids`, R별 procedure/조회 허용 목록과 `purpose_plan`을 사용하지 않는다. Alert 단서 → 검토된 Runbook 검색·호환성 검사 → `observation_plan`의 필수 조회 → 근거 검사 → 최대 한 번 추가 조회 → Synthesis/보고 순서다. 이 날짜의 작업에서는 D 정의를 변경하지 않았다. 이후 D binding 전환은 위 최신 절을 따른다. 아래 이전 날짜의 R 기반 설명은 과거 동작 기록이다.

- 신규 Incident 입력 1.5(기존 사건 revision 경로), 에피소드 입력 1.4, 기존 입력 1.3을 처리한다. 1.3의 목적 필드는 불변 snapshot 호환을 위해 읽지만 실행을 제어하지 않는다. Worker가 지원 계약을 명시해 구형 Worker에 새 입력을 배분하지 않는다.
- Plan은 Runbook revision/hash/origin, 필수 근거, 조회 단계와 `unexpected_evidence`를 evidence에 고정한다. 조사별 assessment는 `assessment_id`, `question`, `runbook_revision_id`로 표시한다. 과거 `purpose_id` 결과와 snapshot/hash는 수정하지 않는다.
- Runbook의 `required_evidence`와 실제 필수 조회 완료 여부를 검사한다. 미실행·빈 응답·부분·실패를 충분한 근거로 보지 않는다. GPU–Pod 신원/사건 시각·producer/freshness·조치 조건 검증은 유지한다. 조건 충족과 코드 매칭은 다른 단계다.
- `unexpected_evidence`는 `on`(unknown_value/missing_evidence/conflicting_evidence/query_failed), `additional_queries`(등록 D 목록), `fallback`(general_runbook/stop)이다. 추가 조회를 우선하고 stop이면 그 뒤 미확정으로 종료한다. 실패 조회를 반복하지 않고 예산/deadline/취소를 준수한다. 없는 필드는 기존 revision 호환을 위해 추가 조회 없음·일반 조사 전환으로 해석한다.
- 발행 일반 Runbook이 없으면 패키지의 `general_runbook.json`을 사용한다. 이 파일은 `runbooks/RB-GENERAL-GPU-NODE.json`의 content와 일치해야 한다. `origin=builtin` 조사 전용 템플릿이며 발행 지식·원인 판정·조치 허가로 취급하지 않는다. 일반 템플릿은 D09의 로그·상태 fact와 부족 시 D02를 사용한다. 광범위한 D 수집 구조 재설계는 별도 작업이다.

배포 순서는 JC의 007 migration·입력 지원 → 새 Worker → Incident/화면이다. 기존 backlog는 유지하며, 실제 배포와 Runbook DB 발행은 별도 승인 작업이다.

## Bounded synthesis context / 분석 입력 크기 제한 — 2026-10-01

원본 메트릭 전체를 그대로 JSON 직렬화하면 `LLM.complete()`의 보수적 UTF-8 입력 예산을 초과해 HTTP 요청 전에 실패할 수 있다. 전체 `llm_usage.calls`에는 후속 조회 선택과 최종 보고서 편집도 포함되므로 값이 양수여도 원인 Synthesis 호출 성공을 뜻하지 않는다.

- `synthesis_context.py`는 저장된 evidence를 수정하지 않고 모델용 view만 제한한다. 최대 16,000바이트이고 남은 예산에서 system/전송 여유와 8,192의 출력 여유를 뺀 값이 더 작으면 그 값을 사용한다. 실제 output cap과 비용 차감은 기존 LLM transport가 담당한다.
- health, 검증된 relation, metric 순서로 담는다. metric은 사건 노드와 비-inventory 계열을 우선하고 계열당 최대 8개의 균등 간격 원본 인덱스 표본을 전달한다. 새로운 평균·최댓값·연속성을 계산하거나 주장하지 않는다. 생략한 관측/표본 수와 계열별 선택 방법을 `context_selection`/`sample_selection`에 명시하며 보고서 한계에도 남긴다. 최소 메타데이터와 유효 관측을 담을 수 없으면 명시적으로 실패한다.
- 후보의 참조는 실제 선택한 관측의 evidence ID로 제한한다. 숫자 측정값을 자유 문장으로 생성하지 못하며, 인용한 관측의 typed `error_code`와 일치하는 XID/SXID 식별자만 예외로 허용한다. 오류 코드 인용은 원인 확정이나 fact 승격이 아니다.
- 모델 view에 그대로 들어 있는 영문+숫자 식별자 토큰(`D05`, `R01`, `cpc-2`, 노드·Pod 이름, UUID 등)은 그대로 인용해도 숫자 검사에서 제외한다. 토큰은 공백 단위로 추출하며 metric `samples`, ISO 시각, `16GB`·`85C`·`30m` 같은 숫자+단위 값과 `sxid:11001` 같은 오류 코드는 식별자로 보지 않는다(오류 코드는 기존처럼 인용 관측의 typed `error_code`만 허용). 숫자만 있는 값(`GPU 0`), 개수·기간·측정값은 계속 `invalid_limitations`/`unregistered_numeric_claim`으로 거부한다. 운영 작업 `ed730b4d`에서 입력 제한 후 실제 요청 1건이 이 검사로 탈락해 보완했다.
- `quality.analysis.synthesis`와 `rca_synthesis.snapshot.diagnostics`에 단계별 `request_attempts`, `response_calls`, 안전한 `error_code`, 입력 크기와 선택 범위를 저장한다. 모델 원문·외부 예외 문자열은 진단에 저장하지 않는다. 응답 기록도 내용 검증 성공을 의미하지 않는다.

기존 partial/missing-data·producer 시각 계약·GPU–Pod mapping 조건과 취소/원격 추론 종료 불명 처리는 유지한다. DB migration과 기존 결과 재작성은 없다. 운영 적용에는 RCA Worker/Frontend의 승인된 배포와 새 실행 검수가 필요하다. [검증 범위](../agents/QA.md).

DBeaver/PostgreSQL에서는 아래 읽기 전용 조회의 `:job_id`에 새 RCA 작업 UUID를 넣어 분석 단계의 진단을 확인한다. 구 결과는 `diagnostics`가 NULL이며 호출 0회를 뜻하지 않는다. `reason`은 장비 식별용 target이 아니라 사건의 `alert.labels.reason`과 `alert_clues`에 보존된다.

```sql
SELECT query_id, tool_status, quality,
       jsonb_extract_path(snapshot, 'diagnostics') AS diagnostics
FROM public.evidence
WHERE job_id = CAST(:job_id AS uuid)
  AND query_id = 'rca_synthesis';
```

## 보고서 첫 화면 접근 — 2026-09-30

RCA 첫 페이지의 `최종 보고서` 버튼/탭과 공개 작업의 바로가기에서 저장된 다섯 섹션으로 이동한다. RCA 판단·저장·LLM 호출 계약은 변경하지 않는다. 미공개 작업을 최종 보고서로 표시하지 않으며 기존 결과를 재작성하지 않는다.

## 2026-09-30 Fleet RCA 수집·분석 보완

- Loki 경계를 밀리초로 안쪽 정규화한 경우 원본 기간의 `complete=false`와 실제 `request_time_range`를 보존한다. 조회 성공·미잘림·경고 없음이면 `observation_usable=true`로 실제 구간 안의 개별 health 관측을 Synthesis에 전달한다. 기간 전체의 오류 부재·지속 시간·집계가 완전하다는 뜻은 아니다. 다른 partial 사유는 허용하지 않는다.
- 기본 프로필 `builtin-grafana-v5`에서 D05는 D09 원본으로 파생하며 D09는 등록된 `fleet-component-log-v1` adapter로 `attributes.health/component/reason`, `resources["machine.id"]`, `resources["k8s.node.name"]`, Loki ns timestamp와 XID/SXID 코드를 정규화한다. `log_type=component_data`, 알려진 component, 대상과 유효 시각이 필요하다. `Unhealthy`만 등록했으며 미등록 상태는 unknown이다.
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

## Korean synthesis and report labels / 한국어 분석·보고서 표기 — 2026-10-01

기준: `origin/main` `529df747173e76a908ff2d56b1ac3688c4a3e648`, 브랜치 `fix/rca-report-korean-labels`.

- Synthesis `claim`·`limitations`는 한국어 문장이어야 한다. 입력 식별자와 인용한 관측의 typed XID/SXID 코드를 제거한 뒤 typed node/Pod/namespace 필드의 숫자 없는 이름도 식별자로 제외한 뒤 한글 완성형 음절이 하나 이상이고, 영문 알파벳 수가 한글 음절 수 이하여야 한다(두 문자군 중 영문 비중 최대 50%). GPU·PCIe 같은 짧은 기술 용어를 허용하면서 영어 문장에 한글만 덧붙이는 우회를 막기 위한 보수적인 기준이며 언어 의미 판별기는 아니다. 실패는 `non_korean_claim`/`invalid_limitations`로 기록한다.
- 수치는 코드가 관리한다. 영어 수사·수량 단어, 한국어 독립 수사, 수관형사+단위와 한자어 수사+퍼센트를 차단한다. Unicode 단어 경계로 일반 단어 안의 수사 접두사를 제외하며 단위 뒤 조사만 제한적으로 허용한다. `한계·열화·일부·이상·삼성·이번·영향·일반·두께·세부·네트워크` 회귀 검사를 둔다. 모든 한국어 수량 표현을 해석하는 형태소 분석기는 아니다.
- 프롬프트는 가설형 문장과 표본 기반 유휴·고장·정상 추론 및 synthetic/test 단어 기반 원인 해석 금지를 명시한다. 검증기는 명시적인 `원인이다/원인입니다`, `고장이다/고장입니다`, 원인 확정, `physically` 등 좁은 표현만 `unsupported_assertion`으로 거부한다. 모든 `…이다` 종결을 금지하면 관측·불확실성 설명도 오탐하므로 넓은 의미 검증은 하지 않는다. 후보는 계속 미확정이다.
- 시각 정밀도 손실 문구는 모델에 전달한 `query_quality[].quality.reason=time_precision_reduced`가 있을 때만 허용한다. 조건 없는 한계 문구는 `invalid_limitations`로 응답 전체를 거부하며 조용히 삭제하지 않는다. Fleet `fact_eligible=false`·Runbook 계획의 한계도 입력에 존재할 때만 언급하도록 프롬프트를 제한한다.
- `report_labels.py`와 Frontend `rcaLabels.json`의 조회·목적·필수 근거·사유·상태·부족 항목 분류를 동일하게 유지하며 Python 테스트로 비교한다. 모든 실행 D-query를 ID별로 표시하고 여러 구간은 상태/완전성별 구간 수로 묶는다. 표본은 단일 구간만 표시하고 합산하지 않는다. 정상은 수집 상태이며 장비 정상이나 전체 기간의 연속성을 뜻하지 않는다.
- 보고서 대상·종료 사유·미충족 항목을 한국어로 표시하며 원본 코드는 병기한다. 원인 분석 응답 검증 완료와 결과 부분 산출이 함께 나오는 이유를 설명한다. 부족 항목의 네 분류는 확인 방향이며 해당 작업의 exporter 부재나 Fleet 설정값을 추정하는 근거가 아니다.

Fleet 계약·충분성 gate·`REQUIRED`·결과 스키마·DB migration은 변경하지 않았다. 기존 결과는 재작성하지 않으므로 저장된 영어 모델 문장이 소급 번역되지는 않는다. 검증 범위는 [Agent QA](../agents/QA.md)를 따른다.

## ci.110 후속 증거·표시 보정

- Synthesis 한계 문장은 개별 검증 후 탈락 문장만 제외합니다. 가설 검증 실패는 여전히 거부합니다. 남은 요청 예산과 deadline이 허용하면 최대 한 번 교정을 요청하고, 교정 실패 시 앞서 검증된 가설을 보존합니다. 추론 종료 불확실/취소는 기존 worker fencing으로 전파합니다.
- 진단은 문장 위치·고정 규칙·토큰 **분류**만 보존합니다. 임의 모델 토큰은 비밀값일 수 있어 원문을 저장하지 않습니다. `validation_failures`, `rejected_limitations`, `repair_attempts/status/error_code`로 원인을 구분합니다. 전체 job 예산을 현재 LLM 잔여 예산으로 해석하지 않습니다.
- XID/SXID 구성 요소 단서는 `gpu_access` 조사 절차를 선택하지만 검증된 사실은 아닙니다. R02/R03의 필수 D08/D06 조회는 별도로 유지합니다.
- R01의 공개 assessment enum은 변경하지 않습니다. `quality.analysis.reported_errors`는 보고된 코드이며 Runbook applicability, verified facts, 조치 적격성을 높이지 않습니다. 유효한 발생 시각·신원 계약 없이 `reported`를 새로운 충분성 상태로 만드는 것은 안전 계약과 충돌합니다.
- Fleet `gpuInfo.gpus`는 시각·근거가 있는 **미검증 신원 후보**로 보존합니다. GPU 한 장이라는 로그만으로 사건 시각의 장애 GPU를 확정하지 않습니다. 검증된 inventory freshness/device-time 계약이 제공될 때까지 `mapping_target_unverified`를 유지합니다.
- 라벨의 단일 원천은 `src/rcca_agent/report_labels.json`입니다. 수정 후 저장소 루트에서 `python tools/generate_rca_labels.py`를 실행하여 frontend JSON을 생성합니다. Python 패키지 데이터에도 포함하며 기존 mirror 일치 테스트를 유지합니다.
