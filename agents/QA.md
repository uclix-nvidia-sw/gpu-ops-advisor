# Agent 검증 범위

이 문서는 현재 기능에 유효한 검증 근거와 남은 한계를 관리한다. 새 작업마다 실행 일지를 붙이지 않는다. 실행 흐름은 [RCA](../rcca-agent/README.md)·[Ops](../ops-agent/README.md), 재현 환경은 [공통 실행 안내](README.md)와 [CI](../.github/workflows/tests.yml)를 따른다. 아래 과거 검증은 이번 정리에서 다시 실행했다는 뜻이 아니다.

## 코드·fixture 검증

| 기능 | 보존한 검증 근거 | 한계 |
|---|---|---|
| RCA 사건 우선 보고·자동 보완 수집 | 2026-10-15, main `dce3aea` 기반 후속 변경: Python 3.12.14 전체 Agent/프로세스 E2E 1,626 통과·Windows 파일 정리 2 실패·skip 없음(261.57초). 예산 소진·검토 수락 후 명시적 규칙 조회, PCI 신원 조인, 수집 상태별 보고, 변경된 보고 섹션 E2E 검사. Ruff 통과 | 임시 loopback PostgreSQL·현재 소스 Backend/JC/Incident·공식 MCP v1.4.2·fixture Grafana/LLM. 두 실패는 기존 열린 파일 삭제·디렉터리 flush의 Windows 제약이며 해당 Linux CI는 이전 revision에서 통과. 실제 자동 조인·모델 품질·지식 발행·배포 후 개선은 미검증 |
| RCA 조건부 보완 조회·명시적 탐색 | 2026-10-14, PR #122: 비 E2E 1,201개 및 격리 PostgreSQL/Backend/JC/Incident/MCP fixture E2E 3개 통과 | Windows 파일 정리 모듈 제외. 실제 모델의 선택 품질과 운영 배포를 입증하지 않음 |
| RCA 공통 수정 불변 조건·전환 검토 | 2026-10-14, PR #124 (`31a0bcc`): 프롬프트 크기에 맞춘 수정 예산 fixture, 집중 검사 360개와 JSON 선택·부분 결과 공개 E2E 2개 통과 기록 | #123의 수정 예산 테스트 실패를 fixture에서 수정. 실제 모델 품질·운영 배포를 입증하지 않음 |
| 집계 보고서 GPU 신원 전환 | 2026-10-14, base `a317bf7`: 계산/전환 46개, 기존 UI 소비자 35개, 전체 Agent/fixture E2E 1,211개 통과 기록 | Python 3.11.16, 임시 loopback PostgreSQL·실제 Worker/NAT/공식 MCP·가짜 Grafana/LLM. 운영 동시 부하·주간 최대 크기는 미검증 |
| 기존 O계열 계산·수집 최소화 | 2026-10-12~13: 동일 합성 자료의 유지 지표·상태·참조 비교, 발행·삭제 fixture 검사 | 원천 실환경 지연·최대 메모리 개선의 증거가 아님 |
| Ops 주제별 AI 해석 | 2026-10-14, PR #126 / main `2171929` 통합: 전체 Agent·격리 프로세스 E2E 1,575개 통과(128.55초, 건너뜀 없음), 설명 검증 40개 포함. 값·시간·참조 검증, 설명 실패 시 계산 유지, CSV 동일성과 HTML 발행 검사 | Python 3.11.16, 임시 PostgreSQL·실제 Worker/NAT/MCP·fixture Grafana/LLM. 실제 운영 모델 재생은 아래 별도 근거이며, 배포·대용량 부하는 미검증 |
| RCA 평가 분리·GUI 디버깅·F0 | 2026-10-15, base `31946b8`의 로컬 변경: Python 3.12.14 전체 비 E2E 1,564 통과·기존 Windows 파일 정리 3 실패, 집중 평가·분석·수정 77 통과. 새 임시 PostgreSQL·실제 양 Worker/NAT/MCP·fixture Grafana/LLM 프로세스 E2E 3 통과: 기존 공개 경로, 수치 수정 진단, 입력 크기 초과 후 종료·null 판정·사전 검사 저장 확인. 입력/토큰/동시 초과·경계·수정 요청·모델 usage 누락도 검사. 기존 평가 분리 시점의 추가 E2E 근거는 Git 이력에 보존 | 커밋·CI·배포 전 로컬 검증. 기존 파일 정리 3건은 열린 파일 삭제·디렉터리 재생성·flush의 Windows 동작으로 실패하며 이번 변경에서 수정하지 않음. 이번 E2E는 해당 3개만 재실행. 새 rubric의 실제 모델 의미 정확도(T79)·운영 환경 GUI는 미검증 |
| 공통 Worker 수명주기 | CI가 양 Worker의 claim·lease·heartbeat·저장·공개·취소·원격 종료 불명 경로 검사 | fixture E2E는 실제 Grafana/LLM의 가용성·성능 검증이 아님 |
| RCA 예약 하한·선택 지침 원문 연결 | 2026-10-15, main `3e6c946` 통합 변경: Python 3.12.14 전체 1,592 통과·기존 Windows 파일 정리 3 실패·47 건너뜀. 별도 새 PostgreSQL·Worker/NAT/MCP·fixture Grafana/LLM 공개 E2E 3 통과. PR #131 head `50dac95` 복사본에 예약 변경과 Runbook 시점 패치를 결합한 RCA 검사 113 통과. 실제 공통 LLM 차감 코드로 고정 예약/기존 조정/검토 하한 조정을 비교하고 사용량 보고·미보고, 초안 크기·예산 경계·출력 잘림 검사. 초기/추가 지침의 단일 원문·같은 ID 사용 및 fast path·XID/SXID 확장 확인 | 외부 모델 호출 없이 고정 응답으로 검사. 실제 모델의 응답 크기·검토 실패율·의미 품질과 운영 배포는 미검증. 최신 main의 사건 보고·명시적 규칙 조회를 보존하여 통합. Windows 실패 3건은 이번 변경에서 수정하지 않음 |

검사 위치: [평가 분리·척도 계약](tests/test_rca_evaluation.py), [GUI 평가 표시](../frontend/src/components/RcaEvaluation.test.tsx), [조건부 조회](tests/test_rca_rule_selection.py), [JSON 선택](tests/test_rca_batch_selection.py), [수정 예산](tests/test_rca_repairs.py), [모델 입력](tests/test_synthesis_context.py), [전환 검토](tests/test_runbook_transition.py), [프로세스 E2E](tests/test_e2e.py), [Ops 해석](tests/test_report_interpretation.py), [파일 정리](tests/test_report_cleanup.py), [파일 정리 DB E2E](tests/test_report_cleanup_e2e.py).

[PR #123 CI 실패 근거](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/actions/runs/38510572299): `test_repair_gate_records_specific_conditions`의 adaptive/deadline 두 경우와 `test_repair_gate_matches_real_transport_output_cap`. [PR #124](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/pull/124)에서 고정 예산 fixture를 현재 프롬프트 크기에 맞췄다. 최신 revision의 전체 결과는 해당 commit의 CI에서 확인한다.

## 실환경 관측·재생 검증

| 대상 | 확인한 사실 | 확인하지 못한 범위 |
|---|---|---|
| RCA 후속 조회 원천 | 2026-10-15 13:13–13:23 KST Grafana UI 읽기 조회: 사건 GPU의 PCI·UUID·A100 모델·Namespace/Pod 라벨, 같은 Pod의 UID·노드 이력 조회됨. 같은 서버 Loki에서 FM/source port/topology 관련 검색은 빈 결과 | MCP 직접 접속 검증이 아니며 사건 순간의 자동 조인·작업 실패·FM 원천의 전체 부재를 입증하지 않음. 저장소 기본 D13은 node 범위를 지원하지 않아 별도 binding이 필요함 |
| 10/15 배포 후 RCA 검수 | 13:18 KST dgx01 XID79 (`c7d388a8-9e0d-45c2-8922-04d0a05eba99`)·SXID11001 (`da5f3b74-564d-448c-99f5-3e438d51b411`): 저장 근거 UI에서 양쪽 D09만 실행, 분석 작성 전송 0회·`llm_context_budget_exhausted`·입력 근거 참조 없음 확인. XID 재검토 출력 잘림, SXID 재검토 예산 부족. SXID의 저장 오류 이벤트 1개도 분석 입력에서 제외됨 | 운영 원본 읽기 검수. 이 관측은 로컬 수정 이후의 개선 검증이 아니며 직접 Grafana MCP 호출·복구 수행·현재 장애를 입증하지 않음 |
| RCA 오류 주입 | 2026-10-14 11:57:34 KST dgx02 주입, 12:00:48경 작업. 당시 배포 코드와 XID79 revision 6·SXID11001 revision 5에서 규칙 선택 LLM 0회, XID D09/D44/D02·SXID D09/D02 성공, partial 결과와 complete 보고서 공개 | 실제 고장 원인·현재 장비 상태. 이후 코드가 배포됐다는 증거가 아님 |
| 집계 신원 전환 | 2026-10-14 read-only 조사: 10월 13일 CPC-1 09–10/12–13시, CPC-2 13–14시의 11 GPU·13 GPU-hour 전환에서 이전/새 라벨 구간이 겹치지 않고 15초 간격임을 확인. 해당 경계를 코드에 재생해 8+3+2개 전환 검증 | 새 이미지의 운영 발행·LLM 지연·고빈도 전환·주간/최대 크기/동시 부하 |
| Ops 실제 설명 재생 | 2026-10-14, PR #126: 분석일 10월 12·13일의 저장 보고서 3건으로 운영 모델 설명만 생성. 17.38초·18.48초는 첫 응답, 51.49초는 형식 보완 1회 후 채택. 시간대별 0→96.98%, 0→60.14% 참조와 설명 외 필드·CSV 동일성 확인 | 운영 DB·보고서 불변. 전체 생성 시간이나 일반적 성공률의 증거가 아님. 신규 배포 Worker 발행·동시/주간 부하·자연어 의미 정확성은 미검증 |
| Ops GPU 메모리 보강 | 2026-10-15, main `bb292af` 통합 `feat/report-gpu-memory`: Python 3.11.16 전체 Agent·프로세스 E2E 1,693개 통과(141.94초, 건너뜀 없음), Ruff 검사·형식 통과. 격리 PostgreSQL·JC·Worker·공식 MCP와 fixture Grafana/LLM으로 메모리 evidence 저장·GiB 결과/CSV·공개 결과와 활동 계산 보존 확인. 자동/수동 profile 및 일정 Go 검사 통과 | fixture E2E는 운영 자동 발행 증거가 아님. RCA·공통 runtime·DB schema·Helm 변경 없음 |
| Ops GPU 메모리 실자료 재생 | 2026-10-15 수동 발행 보고서의 10/14 CPC-1·CPC-2 자료를 읽기 전용 재생. 기존 활동/비교 rows·기존 metrics·사건 topic 동일. 메모리 쿼리 2회 총 0.509초, 직렬화 응답 234,497 bytes. 운영 모델 최종 설명 재생 45.66초, 보완 1회 후 채택. 수치·시간은 코드, 의미·확인 제안은 LLM으로 구분 | 초기 실험 응답의 시간 혼동·근거 없는 메모리 증감/충분 판단을 발견해 검증 보강. 최종 1건 통과가 일반적 성공률·자연어 정확성을 보장하지 않음. 추가 조회 소요이며 전체 생성시간/DB 크기 측정 아님. 운영 DB 불변; 배포 후 자동/수동 신규 발행·주간/최대 규모/동시 부하 미검증 |
| Ops 작업 보조 관측·근거 저장 | 2026-10-15, `feat/report-gpu-memory`: 결측·비정상/중복 값·Job 이름 재사용·혼합 원천·기간 경계와 표본 가중 메모리 검증. 기존 수동 결과의 모델 10행·기존 Namespace 수치 232개·사건 합계 불변 확인. 자동/수동 집계 fixture E2E 및 실측 결과의 격리 PostgreSQL Store→JC 발행→재조회·근거 13개 hash 일치 확인 | 실제 운영 자동 발행, 주간/최대 규모/동시 부하 미검증. 이전 실행의 통과 수를 최신 코드의 검사 결과로 간주하지 않음 |
| CPC-2 smoke 실자료·LLM 응답 재생 | 2026-10-15 CPC-2 실제 Mimir와 읽기 전용 사건 snapshot으로 제품 집계 실행. 배치 3건의 Job 경과시간 1,209/2,418/3,628초 확인. Pending 원천 표본 2→1→0, 제품 시간대 최대 2→0 대조. 실제 운영 모델 원문 응답을 최종 검증기에 수정 없이 재생하고 계산 topics 불변 확인 | 완료 일일 합계에는 오늘 완료된 이전 v3 Job도 포함. Job 경과시간은 대기·준비 포함이며 별도 대기/실행 시간 측정이 아님. 진단 100,000 token budget/6,000 synthesis max이며 운영 기본 예산의 새 Worker 발행·모델 성공률 미검증. 짧은 연결 구간은 메모리 검증에서 제외되므로 오전 메모리와 오후 대기를 동시 관측으로 해석하지 않음 |
| 집계 데이터량 | CPC-1 1일 표본에서 103,716→1,968 samples, 1,698,241→167,175 bytes | 쿼리 시간·DB 디스크·프로세스 최대 RSS 개선을 뜻하지 않음. 산식과 조건은 집계 명세 참조 |

주입 때 발행된 내용 hash:

- XID79: `13a44c8cc52087158f47e9b1ee69cc5df2bcd6af3d1a08e8c3f70ebd43561fcc`.
- SXID11001: `ee1475be64daec318d40c435ee69a5c176b3019f21a177e47adfdde40dacaf0d`.

관련 원천 근거: [binding 표본](../docs/evidence/d-binding-cpc-20261006.md), [발견/UID](../docs/evidence/d-binding-discovery-20261007.md), [D 확장](../docs/evidence/d-observation-expansion-20261007.md), [D07/D13](../docs/evidence/d07-d13-source-review-20261007.md), [Fleet 상태·이벤트](../docs/evidence/fleet-state-event-review-20261008.md), [지침 의미](../docs/evidence/rca-runbook-guidance-20261013.md), [집계 산식·측정](../docs/specs/ops-agent/aggregate-report-v1.md).

## 남은 검증

- 평가 척도: [rubric 1](../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md#분석-품질-평가-척도--rubric-1)의 적절한/과장된 분석 쌍을 실제 모델에 재생하여 항목별 누락·오검출·비용을 사람이 원본과 대조해야 함. 고정 응답의 분기 통과는 의미 정확도 검증이 아님.
- RCA: 실제 사건의 대상·발생 시각·현재 상태·원인 근거, 모델 응답의 의미 품질, 오류별 보완 D 선택과 지침의 적합성.
- Runbook: [265개 전환 검토](../rcca-agent/runbooks/transition-review-20261014.json)의 196개 계약 통과는 의미 승인이나 발행이 아니다. 69개 보류와 기존 구조화 내용의 병합 검토, 최신 운영 revision/hash·profile 대조가 필요하다.
- Ops: 운영 기본 LLM 예산에서 자동·수동 신규 발행, 주간·최대 크기·동시 실행의 지연/RSS 확인. 메모리의 전체 시간대 표본 조건 때문에 짧은 실행·연결 변경 구간이 제외되는 한계를 유지하며, 같은 시간대 활동률·메모리·대기를 연결하는 심화 해석은 후속 검증 대상.
- 운영: 최신 이미지 배포, 기존 일정·과거 결과 호환, PVC 파일 정리·복구. 별도 운영 승인과 환경 확인이 필요하다.

이전 실행의 상세 조건은 [정리 전 검증 이력](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/blob/f7bed6c594dc44a4b1d053bc8b60e2761c0b7f0c/agents/QA.md)에서 확인한다. 과거 통과 수를 새 revision의 결과로 재사용하지 않는다.
