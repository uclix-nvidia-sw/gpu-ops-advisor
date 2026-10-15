# Agent 검증 범위

이 문서는 현재 기능에 유효한 검증 근거와 남은 한계를 관리한다. 새 작업마다 실행 일지를 붙이지 않는다. 실행 흐름은 [RCA](../rcca-agent/README.md)·[Ops](../ops-agent/README.md), 재현 환경은 [공통 실행 안내](README.md)와 [CI](../.github/workflows/tests.yml)를 따른다. 아래 과거 검증은 이번 정리에서 다시 실행했다는 뜻이 아니다.

## 코드·fixture 검증

| 기능 | 보존한 검증 근거 | 한계 |
|---|---|---|
| RCA 사건 우선 보고·분석 원문 예산 | 2026-10-15, base `1322f16` 로컬 변경: 전체 Agent 1,571 통과·Windows 파일 정리 2 실패·47 skip. 오류 이벤트 KST·PCI 연결·조건부 지침 표시·기존 권고 적격성 유지와 검토 예약으로 인한 분석 원문 소실 회귀검사 포함. Ruff 검사 통과 | 실패는 기존 열린 파일 삭제와 디렉터리 flush 사례. 추가로 현재 소스의 Backend·JC·Incident, 임시 loopback PostgreSQL과 공식 MCP v1.4.2에서 양 Worker 발행·RCA 수치 수정 진단·검토 입력 상한 E2E 3개 통과(28.02초). Grafana·LLM은 fixture이며 나머지 E2E는 미실행. 실제 모델 재생·새 지식 발행·배포 후 품질은 미검증 |
| RCA 조건부 보완 조회·명시적 탐색 | 2026-10-14, PR #122: 비 E2E 1,201개 및 격리 PostgreSQL/Backend/JC/Incident/MCP fixture E2E 3개 통과 | Windows 파일 정리 모듈 제외. 실제 모델의 선택 품질과 운영 배포를 입증하지 않음 |
| RCA 공통 수정 불변 조건·전환 검토 | 2026-10-14, PR #124 (`31a0bcc`): 프롬프트 크기에 맞춘 수정 예산 fixture, 집중 검사 360개와 JSON 선택·부분 결과 공개 E2E 2개 통과 기록 | #123의 수정 예산 테스트 실패를 fixture에서 수정. 실제 모델 품질·운영 배포를 입증하지 않음 |
| 집계 보고서 GPU 신원 전환 | 2026-10-14, base `a317bf7`: 계산/전환 46개, 기존 UI 소비자 35개, 전체 Agent/fixture E2E 1,211개 통과 기록 | Python 3.11.16, 임시 loopback PostgreSQL·실제 Worker/NAT/공식 MCP·가짜 Grafana/LLM. 운영 동시 부하·주간 최대 크기는 미검증 |
| 기존 O계열 계산·수집 최소화 | 2026-10-12~13: 동일 합성 자료의 유지 지표·상태·참조 비교, 발행·삭제 fixture 검사 | 원천 실환경 지연·최대 메모리 개선의 증거가 아님 |
| Ops 주제별 AI 해석 | 2026-10-14, PR #126 / main `2171929` 통합: 전체 Agent·격리 프로세스 E2E 1,575개 통과(128.55초, 건너뜀 없음), 설명 검증 40개 포함. 값·시간·참조 검증, 설명 실패 시 계산 유지, CSV 동일성과 HTML 발행 검사 | Python 3.11.16, 임시 PostgreSQL·실제 Worker/NAT/MCP·fixture Grafana/LLM. 실제 운영 모델 재생은 아래 별도 근거이며, 배포·대용량 부하는 미검증 |
| RCA 평가 분리·GUI 디버깅·F0 | 2026-10-15, base `31946b8`의 로컬 변경: Python 3.12.14 전체 비 E2E 1,564 통과·기존 Windows 파일 정리 3 실패, 집중 평가·분석·수정 77 통과. 새 임시 PostgreSQL·실제 양 Worker/NAT/MCP·fixture Grafana/LLM 프로세스 E2E 3 통과: 기존 공개 경로, 수치 수정 진단, 입력 크기 초과 후 종료·null 판정·사전 검사 저장 확인. 입력/토큰/동시 초과·경계·수정 요청·모델 usage 누락도 검사. 기존 평가 분리 시점의 추가 E2E 근거는 Git 이력에 보존 | 커밋·CI·배포 전 로컬 검증. 기존 파일 정리 3건은 열린 파일 삭제·디렉터리 재생성·flush의 Windows 동작으로 실패하며 이번 변경에서 수정하지 않음. 이번 E2E는 해당 3개만 재실행. 새 rubric의 실제 모델 의미 정확도(T79)·운영 환경 GUI는 미검증 |
| 공통 Worker 수명주기 | CI가 양 Worker의 claim·lease·heartbeat·저장·공개·취소·원격 종료 불명 경로 검사 | fixture E2E는 실제 Grafana/LLM의 가용성·성능 검증이 아님 |

검사 위치: [평가 분리·척도 계약](tests/test_rca_evaluation.py), [GUI 평가 표시](../frontend/src/components/RcaEvaluation.test.tsx), [조건부 조회](tests/test_rca_rule_selection.py), [JSON 선택](tests/test_rca_batch_selection.py), [수정 예산](tests/test_rca_repairs.py), [모델 입력](tests/test_synthesis_context.py), [전환 검토](tests/test_runbook_transition.py), [프로세스 E2E](tests/test_e2e.py), [Ops 해석](tests/test_report_interpretation.py), [파일 정리](tests/test_report_cleanup.py), [파일 정리 DB E2E](tests/test_report_cleanup_e2e.py).

[PR #123 CI 실패 근거](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/actions/runs/38510572299): `test_repair_gate_records_specific_conditions`의 adaptive/deadline 두 경우와 `test_repair_gate_matches_real_transport_output_cap`. [PR #124](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/pull/124)에서 고정 예산 fixture를 현재 프롬프트 크기에 맞췄다. 최신 revision의 전체 결과는 해당 commit의 CI에서 확인한다.

## 실환경 관측·재생 검증

| 대상 | 확인한 사실 | 확인하지 못한 범위 |
|---|---|---|
| 10/15 배포 후 RCA 검수 | 13:18 KST dgx01 XID79 (`c7d388a8-9e0d-45c2-8922-04d0a05eba99`)·SXID11001 (`da5f3b74-564d-448c-99f5-3e438d51b411`): 저장 근거 UI에서 양쪽 D09만 실행, 분석 작성 전송 0회·`llm_context_budget_exhausted`·입력 근거 참조 없음 확인. XID 재검토 출력 잘림, SXID 재검토 예산 부족. SXID의 저장 오류 이벤트 1개도 분석 입력에서 제외됨 | 운영 원본 읽기 검수. 이 관측은 로컬 수정 이후의 개선 검증이 아니며 직접 Grafana MCP 호출·복구 수행·현재 장애를 입증하지 않음 |
| RCA 오류 주입 | 2026-10-14 11:57:34 KST dgx02 주입, 12:00:48경 작업. 당시 배포 코드와 XID79 revision 6·SXID11001 revision 5에서 규칙 선택 LLM 0회, XID D09/D44/D02·SXID D09/D02 성공, partial 결과와 complete 보고서 공개 | 실제 고장 원인·현재 장비 상태. 이후 코드가 배포됐다는 증거가 아님 |
| 집계 신원 전환 | 2026-10-14 read-only 조사: 10월 13일 CPC-1 09–10/12–13시, CPC-2 13–14시의 11 GPU·13 GPU-hour 전환에서 이전/새 라벨 구간이 겹치지 않고 15초 간격임을 확인. 해당 경계를 코드에 재생해 8+3+2개 전환 검증 | 새 이미지의 운영 발행·LLM 지연·고빈도 전환·주간/최대 크기/동시 부하 |
| Ops 실제 설명 재생 | 2026-10-14, PR #126: 분석일 10월 12·13일의 저장 보고서 3건으로 운영 모델 설명만 생성. 17.38초·18.48초는 첫 응답, 51.49초는 형식 보완 1회 후 채택. 시간대별 0→96.98%, 0→60.14% 참조와 설명 외 필드·CSV 동일성 확인 | 운영 DB·보고서 불변. 전체 생성 시간이나 일반적 성공률의 증거가 아님. 신규 배포 Worker 발행·동시/주간 부하·자연어 의미 정확성은 미검증 |
| 집계 데이터량 | CPC-1 1일 표본에서 103,716→1,968 samples, 1,698,241→167,175 bytes | 쿼리 시간·DB 디스크·프로세스 최대 RSS 개선을 뜻하지 않음. 산식과 조건은 집계 명세 참조 |

주입 때 발행된 내용 hash:

- XID79: `13a44c8cc52087158f47e9b1ee69cc5df2bcd6af3d1a08e8c3f70ebd43561fcc`.
- SXID11001: `ee1475be64daec318d40c435ee69a5c176b3019f21a177e47adfdde40dacaf0d`.

관련 원천 근거: [binding 표본](../docs/evidence/d-binding-cpc-20261006.md), [발견/UID](../docs/evidence/d-binding-discovery-20261007.md), [D 확장](../docs/evidence/d-observation-expansion-20261007.md), [D07/D13](../docs/evidence/d07-d13-source-review-20261007.md), [Fleet 상태·이벤트](../docs/evidence/fleet-state-event-review-20261008.md), [지침 의미](../docs/evidence/rca-runbook-guidance-20261013.md), [집계 산식·측정](../docs/specs/ops-agent/aggregate-report-v1.md).

## 남은 검증

- 평가 척도: [rubric 1](../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md#분석-품질-평가-척도--rubric-1)의 적절한/과장된 분석 쌍을 실제 모델에 재생하여 항목별 누락·오검출·비용을 사람이 원본과 대조해야 함. 고정 응답의 분기 통과는 의미 정확도 검증이 아님.
- RCA: 실제 사건의 대상·발생 시각·현재 상태·원인 근거, 모델 응답의 의미 품질, 오류별 보완 D 선택과 지침의 적합성.
- Runbook: [265개 전환 검토](../rcca-agent/runbooks/transition-review-20261014.json)의 196개 계약 통과는 의미 승인이나 발행이 아니다. 69개 보류와 기존 구조화 내용의 병합 검토, 최신 운영 revision/hash·profile 대조가 필요하다.
- Ops: 운영 주간·최대 크기·동시 실행에서 지연과 RSS, 신원 변동과 원본 보존 부족, 예산 소진 시 부분 결과 확인.
- 운영: 최신 이미지 배포, 기존 일정·과거 결과 호환, PVC 파일 정리·복구. 별도 운영 승인과 환경 확인이 필요하다.

이전 실행의 상세 조건은 [정리 전 검증 이력](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/blob/f7bed6c594dc44a4b1d053bc8b60e2761c0b7f0c/agents/QA.md)에서 확인한다. 과거 통과 수를 새 revision의 결과로 재사용하지 않는다.
