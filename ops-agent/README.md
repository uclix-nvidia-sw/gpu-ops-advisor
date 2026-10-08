# D binding Report 연결 — 2026-10-06

[공통 전환 기록](../docs/specs/common/d-binding-runtime.md)을 따른다. 새 profile에서는 D01/D08 역할을 D02로 통합하고 D06 UID/시간 연결을 보존한다. 매핑 §6의 기본 추가 D를 선택하며 실패는 기존 수치와 분리한다. O01 여유량·용량 비율·CPU·window별 load와 Node condition 관측을 연결했다. 전체 조건부 조사/신규 산식은 미완료다. 미선택 후보는 원격 조회하지 않는다. 구 profile의 기존 산식과 계획은 회귀검사로 유지한다.

## O01 추가 관측 결과의 고유 ID — 2026-10-08

D03·D15·D16·D18·D19를 소비하는 O01 추가 지표는 한 보고서에 여러 GPU·Node·load 시간창의 결과를 만든다. 각 지표 ID는 기존 다중 행 방식인 `O01.<metric_name>.<순번>`을 사용하며, 항목별로 0부터 증가한다. 단일 결과와 자료 부족으로 남기는 null 행에도 순번을 붙인다. 이 번호는 보고서 내부 행 식별자이며 보고서 간 영구 장비 식별자가 아니다. 실제 대상은 기존 `target`에 보존한다.

값·단위·기간·대상·근거·부족 사유·행 수는 바꾸지 않으며, 같은 target으로 표시되는 별도 원천 시리즈도 ID 충돌을 피하려고 삭제하거나 합치지 않는다. 결과 전체의 중복 ID 검증은 그대로 유지한다. 화면·보고서 문장·Backend 내보내기는 기존 `O01.<metric_name>`과 새 순번 형식을 모두 읽는다. 과거 결과·실패 이력은 재작성하지 않으며 배포 후 새 요청의 발행을 확인한다. 시간 초과·공통 Worker 로깅·JC 슬롯 정책은 이번 수정 범위가 아니다.

# ops-agent

운영 보고서 Worker이며 JC kind는 `report`다. 하나의 job/attempt/lease 안에서 **입력·DB snapshot 고정 → 수집 계획 → 병렬 Observation → 결정적 계산 → 보고서 문장 선택 → 저장·JC 공개**를 수행한다. 일정 계산은 Backend가 담당한다.

## 계획과 병렬 수집

`collection.py`는 중복 query를 합치고 query+CPC+기간별 독립 Observation task를 만든다. 비교 기간은 별도 task다. 실제 조회 전 전체 초기 호출량·설정·범위를 검사한다. 각 task의 query/discovery 예산을 예약하고 의존성이 해결된 task를 한 배치로 실행한다. 배치 종료 후 미사용 예산을 다음 task에 배분한다. 실패는 해당 근거에 남기고 독립 결과를 보존하며, 취소 시 모든 task를 회수한다. RCA와 공통 bounded runner를 사용한다.

`report.limits` 예시는 `max_queries=2048`, `chunk_seconds=86400`, `max_rows=50000`, `max_concurrency=3`이다. 네 키만 양수 정수로 받으며 미지정 키는 기존 공통 limits를 사용한다. 동시성 1은 순차 실행이다. 원본 표본·응답 크기·전체 deadline·최대 기간은 보존한다. 세부 예산·시간 배분은 [설계서](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md#기간-수집예산-분리--2026-10-01)를 따른다.

`builtin-grafana-v7`의 `report.query_chunk_seconds={"D06":7200}`은 D06(Pod 신원 이력)의 초기 조회 구간을 최대 2시간으로 제한한다. 등록된 query ID와 양수 정수만 허용하며 전체 `chunk_seconds`와 query별 값 중 작은 값을 계획·실행에 똑같이 적용한다. 맵이 없으면 기존 전체 구간 설정을 사용하고, 다른 query는 예시의 24시간을 유지한다. D06의 원본 표본·Pod UID·연결 시각을 보존한다. 2시간은 확인한 하루 약 32MiB의 전송·처리량과 Agent의 2MiB·50000표본 한도를 고려한 초기 상한이다. Prometheus의 고정 10MiB 제한을 전제로 하지 않으며, 응답 밀도·추가 분할에 따라 예산을 소진할 수 있으므로 월간 완료를 보장하지 않는다.

수집기는 Mimir/Prometheus·Loki의 수신 응답 크기·표본 한도를 넘거나 알려진 MCP 원격 크기 초과 오류를 받으면 기존 예산 안에서 구간을 줄인다. 확인된 원격 10MiB 상한은 Loki에 한정하며, Prometheus 원격 오류 복구는 오류 주입 fixture 검증이다. 일반 timeout·연결 실패를 같은 구간에서 무조건 반복하지 않는다. 공통 `grafana_mcp`는 HTTP 제한을 도구 제한보다 5초 길게 두고 연결 수명을 별도 task로 관리한다. 실패한 호출은 재실행하지 않으며 다음 예산 내 호출에서 연결을 다시 열 수 있다. 세션 종료 404도 연결을 정리한 뒤 다음 호출에서 복구한다. 두 Worker에 적용되는 공통 전송 변경이며 RCA 계산 정책은 유지한다. 구간별 안전한 진단 로그와 배포 범위는 [공통 실행 문서](../agents/README.md#grafana-조회와-llm-오류-진단)를 따른다.

동일 CPC·기간·metric task에는 순서를 두어 완전한 동일 Prometheus 응답을 재사용한다. 도구·데이터소스·범위·표현식·시각·구간이 모두 일치해야 하며 query/evidence ID와 `quality.reused_from_evidence`를 보존한다. 실패·부분·대용량 폐기 응답과 Loki는 재사용하지 않는다. 완료된 캐시만 복사하고 실행 중 상태는 공유하지 않는다. O08 단독 namespace의 D06은 새 profile의 D02(구 D01/D08) 완료 뒤 검증된 namespace 범위로 좁힌다. 불완전·후보 없음·복수 주제는 기존 범위를 유지한다.

`quality.collection.tasks`의 `sub_agent_id`, `depends_on`, 초기 구간 상한 `chunk_seconds`, 예약/실사용 호출량, 시작 offset·소요시간, 완료/빈 응답/미완료 구간으로 웹 결과 상세에서 수집을 추적한다. 근거의 `quality.sub_agent_id`와 연결된다. 응답 완료 구간은 표본 커버리지·계산 성공을 뜻하지 않는다. 저장된 진단이며 실시간 분산 추적은 아니다.

## 불필요한 조회 제거 — 2026-10-06

구 profile에서는 O01 장비 계산이 사용하지 않는 D06 Pod 이력을 조회 계획에서 제외한다. 새 binding profile은 매핑 설계의 기본 입력에 따라 D06을 포함한다. 다른 주제가 D06을 필요로 하면 조회한다. O06은 고정 DB snapshot에서 요청 범위·기간의 저장 사건이 명시적으로 0건일 때 D13 작업 로그만 생략하며, O10 등 다른 주제의 D13 조회는 유지한다. 사건 있음·snapshot 미확인에서는 생략하지 않는다. O06의 D08/D06 관측과 기존 자료 부족 판정은 유지한다.

생략 사유와 DB 근거를 주제 `quality.omitted_queries` 및 보고서 문장에 남긴다. 조회하지 않은 로그를 정상 빈 응답이나 실제 장애 0으로 해석하지 않는다. 기본 2개 클러스터·하루 장비 묶음의 초기 계획은 34→10회, 사건 0건 O06은 28→26회다. O08 단독과 11주제 전체는 줄지 않는다. 실제 전송량·실행시간 감소는 운영 측정 전이다. RCA·공통 수집·DB·실행 프로필은 바꾸지 않는다. 기간별 계획과 범위는 [12번 설계서](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md#불필요한-보고서-조회-제거--2026-10-06), 검증은 [Agent QA](../agents/QA.md)를 따른다.

## UI 개편 전 분석 조건 정리 — 2026-10-06

[보고서 선택 개편 기준](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md#보고서-선택-개편-전-확정-기준--2026-10-06)에 7개 종류의 주제·집계 기본값, 실제 계산 단위와 필수 자료, 기존 일정/결과 보존을 정리했다. 후속 변경에서 7개 종류 다중 선택·전체 종합을 한 보고서로 실행한다. 선택적 `topic_group_by`를 주제별로 적용하고 실제 표시 기준을 topic/metric quality에 남긴다. O10 조치·비교 기간 미지정 시 해당 주제 전용 조회를 생략하고 사유를 보존한다. 종합 실행은 수집량 감소를 뜻하지 않는다. O08 이외 일반 그룹 집계는 미완료이므로 cluster 요청을 클러스터별 결과로 오해하지 않는다.

D08이 연결 관측(`observed_pod_labels`)인 O02/O03/O04/O06에는 기존 `allocation_contract_missing` 사유를 명시한다. O02 연결 관측 수치와 다른 클러스터의 유효 수치는 보존하며, 조회 실패/빈 응답/독점 episode 부족과 구분한다. 보고서 문장·화면·내보내기 사유 설명을 동기화한다. 데이터 계약·산식·저장 결과·일정·RCA는 변경하지 않는다. 준비 상태는 실행에 고정된 evidence 기준이며 현재 배포 가용성 전체를 증명하지 않는다.

## 계산과 보고서

O01~O11은 공통 결정적 산식을 사용하고 고정 절대 기간·공개 RCA ID/hash·주제별 partial/blocked를 보존한다. HTML/CSV는 저장 수치에서 생성한다. 모델은 코드로 만든 사실·보고서 문장의 참조와 순서만 선택하며 수치·권고를 생성하거나 계산 품질을 승격하지 않는다.

주제 계산은 별도 스레드에서 요청 순서대로 하나씩 수행하여 CPU 계산 중에도 Worker heartbeat가 계속 동작하게 한다. 해당 주제에서 사용하는 할당·활동 입력만 정규화한다. 취소·lease 상실·deadline이면 다음 주제와 보고서 설명·저장으로 진행하지 않으며, 이미 실행 중인 계산은 끝날 때까지 회수한다. 수집·주제 계산·보고서 문장 구성의 시작/완료와 소요시간을 job/attempt별 로그로 남긴다. 원본 관측·프롬프트는 이 로그에 넣지 않으며 계산 산식·결과 스키마·RCA·JC 한도는 바꾸지 않는다.

`report.py`는 분석 범위와 결과·확인된 운영 현황·권고와 실행 조건·추가 확인·분석 한계의 다섯 섹션을 구성한다. 모델 미설정·확정 실패·무효 응답에도 결정적 기본 보고서를 남긴다. `quality.report.status=complete`는 보고서 구성 완료이며 topic/result_status와 다르다. `narrative_status`와 `quality.narrative_reason`은 모델 편집 상태다. 원격 종료 불명·취소·lease 상실은 기존 fail·슬롯 반환 계약을 따른다.

O08 criteria 1.2는 namespace 또는 cluster+namespace의 연결 GPU 고유 대수·연결 GPU-hours·평균 유효시간·시간 가중 활동률을 제공한다. Backend는 해당 요청에 report-namespace-v1을 선택하고 JC가 기준 버전을 고정한다. 연결 활동률은 namespace 실사용률·독점 할당량이 아니다. 공유/MIG·신원/활동 충돌 구간을 제외하며 null과 실제 0%를 구분한다. 유효시간은 전체 클러스터 커버리지나 정책 비교 적격성을 뜻하지 않는다. 과거 결과를 재계산하지 않는다.

## 클러스터 관측 요약 — 2026-10-02

O08 criteria 1.2는 요청 클러스터마다 관측 GPU·연결 확인 GPU·누적 연결 시간과 Pod 라벨 없음/신원 연결 미확인 대수를 저장한다. 물리 UUID와 시간 합집합으로 중복을 제거한다. 요청 Namespace 필터를 유지하며 조회 실패는 null, 확인된 연결 부재는 0으로 구분한다. 라벨 부재를 유휴로 확정하지 않는다. 실제 오류만 partial/blocked를 만들고 독점 할당 아님은 해석 제한으로 남긴다. 기존 Namespace 활동률 산식과 결과 스키마·RCA는 유지하며 과거 보고서는 바꾸지 않는다.

## 남은 범위와 실행

최초 병렬 관측은 구현했다. 판단 부족에 따른 추가 관측 라운드, 자유 생성형 Report Synthesis와 조언 검증은 [OP-05~07](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md)의 후속 목표다. 실제 Grafana 부하·일간/주간/월간 완료·관측 의미·모델 품질은 고정 fixture 검수와 별도다.

[공통 설치·환경·E2E](../agents/README.md) · [검증 기록](../agents/QA.md) · [현재 상세 흐름](../docs/architecture/report-agent-workflow/detailed-workflow.md) · [Archify](../docs/architecture/archify/gpu-ops-advisor.html#sequence-report-collection)

저장소 루트에서 실행한다.

```powershell
.venv/Scripts/python.exe -m ops_agent.main
```
