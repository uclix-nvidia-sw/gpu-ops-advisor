# Ops Report Agent

JC에서 보고서 작업을 인수하고 관측·사건을 집계해 결과와 HTML/CSV를 저장한다. 신규 집계 보고서와 기존 O계열 보고서는 서로 다른 입력 계약이며 [workflow.py](src/ops_agent/workflow.py)가 분기한다. 기존 일정·결과를 자동 변환하지 않는다.

## 신규 기본 보고서

`report-aggregate-v1`은 `namespace_usage`·`incident_summary`의 일일/주간 보고서와 직전 동일 기간 비교다. [집계 보고서 계약](../docs/specs/ops-agent/aggregate-report-v1.md)이 쿼리·산식·제한·검수 기준의 담당 문서다.

- [report_queries.py](src/ops_agent/report_queries.py)의 Ops 전용 PromQL을 사용한다. 공통 D registry를 읽지 않는다. 클러스터·기간별 활동, Pod 신원, GPU 신원 3개 range 조회를 1시간 간격으로 수행한다.
- [namespace_usage.py](src/ops_agent/namespace_usage.py)는 유효 활동 합계/유효 표본 수로 평균을 계산한다. 관측 연결은 전용 할당의 증거가 아니다.
- [identity_transitions.py](src/ops_agent/identity_transitions.py)는 시간대 내 신원 변경이 모호한 GPU·시간대만 추가 조회한다. 검증 요약을 보존하고 이 추가 조회의 원본 표본 배열은 저장하지 않는다.
- [report_store.py](src/ops_agent/report_store.py)는 같은 DB snapshot에서 사건과 공개 RCA ID/hash를 읽는다. 새 RCA를 실행하지 않는다.
- [report_contract.py](src/ops_agent/report_contract.py)의 클러스터·Namespace·GPU·표본·바이트·호출·시간 한도를 따른다. 응답을 받은 뒤의 크기 검사만으로 프로세스 최대 메모리를 보장하지 않는다.
- 근거에는 시간 집계와 검증 요약을 저장한다. 수집 누락·연결 모호성·잘림은 품질과 보고서에 남긴다. 과거 큰 snapshot을 변환하는 migration은 없다.

### 주제별 AI 운영 해석 / Topic-level AI interpretation

신규 집계 보고서는 계산 후 Ops 전용 `report_interpretation.py`에서 두 주제별로 **눈에 띄는 변화 → 의미와 한계 → 확인할 점**을 작성합니다. 기존의 전체 최대 3개 계산 문장 선택을 주제별 1~3개 근거 선택과 짧은 한국어 해석으로 바꿉니다. 수치·대상은 선택한 근거의 참조를 코드가 치환하며, 계산·PromQL·품질 판정·CSV는 그대로입니다. 정책·전용 할당·효율·회수·장애 원인·복구를 판단하지 않습니다.

시간대 설명에는 이미 저장된 시간당 metric만 사용합니다. 같은 Namespace·모델·GPU 구성의 끊기지 않은 인접 시간대 중 변화 폭이 큰 쌍을 편집 우선순위로 선택합니다. 새 수치나 이상 판정을 계산하지 않으며, 자료 부족·GPU 구성 변경·관측 공백이 있는 쌍은 사용하지 않습니다. 모델은 대상·전후 시간·전후 수치와 해당 시간대에 대조할 작업 기록을 함께 적어야 합니다. 이는 보고 기간 안의 변화이지 전날 같은 시간대와의 비교가 아닙니다. 이전 기간 비교가 불가능한 행의 이전 값·차이는 모델 입력에서도 제외합니다. 근거 ID(`fact_id`)와 수치 ID(`metric_id`)를 구분하고 날짜·값·대상은 저장된 참조만 치환합니다.

성공은 `quality.report.method=llm_interpreted`와 두 주제의 narrative로 저장합니다. 참조·형식 검증에 실패하면 최대 한 번 재요청하고, 그래도 실패하거나 모델이 없으면 기존 계산 요약으로 돌아갑니다. 입력은 주제별 최대 30개 finding, 전체 32KB로 제한하고 초과 시 요약만 제공합니다. 기존 공통 LLM deadline·토큰 예산·취소·원격 상태 계약은 유지합니다. 검증은 수치 참조와 형식을 보호하며 자연어 의미의 정확성을 완전히 증명하지는 않습니다.

웹은 주제별 녹색 **AI 운영 해석** 영역과 접을 수 있는 근거를 표시하고, HTML 내보내기도 같은 저장 문장을 사용합니다. 과거 `llm_prioritized` 보고서는 **AI가 고른 주요 변화**, 실패 시 **계산 결과 요약**으로 구분합니다. 기존 결과·RCA·공통 runtime·DB·Helm 설정은 바꾸지 않습니다. [검증 범위](../agents/QA.md)를 참고하세요.

## 기존 O계열 보고서

이전 요청 방식과 기존 일정은 [O계열 명세](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md)를 사용한다. `criteria 1.3`의 기본 주제는 O08/O01/O05/O11이며 현재 신규 화면의 기본 집계 계약과 구분한다.

- 공통 D binding과 query+CPC+기간 계획으로 조회한다. [collection.py](src/ops_agent/collection.py)가 의존성·예약 예산·병렬 수집·취소 회수를 처리한다. 실행별 관측 캐시는 같은 조회·기간의 근거를 재사용한다.
- O01 장비/Node 관측, O08 사용 패턴, O05 DB 사건·공개 RCA·조치 기록, O11 자료 신뢰도에 [operator_insights.py](src/ops_agent/operator_insights.py)의 확인 항목을 연결한다. 누적 상태와 현재 장애, 알람 해제와 복구 완료를 구분한다.
- 통합 binding과 criteria 1.3에서 O01은 불필요한 D06을, O05는 D10/D22를 조회하지 않는다. 계산에 쓰지 않는 보고서 D09/D13도 생략하며 `quality.omitted_queries`에 이유를 남긴다. 다른 계약의 조회를 임의로 줄이지 않는다.
- D06 범위 축소는 완전한 D02 신원·기간과 허용된 주제 조합에서만 적용한다. 신원 누락·공백·빈 후보·필터 한도 초과 시 넓은 기존 범위로 복귀한다. 최종 UID·Node·시간 연결 검사는 유지한다.
- O01 추가 관측은 대상별 고유 지표 ID를 사용한다. criteria 1.3은 D20 원본 구간을 결과 본문에 중복 저장하지 않고 계산 결과와 evidence refs를 유지한다. 구 결과 형식은 조회 호환용으로 유지한다.
- [report.py](src/ops_agent/report.py)는 코드가 만든 문장을 문장 ID 선택 LLM으로 편집한다. 새 수치·원인·조치를 생성하지 않으며 모델을 사용할 수 없으면 기본 보고서를 남긴다.

## 보고서 삭제와 파일 정리

사용자가 종료한 보고서를 삭제하면 JC가 DB 결과·근거를 삭제하고 `report_deletions`를 기록한다. [cleanup.py](src/ops_agent/cleanup.py)는 Worker 시작 시와 이후 30초마다 대상 1건을 처리한다. DB 행 잠금·`SKIP LOCKED`로 여러 Pod가 같은 대상을 동시에 맡지 않는다.

정규 UUID의 `ARTIFACT_DIR/<job_id>`만 처리하고 심볼릭 링크를 따라가지 않는다. 파일 삭제 후 0바이트 일반 파일로 표시해 늦게 끝난 저장 작업이 디렉터리를 다시 만들지 못하게 한다. `pending`/`failed`는 미완료, `complete`는 삭제 표시까지 생성한 상태다. 실패 시 재시도하며 DB에서 삭제한 본문이 복구되지는 않는다. migration 008 미적용 중에는 경고를 남기고 분석 루프를 유지한다. RCA에는 이 정리 루프가 없다.

## 실행·검증

[공통 실행 안내](../agents/README.md) · [Agent QA](../agents/QA.md) · [삭제 회귀](../agents/tests/test_report_cleanup.py) · [격리 DB 삭제 검증](../agents/tests/test_report_cleanup_e2e.py).

실환경 지연·최대 메모리·운영 PVC의 삭제·복구와 원인/업무 영향 해석은 각 검증 근거의 범위를 따른다. 저장소 원본이나 fixture 테스트만으로 운영 배포와 성능 개선을 확정하지 않는다.
