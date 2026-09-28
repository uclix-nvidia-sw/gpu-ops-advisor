# Agent 검증 기록

## 2026-09-28 Runbook 콘텐츠 연계 후속 검증

일반 조사 `RB-GENERAL-GPU-NODE`와 `RB-SXID-11001`을 추가해 작성 초안이 4건이다. `investigation_only` 일반 계획을 원인 판정·fast path 근거에서 제외하고, 선택된 Runbook의 revision·적용 상태·analysis_guidance·limitations를 Synthesis에 전달했다.

PR 준비 최종 재검증: **전체 102 passed(일반 94 + E2E 8)**, 기존 MCP client deprecation warning 3건. 아래 101건 및 94건 분리 실행 이후 같은 격리 환경에서 전체를 다시 실행했다. 원격 CI 성공을 의미하지 않는다.

- **통과:** 전체 실행 101건(일반 검사 93 + 실제 프로세스 E2E 8). 일반 JSON에 격리 테스트 cluster 호환성만 부여해 DB에 발행한 뒤 실제 JC/Worker/NAT/MCP 수집·Synthesis 요청·저장·보고서 인용을 검증했다. Grafana 데이터와 LLM 응답은 fixture다.
- **통과:** 추가한 일반 Runbook 표시 누락 방어를 포함한 RCA 분석 검사 13건, 최종 일반 검사 재실행 94건. Xid/SXid JSON의 검색·수집 계획 소비 및 오류 코드 fact 미확인 시 candidate 유지, 잘못된 일반 판정 콘텐츠 거부를 확인했다. 운영 producer/parser 검증은 아니다.
- **통과:** Ruff lint/format, 문서 링크, diff 공백 검사. 실행 명령과 격리 환경은 아래 실행부 검증과 같으며 단위 검사에는 `--basetemp=.local/pytest-runbooks`를 사용했다.
- **미검증/미수행:** 실제 Fleet 로그 parser·대상/버전/freshness 계약, Backend 발행 단계의 v1 validator 연결, 운영 발행·LLM 연결·배포. 네 초안의 빈 compatibility는 운영 실행을 차단한다. GPU reset·재부팅·진단 도구 실행은 하지 않았다.

세부 작성·실행 계약은 [Runbook README](../rcca-agent/runbooks/README.md)에 기록했다. 새 DB 구조나 운영 설정 변경은 없다.

## 2026-09-28 RCA 병렬 조사·Synthesis 구현 검증

로컬 파일 개발 단계다. [보완 계획](../docs/specs/rca-agent/implementation-plan-20260928.md)의 입력 1.3 실행부를 구현했다. 실제 LLM endpoint 연결, 운영 Runbook 발행, 배포는 수행하지 않았다.

| 검사 | 결과·검증 범위 |
|---|---|
| 단위/Worker + 실제 프로세스 E2E | **99 passed**: 일반 검사 91개 + E2E 8개. Python 3.12.14 / NAT 1.5.0 / 공식 Grafana MCP 1.4.2 / PostgreSQL 16.9 |
| 수집·분석 | 기존 근거 충분 시 MCP·LLM 0회, 승인 일반 Runbook 대체, 발행본 없음→조회 0회, 병렬 수집·예산 예약·실패 격리·취소 회수, 최대 1회 재조사, 도구 없는 최종 Synthesis |
| 모델 경계 | 없는 근거 참조·추가 query·인과 수준 필드·숫자 claim 거부. 잘못된 계획/분석 응답의 근거 보존, endpoint 미구성 표시, 원격 종료 불명의 Worker 격리 경로 |
| 입력·저장·보고서 | 실제 Incident webhook→JC→RCA Worker→NAT/MCP→DB candidate→JC 공개. 원문/hash와 provider action 미수행 보존. 공개 RCA ID/hash의 보고서 인용 및 기존 에너지 계산·실패 격리 회귀 |
| MCP 시간 정밀도 | 실제 webhook 마이크로초 시각으로 Loki parser 실패를 재현한 뒤 공통 시간 변환으로 해결. 조회창 확장 없이 밀리초 경계 사용, 줄어든 구간은 `time_precision_reduced`/partial 기록. 두 Worker 공통 경로 검사 |
| 정적/배포 검사 | Ruff lint·format, 문서 링크, `tools/ci/check_chart.py`(Helm 3.17.3), CI 계약 unit test 3개 통과 |
| 미검증 | 운영 Grafana/Mimir/Loki 쿼리 평가·인증·producer 의미, 실제 모델 품질, Fleet 오류 fact parser·binding·freshness, 입력 1.4 목적 자동 선택·이력 고정, 운영 배포 |

저장소 루트의 Python 3.12 venv에서 `python -m pytest -c agents/pytest.ini agents/tests -q`를 실행했다. `RUN_AGENT_E2E=1`, 실제 JC/Incident/MCP 바이너리, 검증한 Helm 3.17.3을 지정했다. Windows 한글 경로의 PostgreSQL 초기화 문제 때문에 테스트의 `LOCAL` scratch 경로만 ASCII 임시 폴더로 바꾼 로컬 runner를 사용했다. 매 실행 새로운 data directory와 무작위 localhost 포트를 사용하고 종료했다. 운영 DB 환경변수는 재사용하지 않았다.

Grafana datasource HTTP 응답과 모델 응답은 fixture다. 일반 Runbook은 격리 DB에만 넣은 계약 fixture이며 운영 콘텐츠가 아니다. MCP Host 보호 회귀 3건도 실제 바이너리로 통과했다. 기존 MCP Python client의 deprecation warning 3건은 남아 있으며 실행 실패는 아니다. Incident Go 검증은 [Incident QA](../incident/QA.md)를 따른다.

Ruff 명령은 `ruff check shared/python/src rcca-agent/src ops-agent/src agents/tests tools/ci`, `ruff format --check`에 같은 경로를 사용했다. 문서/차트/CI 검사 명령은 `python tools/check_links.py`, `python tools/ci/check_chart.py`, `python -m unittest discover -s tools/ci/tests -v`다. 최종 전체 실행 로그/XML은 로컬 `.local/rca-e2e-results.xml`에 보관한다.

## 2026-09-18 Incident → RCA 계약 회귀 검증

실제 Incident는 `snapshot.alert`를 저장하지만 RCA가 `snapshot.evidence`만 읽어 실패하던 문제를 수정했습니다. 새 회귀 테스트를 먼저 추가해 수정 전 실제 웹훅 경로의 RCA 작업이 `failed`가 되는 것을 재현했습니다. 수정 후에는 snapshot을 변경하지 않고 `alert`를 읽으며 legacy `evidence`도 지원합니다. 원본 알람 필드를 검증된 사실로 승격하지 않습니다.

- 단위/Worker 테스트 29개와 실제 프로세스 E2E 5개, 총 **34 passed**.
- 새 경로: Grafana 형식 HTTP webhook → 실제 Incident 저장/outbox → 실제 JC → 실제 RCA Worker/NAT/공식 Grafana MCP → 결과 저장/JC `succeeded`.
- 이 회귀 테스트는 Incident snapshot이나 RCA job을 DB에 직접 삽입하지 않습니다. Incident가 생성한 R01/R02 목적, 원본 alert, evidence snapshot과 hash 보존을 확인합니다.
- 별도 프로필 없이 datasource 자동 탐색, 기존 legacy snapshot·Runbook·보고서·실패 격리 경로도 통과했습니다.
- Ruff lint/format, actionlint, 문서 링크 검사를 통과했습니다. CI와 Windows 테스트 스크립트에 실제 Incident 바이너리 빌드를 추가했습니다.

Windows 로컬 PostgreSQL 초기화는 샌드박스의 restricted-token 오류 때문에 일반 사용자 권한에서 격리된 테스트 DB로 실행했습니다. Grafana/Mimir/Loki와 LLM 응답은 fixture이며 운영 연결이나 실제 모델 품질을 검증한 것은 아닙니다. 아래 2026-09-17 기록의 RCA snapshot 테스트는 DB에 직접 넣은 fixture였으며 실제 Incident 생산 형식을 검사하지 못했습니다.

## 이전 검증 기록

검증일: 2026-09-17, Windows, Python 3.12.14, NAT 1.5.0, 공식 Grafana MCP 1.4.2, PostgreSQL 16.9, 저장소의 실제 Go Job Controller.

## 실행 결과

| 검사 | 결과 |
| --- | --- |
| 최소 단위/Worker 테스트 | 8 passed |
| 실제 프로세스 E2E | 3 passed |
| Ruff 정적 검사 | 통과 |
| Python compile/모듈 import | 통과 |
| Docker Compose 구성 구문 검사 | 통과 (`config --no-env-resolution -q`) |
| 공식 MCP Windows 릴리스 SHA-256 | 검증 |
| 공식 Docker 이미지 `grafana/mcp-grafana:1.4.2` 태그 | 존재 확인 |
| Linux Docker build/up | NOT RUN — 사용자 안내에 따라 Windows 프로세스로 대체 |
| 운영 Grafana/Mimir/Loki·실제 LLM endpoint | NOT RUN — 해당 연결 정보/키가 제공되지 않음 |

## 최소 테스트

- 전용 할당 합집합 중복 제거, 공동 유효 구간 교집합.
- 58분 공동 관측/54분 저활동 고정 사례, 5분 할당·30분 Pod 교체 후보 보류.
- 시간 가중 평균/P95, 좌측 유지 전력 적분, 공백·중복 충돌 처리.
- 검사 불가+Healthy → unknown, Go JSON 호환 hash, reasoning tag 제거.
- 호환성 제한 후 최신 Runbook 선택.
- 주제별 ready/partial/blocked 집계, HTML escape·CSV 수식 방어.
- 실제 LLM 요청 형식 및 timeout 시 원격 종료 unknown.
- scope escaping·등록 query ID·조회 예산·기간 범위 제한.
- 비동기 heartbeat 중 취소, 미종료 LLM unknown 보고, 저장 실패 시 complete 미호출.

## E2E 경로와 단언

실제 구성: 테스트 전용 PostgreSQL → **실제 JC HTTP API** → **별도 Worker 프로세스** → **NAT workflow/MCP client** → **공식 Grafana MCP Windows 서버**.

Grafana datasource HTTP 응답과 OpenAI 호환 LLM endpoint만 고정 데이터 서버로 대체했습니다. 따라서 실제 Mimir/Loki 엔진의 쿼리 평가·운영 인증·실제 모델의 진단 품질을 검증했다는 의미는 아닙니다.

1. Incident snapshot → RCA claim → Loki 로그 조회 → LLM의 등록 D02 선택 → Mimir 호환 원본 표본 조회 → 상태 정규화·후보 저장 → JC complete. 이어 보고서가 공개된 RCA ID/hash를 인용하고 GPU 전력 250W×1시간=0.25kWh를 산출합니다. DB 저장 본문 hash, HTML/CSV 파일 checksum을 확인합니다.
2. LLM 503 + Loki 실패 시에도 O09 에너지 0.25kWh를 보존합니다. O10은 blocked, 설명은 failed이며 독립 주제를 지우지 않고 JC가 결과를 발행합니다.
3. O01~O11 전체 결과가 주제별 상태를 유지합니다. 호환 발행 Runbook의 필수 증거가 이미 충분한 R01은 추가 MCP 조회 없이 조건·권고를 평가하고 supported 후보를 발행합니다.

실행 명령: `./agents/scripts/test.ps1 -E2E -PgBin ./backend/.local/postgres/bin/bin`

테스트는 임시 포트와 새로운 DB data directory를 사용하며 기존 DB 데이터에 접근하지 않습니다. 이번 테스트의 로그와 보고서 파일은 `.local/agent-e2e/`에 있습니다. 초기 Windows PostgreSQL 관리자 직접 실행/파이프 상속 오류는 `pg_ctl`의 권한 처리와 DEVNULL 출력으로 수정했습니다. 실제 Grafana MCP가 Prometheus query를 form POST로 전송하는 동작도 fixture에 반영했습니다.

## 남은 운영 검수

배포 C02~C07의 실제 datasource UID/CPC 필터/metric 의미/원본 주기/조회 한도, Fleet parser 계약, 할당/작업 신원·완전성, 기대 대상 분모를 설정해야 합니다. 설정이 없는 판단은 null/partial/blocked입니다. 실제 도구 호출 모델 호환성, 실제 GPU 부하·공백·장기 이력과 C08 회복 정책은 운영 표본으로 별도 검수해야 합니다.
