# 04. DSX Agent 동작·판단 명세서

문서 ID: DSX-AGENT-001 · 버전: 1.2 · 기준일: 2026-09-17 · 상태: 개발 기준

대응 요구사항: F05·F06·F09·F10·F11, N01~N04. 공통 데이터·식별은 03, 작업 실행은 15를 따른다. 기존 공통 판단 기준 v1.0의 산식과 5%·60분·95%·90% 값을 유지한다. 짧은 할당·후보 단위·시간창 정렬·수치 참조·검사 유효성의 빈칸을 v1.1에서 정했으므로 새 실행의 criteria_version은 1.1로 기록한다. 과거 결과를 소급 재판정하지 않는다.

문서 버전 1.2는 실행 경계 개정이다. 아래 criteria_version·result_schema_version 1.1과 수치 계산 계약은 그대로 유지한다. 전문 job 수명주기는 [15](15_모듈간_호출과_공통실행_계약.md)의 Agent 공통 커널을 사용한다.

## 1. 공통 역할과 상태

공통 도구는 조회·연결·계산·품질·규칙을 결정적으로 수행한다. LLM은 사실 설명·후보 정리·등록된 다음 조사의 선택을 맡는다. 일반 Assistant는 요청 해석과 기존 결과 설명·가벼운 조회를 처리하고 긴 RCA·보고서는 해당 전문 작업으로 접수한다.

| 축 | 값 | 해석 |
|---|---|---|
| 작업 실행 | queued/running/retry_wait/succeeded/failed/cancelled/expired | 접수·실행·저장 상태. 15 기준 |
| 조회 도구 | ok/partial/empty/unavailable/parse_error | 저장소 접근·응답 상태. 03 기준 |
| 분석 주제 | ready/partial/blocked/not_applicable | 근거가 충족하는 산출 범위 |
| Pod 배치 | unbound/bound/unknown | 노드 바인딩. 원래 phase·condition은 별도 보존 |
| GPU 관계 | matched/ambiguous/not_observed/unknown | 실제 장치 관계의 관측·모호성 |
| GPU 활동 | active_observed/low_activity_candidate/insufficient_data/not_applicable | 아래 시간창·품질·규칙에 따른 관측 |

job이 succeeded라도 과거 할당시간은 blocked일 수 있다. 부분 조회가 모든 주제 실패를 뜻하지 않는다. ‘Pending→Mapped→Active→Released’ 하나의 상태 흐름으로 합치지 않는다.

작업 목록·결과 상단의 `result_status`는 서버가 다음 규칙으로 계산해 final에 저장한다. 보고서는 요청한 topics[].status, RCA는 요청한 purpose별 assessments[].status를 사용한다. not_applicable을 제외한 항목이 모두 ready면 ready, 유효한 ready 또는 partial이 있으면서 다른 항목의 부족/부분 산출이 있으면 partial, 적용 대상이 모두 blocked면 blocked, 적용 항목이 하나도 없으면 not_applicable이다. partial만 있는 경우도 partial이다. 결과 미발행은 null이며 succeeded 여부와 혼합하지 않는다. narrative_status도 별도이므로 result_status=ready에 설명 실패가 함께 있을 수 있다.

## 2. 공통 실행 순서

1. 요청자의 현재 권한과 scope·target·기간·시간대를 검증하고 입력을 정규화한다.
2. 데이터 마감 시각·등록 query/procedure·파서·산식·정책·지식·모델 버전을 고정한다.
3. 각 주제의 필수/보조 입력을 검사한다. 원본 시각·의미·단위·모델 지원·완전성 조건을 적용한다.
4. 허용된 query ID로 필요한 범위만 조회하고 근거 스냅샷·tool_status를 남긴다.
5. 같은 신원·시간 구간으로 연결하고 중복·공백·상충·센티널 값을 처리한다.
6. 주제별 수치·품질·사실·미확인 정보를 만든다. 실패한 입력에 의존하지 않는 분석은 계속한다.
7. 공유 추론 한도 내에서 LLM이 설명 또는 등록된 추가 조사를 요청한다. 서버가 다시 권한·예산·도구 입력을 검사한다.
8. 구조화 결과와 설명의 대상·숫자·인용·판단 수준을 대조한 뒤 최종 저장한다. 취소·만료·무효 attempt는 결과를 발행하지 않는다.

## 3. RCA 입력과 조사 절차

R01~R09의 입력·조사·등록 절차·상태 판단은 [11 RCA Agent 모듈 설계서](11_RCA_Agent_모듈_설계서.md) §3을 따른다. RCA 내부 API와 Worker는 Backend와 별도 실행한다.

## 4. 운영보고서 입력과 처리

O01~O11의 입력·집계·출력은 [12 보고서 Agent 모듈 설계서](12_보고서_Agent_모듈_설계서.md) §3을 따른다. Chatbot의 대화·전문 요청 분기는 [10](10_Chatbot_Agent_모듈_설계서.md)을 따른다.

## 5. 계산 기준 v1.0

절의 산식은 v1.0에서 유지한다. 추가한 후보 적격성·구간 처리까지 포함한 실행 정책 버전은 v1.1이다.

### 5.1 구간·중복·분모

전용 GPU의 같은 할당 대상·시간에 여러 컨테이너/생산자 관측이 있어도 유효 구간 합집합을 한 번 센다. 동일 물리 GPU를 여러 Namespace가 공유하면 물리 합계는 한 번, 공유 관계 수는 따로 표시한다. MIG는 구성·프로파일별 instance-hours이며 물리 GPU-hours와 합산하지 않는다.

필수 입력들의 **동시 유효 구간 교집합**을 공동 관측 구간으로 사용한다. 개별 커버리지 평균·최솟값으로 대체하지 않는다. 분모는 주장별 기대 GPU·시간, 유효 할당 대상·시간, 기대 Node·시간으로 명시한다. 기대 대상/할당 이력 자체가 없으면 분모와 전체 커버리지는 null이다.

0은 관측된 유효 0이다. 수집 실패·미지원·센티널·오래된 값은 null과 이유로 처리한다. counter 리셋·기기 교체·소스 변경 경계는 각각 검증한 구간만 계산한다.

할당 이력의 기준은 공통 조회 모듈이 Mimir에 보존된 원본 표본 시각·관계·수집 완전성으로 복원한 구간이다. UI를 열었는지와 관계없이 보존 기간 안의 같은 입력을 사용한다. 시각·완전성·해상도 또는 보존이 부족하면 해당 기간 계산만 보류한다. 복원 방법과 스냅샷 저장은 03의 이력 생성 계약을 따른다.

계산용 query revision은 원본 관측 시각·원본 주기·값 유지·구간 경계·chunk 겹침 제거·최대 유효시간을 고정한다. 범위 조회의 평가 시각이나 차트 점 수를 원본 샘플 수로 사용하지 않는다. 저장소가 지원하면 원본 range-vector 표본을 제한된 chunk로 조회해 사용하며, 원본성이 확인되지 않는 다운샘플 자료로 급증·시간·P95를 확정하지 않는다. UI chart_step은 표시 전용이고 이미 저장된 계산 결과를 바꾸지 않는다.

### 5.2 산식

| 지표 | 산식·단위 | 제한 |
|---|---|---|
| 현재 전용 할당 | 기준 시각에 유효한 전용 고유 GPU 수 | 불완전 매핑이면 확인된 수량·범위만 |
| 할당 GPU-hours | Σ(전용 GPU별 유효 할당 구간 합집합 초)/3,600 | 활동값 없어도 계산 가능, 과금 원장으로 보장하지 않음 |
| 저활동 GPU-hours | Σ(할당∩활동 유효∩util<5% 구간의 GPU·초)/3,600 | 선정된 시간창 전체로 대체하지 않음 |
| 평균 활동률 | Σ(util%×유효 GPU·초)/Σ(유효 GPU·초) | 동일 의미·모델/공유 방식, 분모 0이면 null |
| 시간 가중 P95 | 값 오름차순 누적 유효시간이 전체의 95% 이상이 되는 최소 값 | 시간 분포/장치 간 분포를 구분, 샘플 개수 동일 가중 금지 |
| 미배치 요청 | 종료/삭제 아닌 unbound Pod의 검증된 유효 요청 합 | 실제 resource 단위, init/sidecar/overhead 규칙은 배포 버전별 등록 |
| 관측 미배치 요청시간 | Σ(유효 요청량×확인된 미배치 구간 시간) | 처음 관측 전 대기는 미확인. GPU 부족 시간으로 치환 금지 |
| 미할당 GPU-hours | 인벤토리와 완전한 할당 조회에서 부재 확인된 GPU·시간 | mapping 실패/Pod 종료는 충분조건 아님 |
| 사건 발생률 | 중복 제거 사건 수/유효 사건 관측 GPU-hours×1,000 | 총 건수·모델·기간도 함께 표시 |
| GPU 에너지 | Σ(W×유효 초)/3,600,000 kWh | v1 전력 적분은 유효 유지 구간의 좌측 값. 공백·리셋 제외 |

공통 v1의 전력 적분을 구현하기 위해 좌측 유지값 방식을 채택한다. 원본 최대 유효시간을 초과해 연장하지 않는다. 검증된 누적 에너지 계수를 쓰면 구간 증가량·단위·리셋 규칙을 별도 계산 revision에 명시하고 전력 적분과 중복 합산하지 않는다.

### 5.3 품질·저활동 정책

| 항목 | v1 값 |
|---|---|
| 일반 기간 비교·순위 | 공동 커버리지 95% 이상. 핵심 사건/시간대가 빠지면 충족해도 보류 |
| 저활동 대상 | 확인된 전용 GPU 할당. 공유 장치 활동은 별도 보기 |
| 시간창 | 60분 |
| 저활동 임계값 | 정규화 GPU utilization 5% 미만 |
| 후보 조건 | 공동 커버리지 ≥95%, 유효 할당·활동 시간 중 저활동 비율 ≥90% |
| 보조 근거 | VRAM·검증된 SM·업무 유형. SM 부재만으로 일반 활동 분석 차단 안 함 |
| 예외 확인 | 초기화·체크포인트·추론 대기·예약 목적 등. 목적 불명은 일반 검토 후보 |

검증된 5% 이상 활동이 있고 저활동 후보 조건은 충족하지 않으면 active_observed다. 후보가 되면서 일부 활동도 있으면 low_activity_candidate와 활동 구간을 같이 표시한다. 품질 미달은 insufficient_data다. 저활동 후보는 낭비·회수 가능·성능 비효율 확정이 아니다.

**장시간 후보 적격성 v1.1:** 후보 단위는 `cluster_id+gpu_uuid+pod_uid+allocation_episode_key`의 전용 할당 관계다. 같은 Pod의 각 GPU는 개별 판정하며 다른 Pod A→B의 시간을 합쳐 한 후보를 만들지 않는다. episode_key는 검증된 신원·연속 관측·할당 방식과 관계 변경 경계로 정하고, 실제 할당 이벤트가 없으면 ‘관측된 episode’라고 표시한다.

검증된 관측 episode의 시작을 기준으로 겹치지 않는 60분 창을 만든다. 실제 시작이 불명확하면 최초 유효 관측을 기준으로 한 창임을 남긴다. episode가 끝나거나 분석 구간 경계로 잘린 60분 미만 구간은 관측 저활동 시간만 제공하며 장시간 후보 판정은 `insufficient_data`, 이유 `short_allocation_window`로 보류한다. 새로운 최소 시간 숫자를 더하지 않고 기존 60분 창 전체를 후보의 최소 범위로 적용한다.

60분 창 내부의 관측 공백은 공동 유효시간에서 빠지며 분모 60분에는 남는다. 따라서 58분 유효·54분 저활동의 기존 예는 그대로 후보가 된다. 5분만 할당·관측한 경우 할당 구간의 관측률이 100%일 수 있어도 장시간 후보는 아니다. 30분 A→30분 B는 각각 관측 저활동 시간만 보고한다. 유효 활동이 있는 짧은 구간의 실제 활동 사실은 별도로 제공한다.

### 5.4 고정 계산 예

아래는 시험 데이터이며 실제 CPC 측정 결과가 아니다.

| 입력 | 기대 결과 |
|---|---|
| 전용 GPU 2개, 각 8시간 유효 할당·각 5시간 저활동 | 할당 16 GPU-hours, 저활동 10 GPU-hours |
| 60분 중 공동 관측 58분, 저활동 54분 | 커버리지 96.6667%, 저활동 비율 93.1034%, 후보=true, 저활동 0.9 GPU-hours |
| 같은 정의의 G1 4건/100 GPU-hours, G2 5건/500 | 발생률 각각 40·10건/1,000 GPU-hours, 총 건수 4·5 |
| GPU 4개×10시간, 전 250W/후 200W, 전 구간 유효 | 10kWh→8kWh, 관측 감소 2kWh. 조치 인과는 별도 |
| Pending 6개, 그중 4개 bound, 2개 unbound·각 유효 GPU 요청 1 | 미배치 요청 2단위. GPU 부족량은 scheduler 근거 없으므로 null |
| 공유 G1에 A·B, G1 활동 80% | 물리 GPU 1, 공유 관계 2. A/B 실사용률 각각 null |
| 60분 중 한 Pod가 5분만 전용 할당, 그 5분은 모두 저활동 | 관측 저활동 1/12 GPU-hours. 장시간 후보 보류, short_allocation_window |
| 전용 G1이 같은 60분에 A 30분→B 30분, 각각 모두 저활동 | A/B 각각 0.5 관측 저활동 GPU-hours. 둘을 합친 장시간 후보 금지 |

## 6. Knowledge 계약

| 역할 | 담을 내용 | 적용 방식 |
|---|---|---|
| Runbook | 의미·producer 계약·모델/버전·필수 증거·조건·권고·출처 | 정확 조건 후보 검색 후 권고별 적용 가능 검사 |
| 조사 procedure | 등록 ID·버전·입력·분기·종료·한도 | 코드 등록 함수. LLM이 임의 절차를 실행 코드로 등록하지 않음 |
| 운영 정책 | 품질·우선순위·조회 예산·권고 예외 | 발행 revision 사용 |
| 데이터 사전 | D 항목·원본 의미·단위·지원·query ID | 해당 source·모델·기간에 적용 |
| 참고·검증 사례 | 공식/내부 원문·실제 검토 결과·출처 | 후보·설명 보완. 검증 수준 명시 |

초안 draft→검토 요청 in_review→검토 완료 reviewed→발행 published→폐기 retired 흐름을 사용한다. 검토 action=request/approve/request_changes를 02 API로 처리하며 수정 요청·검토 후 내용 수정은 draft로 돌리고 재검토한다. 발행은 검토한 content_hash가 일치해야 한다. 발행 content는 불변이고 신규 revision으로 수정한다. 폐기는 신규 실행 선택만 막으며 과거 실행 인용은 보존한다.

기술 호환 범위와 데이터 공개 범위는 별도다. Knowledge 검색·초안/발행 상세·LLM 입력·근거는 해당 지식의 visibility/scope와 현재 사용자 권한을 검사한다. 실제 사건 기반 사례를 공통 지식으로 발행할 때는 비식별 내용·참조 공개 가능성 검토가 필요하다. 지식 관리자 역할만으로 모든 CPC의 원문을 읽을 수 없다. 등록 procedure는 읽기 전용 메타데이터이며 화면에서 임의 실행 코드를 편집·발행하지 않는다.

지식 선택은 **호환 계약·모델·소프트웨어·정책 범위로 먼저 제한한 뒤 그 안에서 최신 발행본**을 고른다. 계약 B용 revision 2가 있다고 계약 A용 revision 1을 전역 최신 규칙으로 제거하지 않는다. supplier 권고와 DSX 정책은 출처를 구분한다. 필수 증거가 부족한 특정 권고만 보류하고 가능한 로그 확인 등의 권고는 유지한다.

LLM 결과·사용자 메모·유사도 높은 문서를 자동으로 검증된 지식에 발행하지 않는다. 결과의 근거·실제 운영 확인·검토를 거쳐 새 revision으로 등록한다.

## 7. LLM 입력·도구·출력 검사

LLM 입력에는 요청 scope·시간, 구조화 사실/수치·품질·evidence ID, 호환 발행 지식의 필요한 구간, 허용 도구·예산만 포함한다. 원시 메트릭·전체 Loki 로그를 통째로 전달하지 않는다. 로그·문서 안의 지시문은 분석 데이터로 취급하고 서버 권한·실행 규칙을 바꾸지 않는다.

허용 도구는 자산 해석, 현재/과거 매핑, 등록 메트릭·로그 조회, 사건 이력, 제공되는 Pod 근거, Knowledge 조회다. 임의 SQL/PromQL/LogQL·쉘·장비 변경 도구를 노출하지 않는다. 도구 출력의 숫자를 다시 추정하지 않는다.

저장 전에는 JSON 스키마, 필수 필드, enum, 대상 scope, evidence ID 존재, 값·단위·기간·반올림 일치, 인과 판단 승격, 권고 선행 조건을 검사한다. 사실·수치는 구조화 값에서 렌더링하고 설명에 있는 수치 참조도 해당 필드와 연결한다. 검증 실패는 제한된 재생성 또는 설명 생략으로 처리하며 잘못된 설명을 정상 결과로 저장하지 않는다.

수치 주장에는 §8의 value_refs가 필수다. evidence ID가 존재하는지만 검사하지 않고 참조된 값의 대상·기간·단위·산식·source가 문장 주장과 맞는지 검사한다. `%↔비율`, `W↔kWh`, 현재 수량↔기간 합계를 임의 변환하거나 같은 숫자의 다른 대상을 인용하면 발행을 차단한다. 인과 확정은 검토된 confirmation_rule과 근거 검사로 제한하며 LLM의 자기 평가를 검증 수단으로 사용하지 않는다.

Nemotron 3 Super는 기존 초기 후보를 유지한다. 실제 서빙 가능 여부·모델/엔진·정밀도·GPU·동시 처리 수치는 C06/C07에서 평가·기록한다. 모델 교체 시 아래 동일 사례와 T40을 재검증한다.

## 8. 결과 계약

공통 최종 결과는 `job_id,kind,scope,target?,time_range,timezone,data_cutoff_at,result_schema_version,versions,result_status,measurements,facts,evidence_refs,quality,narrative_status,limitations`를 포함한다. result_schema_version은 1.1이다. scope는 02의 CPC별 namespaces 구조다. narrative_status는 complete/failed/omitted이며 작업 성공·result_status와 별개다.

facts는 `id,text,evidence_refs,value_refs`를 갖는다. 수치가 없으면 value_refs는 빈 배열이다. 수치 원본은 RCA·공통 도구의 measurements 또는 보고서 topics[].metrics 중 한 곳에만 두며 각 value의 id는 결과 전체에서 유일하다. value_refs는 그 id들의 배열이다. value는 `id,value,value_type,unit,target,period,method,quality,evidence_refs`를 포함한다. value_type은 number/integer/ratio/percentage이고 null은 quality.reason이 필수다. 백분율 값 3과 비율 0.03은 서로 다른 단위로 유지한다. measurements와 metrics를 수치 레지스트리로 해석하며 문장·HTML/CSV는 그 값을 참조해 렌더링한다.

RCA는 `incident_id?,incident_time?,current_checked_at,pod_relations,assessments,cause_candidates,recommendations,missing_inputs,termination_reason`을 추가한다. assessments는 요청한 purpose_id별 status·missing_inputs·evidence_refs이며 결과 상단 산출 상태 계산에 사용한다. 후보는 `id,claim,causal_status,supporting_refs,contradicting_refs,value_refs,missing_inputs,confirmation_rule_ref?`, 권고는 `text,preconditions,eligibility=eligible|withheld,reason,evidence_refs,value_refs,execution=not_performed`를 가진다.

보고서는 `topics[]`를 추가한다. 각 주제는 `topic_id,status,metrics,facts,findings,missing_inputs,quality,evidence_refs,recommendations`를 가진다. metric은 공통 value 필드에 denominator를 추가하며 값이 null이면 이유가 필수다. O10에는 입력 action_record_ids와 비교 기간, O07에는 실제 resource/단위를 결과에 보존한다.

```json
{
  "job_id": "7af117a4-c4bb-4b57-8f0b-d08fc88bfd1c",
  "kind": "report",
  "result_schema_version": "1.1",
  "scope": {"clusters": [{"cluster_id": "cpc-2", "namespaces": ["dev"]}]},
  "time_range": {"start": "2026-09-15T01:00:00Z", "end": "2026-09-15T02:00:00Z"},
  "timezone": "Asia/Seoul",
  "data_cutoff_at": "2026-09-15T02:01:00Z",
  "versions": {"criteria": "1.1", "query": "test-v1.1", "model": "not_used"},
  "result_status": "partial",
  "measurements": [],
  "facts": [],
  "evidence_refs": ["943cb0e4-6279-4c83-8d25-536b810d35c5"],
  "quality": {"history_coverage": null},
  "narrative_status": "omitted",
  "limitations": ["기간 이력 없음"],
  "topics": [{
    "topic_id": "O02",
    "status": "partial",
    "metrics": [
      {"id": "O02.current_allocated_gpu", "value": 2, "value_type": "integer", "unit": "physical_gpu", "target": {"cluster_id": "cpc-2", "namespace": "dev"}, "period": {"at": "2026-09-15T02:00:00Z"}, "denominator": null, "method": "unique_exclusive_devices", "quality": {"scope": "observed_mapping"}, "evidence_refs": ["943cb0e4-6279-4c83-8d25-536b810d35c5"]},
      {"id": "O02.allocated_gpu_hours", "value": null, "value_type": "number", "unit": "GPU-hours", "target": {"cluster_id": "cpc-2", "namespace": "dev"}, "period": {"start": "2026-09-15T01:00:00Z", "end": "2026-09-15T02:00:00Z"}, "denominator": null, "method": "valid_interval_union", "quality": {"reason": "mapping_history_missing"}, "evidence_refs": []}
    ],
    "facts": [{"id": "F-current", "text": "현재 확인된 전용 할당 GPU는 2개다.", "value_refs": ["O02.current_allocated_gpu"], "evidence_refs": ["943cb0e4-6279-4c83-8d25-536b810d35c5"]}],
    "findings": [],
    "missing_inputs": ["mapping_history"],
    "quality": {"history_coverage": null},
    "evidence_refs": ["943cb0e4-6279-4c83-8d25-536b810d35c5"],
    "recommendations": []
  }]
}
```

예시의 현재 수량은 기간 집계와 다른 기준 시각을 명시한다. 결과에 실제 evidence·query·모델 revision을 채우는 것은 실행 책임이다. 표·파일도 저장된 값에서 생성하며 화면마다 산식을 다시 적용하지 않는다.

## 9. 합격 기준

R01~R09와 O01~O11은 각각 정상·필수 입력 부족·독립 부분 성공을 검증한다. 알려진 오류만 처리하고 미등록 조사를 빠뜨리거나, 운영보고서를 단순 지표 나열로 끝내지 않는다. 확인된 사실→운영 검토 대상→근거→다음 확인의 연결이 있어야 한다.

정확한 검증 절차·허용 오차·실행 증거는 [05 검수 기준서](<05_테스트_검수_기준서.md>)의 T10~T21·T38~T40을 따른다. 데이터 계약은 [03](<03_데이터_설계서.md>), 작업·호출 예산은 [15](15_모듈간_호출과_공통실행_계약.md)와 [06](<06_배포_운영_인계서.md>)을 따른다.
