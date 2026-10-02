# ops-agent

운영 보고서 Worker이며 JC kind는 `report`다. 하나의 job/attempt/lease 안에서 **입력·DB snapshot 고정 → 수집 계획 → 병렬 Observation → 결정적 계산 → 보고서 문장 선택 → 저장·JC 공개**를 수행한다. 일정 계산은 Backend가 담당한다.

## 계획과 병렬 수집

`collection.py`는 중복 query를 합치고 query+CPC+기간별 독립 Observation task를 만든다. 비교 기간은 별도 task다. 실제 조회 전 전체 초기 호출량·설정·범위를 검사한다. 각 task의 query/discovery 예산을 예약하고 의존성이 해결된 task를 한 배치로 실행한다. 배치 종료 후 미사용 예산을 다음 task에 배분한다. 실패는 해당 근거에 남기고 독립 결과를 보존하며, 취소 시 모든 task를 회수한다. RCA와 공통 bounded runner를 사용한다.

`report.limits` 예시는 `max_queries=2048`, `chunk_seconds=86400`, `max_rows=50000`, `max_concurrency=3`이다. 네 키만 양수 정수로 받으며 미지정 키는 기존 공통 limits를 사용한다. 동시성 1은 순차 실행이다. 원본 표본·응답 크기·전체 deadline·최대 기간은 보존한다. 세부 예산·시간 배분은 [설계서](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md#기간-수집예산-분리--2026-10-01)를 따른다.

동일 CPC·기간·metric task에는 순서를 두어 완전한 동일 Prometheus 응답을 재사용한다. 도구·데이터소스·범위·표현식·시각·구간이 모두 일치해야 하며 query/evidence ID와 `quality.reused_from_evidence`를 보존한다. 실패·부분·대용량 폐기 응답과 Loki는 재사용하지 않는다. 완료된 캐시만 복사하고 실행 중 상태는 공유하지 않는다. O08 단독 namespace의 D06은 D01/D08 완료 뒤 검증된 namespace 범위로 좁힌다. 불완전·후보 없음·복수 주제는 기존 범위를 유지한다.

`quality.collection.tasks`의 `sub_agent_id`, `depends_on`, 예약/실사용 호출량, 시작 offset·소요시간, 완료/빈 응답/미완료 구간으로 웹 결과 상세에서 수집을 추적한다. 근거의 `quality.sub_agent_id`와 연결된다. 응답 완료 구간은 표본 커버리지·계산 성공을 뜻하지 않는다. 저장된 진단이며 실시간 분산 추적은 아니다.

## 계산과 보고서

O01~O11은 공통 결정적 산식을 사용하고 고정 절대 기간·공개 RCA ID/hash·주제별 partial/blocked를 보존한다. HTML/CSV는 저장 수치에서 생성한다. 모델은 코드로 만든 사실·보고서 문장의 참조와 순서만 선택하며 수치·권고를 생성하거나 계산 품질을 승격하지 않는다.

`report.py`는 분석 범위와 결과·확인된 운영 현황·권고와 실행 조건·추가 확인·분석 한계의 다섯 섹션을 구성한다. 모델 미설정·확정 실패·무효 응답에도 결정적 기본 보고서를 남긴다. `quality.report.status=complete`는 보고서 구성 완료이며 topic/result_status와 다르다. `narrative_status`와 `quality.narrative_reason`은 모델 편집 상태다. 원격 종료 불명·취소·lease 상실은 기존 fail/격리 계약을 따른다.

O08 criteria 1.2는 namespace 또는 cluster+namespace의 연결 GPU 고유 대수·연결 GPU-hours·평균 유효시간·시간 가중 활동률을 제공한다. Backend는 해당 요청에 report-namespace-v1을 선택하고 JC가 기준 버전을 고정한다. 연결 활동률은 namespace 실사용률·독점 할당량이 아니다. 공유/MIG·신원/활동 충돌 구간을 제외하며 null과 실제 0%를 구분한다. 유효시간은 전체 클러스터 커버리지나 정책 비교 적격성을 뜻하지 않는다. 과거 결과를 재계산하지 않는다.

## 남은 범위와 실행

최초 병렬 관측은 구현했다. 판단 부족에 따른 추가 관측 라운드, 자유 생성형 Report Synthesis와 조언 검증은 [OP-05~07](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md)의 후속 목표다. 실제 Grafana 부하·일간/주간/월간 완료·관측 의미·모델 품질은 고정 fixture 검수와 별도다.

[공통 설치·환경·E2E](../agents/README.md) · [검증 기록](../agents/QA.md) · [현재 상세 흐름](../docs/architecture/report-agent-workflow/detailed-workflow.md) · [Archify](../docs/architecture/archify/gpu-ops-advisor.html#sequence-report-collection)

저장소 루트에서 실행한다.

```powershell
.venv/Scripts/python.exe -m ops_agent.main
```
