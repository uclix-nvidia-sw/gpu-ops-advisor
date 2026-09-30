# ops-agent

`12_보고서_Agent_모듈_설계서.md`에 따른 운영 보고서 Worker입니다. JC kind는 `report`입니다.

`src/ops_agent/workflow.py`의 O01~O11 수집 계획을 순차 실행합니다. 집계는 공통 결정적 산식을 쓰고, LLM은 검증된 사실 선택만 수행합니다. 고정된 절대 기간·DB snapshot·공개 RCA 참조·주제별 partial/blocked 상태를 보존합니다. HTML/CSV는 저장한 수치 레지스트리에서 생성합니다.

후속 개발의 기준은 [12번 보고서 설계서](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md)의 OP-01~07·개발 순서입니다. 2026-09-30에 Orchestrator → query별 병렬 Observation Sub-agent → 통계·제한적 보완 조회 → 도구 없는 단일 Synthesis → 검증·공개 구조를 개발 목표로 반영했습니다. 같은 Worker/job/lease와 전체 예산을 사용하며 현재 구현된 기능은 아닙니다. [상세 Mermaid 흐름도](../docs/architecture/report-agent-workflow/detailed-workflow.md)는 이 기준을 설명하고, [05 T60~T65](../docs/specs/05_테스트_검수_기준서.md)는 추가 검수 기대값입니다. 제품 구현은 대기 중입니다.

## Namespace 관측 보고서 초안 — 2026-09-30

`versions.criteria=1.2`인 보고서의 O08에 한해 `group_by=["namespace"]` 또는 `["cluster","namespace"]`를 적용한다. D01/D02/D06/D08을 순차 조회하고, 연결 관측 시간·활동률 계산에 사용한 시간·연결 GPU의 시간 가중 평균 활동률을 기존 `topics[].metrics`에 저장한다. D12 프로젝트 연결은 이 초안의 계산 입력이 아니다.

연결 GPU 활동률은 namespace 실사용률이나 독점 할당량이 아니다. 공유/MIG·신원 충돌·활동값 충돌 구간은 제외하고, 다른 시각의 충돌 없는 구간은 보존한다. 값 없음은 null·사유이며 실제 활동률 0%와 구분한다. 다른 모델 또는 복수 GPU의 모델 미확인은 평균을 보류한다. 유효시간은 관측된 연결 범위 안의 분모이며 전체 클러스터 커버리지·정책 비교 적격성을 뜻하지 않는다. 권고·회수량·저활동 후보는 추가하지 않는다.

새 경로는 `namespace_usage.py`에서 namespace·Pod UID·시각 라벨을 보존하며 공통 `allocations`/`intervals`/`allocation_hours`를 재사용한다. 라벨을 제거하는 기존 `gpu_intervals()`를 사용하거나 변경하지 않는다. O01~O07/O09~O11 및 기존 criteria의 O08은 기존 동작을 유지한다. 전체 OP-01 구현 완료가 아니며 나머지 O08 지원 축은 `group_by_not_implemented`, 명세상 미지원 축은 `unsupported_group_by`로 blocked다.

후속 실행·표시 개선에서는 Backend가 O08 + namespace(또는 cluster+namespace) 요청에 report-namespace-v1을 선택하고 JC가 criteria 1.2를 고정한다. 기본 전역 criteria와 RCA 기준은 유지한다. 새 요청은 화면의 `Namespace GPU 현황` 프리셋으로 만들 수 있다. 새 프로필이 없는 JC와의 혼합 배포는 접수 실패할 수 있으므로 Worker·JC를 먼저 갱신해야 한다. 사용자 정의 JC 전체 설정에도 프로필을 추가한다. 실제 관측 의미 검수·운영 배포는 별도다.

Namespace 요약을 먼저 표시하며 한글 지표/사유와 유효 관측시간을 함께 읽는다. 구 결과에는 새 수치를 소급하지 않는다. 수집 호출수·한도와 AI 설명 실패 코드는 result.quality에 기록한다. 설명용 fact 선택에서 반복 UUID는 입력에서만 생략하고 공개 참조는 유지한다. 상세 범위·검수 계획은 [12 §0.3](../docs/specs/ops-agent/12_보고서_Agent_모듈_설계서.md#03-namespace-보고서-실행표시-개선--2026-09-30)을 따른다.

로컬 검증: `.venv/bin/python -m pytest -c agents/pytest.ini agents/tests/test_namespace_usage.py agents/tests/test_report_observation.py -q`. [Agent QA](../agents/QA.md)의 실행 환경과 결과를 따르며, 고정 자료와 실제 Grafana 검증을 구분한다.

설치·환경 설정·Docker·최소 테스트/E2E: [공통 실행 안내](../agents/README.md), [검증 기록](../agents/QA.md).

```powershell
.venv/Scripts/python.exe -m ops_agent.main
```

저장소 루트에서 실행합니다. 일정 계산, RCA 생성, 별도 접수 API는 제공하지 않습니다.
