# 보고서 Agent 흐름

현재 구현은 [상세 흐름](detailed-workflow.md)과 [Archify 보고서 수집](../archify/gpu-ops-advisor.html#sequence-report-collection)을 따른다. 구현·남은 개발 목표의 기준은 [12번 설계서](../../specs/ops-agent/12_보고서_Agent_모듈_설계서.md)다.

| 구분 | 현재 상태 |
|---|---|
| 최초 수집 | query+CPC+기간 계획, 의존성, 예약 예산, 독립 Observation 병렬 실행, 취소 회수 구현 |
| 통계 | 고정 DB snapshot·공개 RCA 참조와 결정적 산식 사용 |
| 최종 보고서 | 코드의 기본 다섯 섹션과 검증된 문장 선택 구현 |
| 보완 관측·자유 생성형 조언 | OP-05~07 후속 목표. 실제 코드에 연결하지 않음 |
| 검증 | [Agent QA](../../../agents/QA.md)의 fixture/E2E 결과. 실제 Grafana 부하·모델 품질은 별도 |

이 폴더의 기존 2026-09-28 `report-agent-workflow` JSON/HTML 및 당시 영수증은 **당시 개발 제안**을 보존한다. 현재 실행도나 최신 검증 기록으로 사용하지 않는다. 같은 내용을 다시 설명하는 오래된 본문은 제거하고 현재 실행도와 설계서로 통합했다.
