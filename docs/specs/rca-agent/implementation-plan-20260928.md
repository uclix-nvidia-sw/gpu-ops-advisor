# RCA 입력·병렬 조사·Synthesis 구현 계획

2026-09-28 · 로컬 개발 기준. 운영 배포·실환경 분석 품질 검수 완료를 뜻하지 않는다.

다른 PC에서 이어받는 순서, 코드 위치, 검증 재현 및 CSC 적용 조건은 [RCA·Runbook 인수인계](../../../rcca-agent/HANDOFF.md)를 따른다.

사용자가 제공한 `rca-orchestrator-synthesis-pipeline.md`, `GPU_노드_RCA_장애_Domain_Category_메트릭_매핑(수정).md`, `GPU_노드_RCA_Agent의_Knowledge_DB_설계.md`를 현행 코드 및 11번 설계서와 대조했다. 아래 결정이 첨부 초안의 미정 항목과 과거 구현 설명보다 우선한다. 원본 파일의 운영 접속 정보·fault injection 명령은 실행하거나 저장소에 복사하지 않는다.

## 1. 채택·보완 사항

| 첨부 제안 | 반영 결정 |
|---|---|
| Orchestrator + Observation Sub-agent + Synthesis | 하나의 NAT workflow/Worker/JC lease 안에서 역할을 분리한다. 관측 sub-agent는 query별 asyncio task로 생성·회수하고 별도 서비스나 JC job을 만들지 않는다 |
| Runbook 기반 계획 | DB에서 scope·published/retired pinned revision·hash를 제한한 뒤 결정적 검색과 조건 검사를 수행한다. LLM은 검색하지 않는다 |
| Runbook 부재 | 사용자가 승인한 **일반 조사 Runbook 대체**를 적용한다. `rca.general_runbook_key`로 지정된 승인·고정 revision만 사용한다. 일반 Runbook도 없거나 검증이 안 되면 `approved_runbook` 부족으로 종료한다 |
| 병렬 조사 | 기본 동시성 3, `limits.max_concurrency`로 조정. query별 독립 Observation 상태와 예산을 주고 같은 NAT MCP 연결의 읽기 도구를 사용한다 |
| 예산 예약 | 최초 라운드에 잔여 query/discovery 예산의 절반을 올림하여 예약하고 query별로 분배한다. 다음 라운드에는 잔여 한도를 분배한다. 이미 발행한 실패 호출도 소비로 계산하며 미사용 예약은 형제 회수 후에만 재사용한다 |
| 재조사 | 최초 수집 + **최대 1회** 재조사. 기존 공통 `limits.max_followups`가 더 커도 RCA는 1회를 넘지 않는다. 충분하면 재조사를 강제하지 않는다. 이미 실행한 query를 다시 선택할 수 없다. 실패·부분 수집은 degraded로 남기고 증거 부족 재조사로 치환하지 않는다 |
| 충분성 | 코드가 목적별 필수 입력·Runbook 적용·품질·상충으로 판정한다. LLM의 완료 선언으로 ready/confirmed를 만들지 않는다 |
| Synthesis | 관측 라운드가 끝난 뒤 한 번 실행한다. 도구 없이 검증된 관측·Runbook·부족 입력을 해석하며 모델 후보는 항상 candidate다. 최종 assessment·권고 자격·저장·공개는 코드 책임이다 |
| 기존 증거 충분 | 이전 합의 유지: MCP와 LLM 모두 생략하고 같은 검증·저장·공개 경로로 진행한다 |
| 근거 부족 종료 | 유효 관측이 있으면 한계를 포함해 Synthesis를 수행한다. 유효 증거 자체가 없으면 모델 추론도 생략한다. 모델 미구성·잘못된 출력은 partial/blocked와 진단으로 보존한다 |
| 병렬 결과 hash | 완료 순서 대신 query/cluster/period/input으로 정렬한다. UUID·수집 시각이 다른 별도 실행의 전체 hash까지 같다고 약속하지 않는다. JC complete 재시도는 같은 저장 candidate/hash를 재사용한다 |
| 취소 중 증거 보존 | 모든 task를 회수하고 확보 결과를 메모리에 보존한다. 유효 lease가 없거나 취소된 작업의 중간 증거를 성공 결과로 강제 저장·공개하지 않는다 |

## 2. 입력과 Knowledge DB 문서의 보완

- Incident의 수신→원문/snapshot 저장→outbox→JC 전달은 이미 구현돼 있다. 1.4의 `k8s_node_name`을 labels와 annotations 양쪽에서 받도록 보완하며, 서로 다르면 신원 충돌로 거부한다. 1.3의 기존 사건 dedup 키와 원문/hash는 재작성하지 않는다.
- RCA는 `reason`, `component`를 **검색 단서**로 사용한다. `XID 79`와 `SXID 11001`은 각각 `xid:79`, `sxid:11001`로 구분한다. 이름·코드 추출은 producer 의미나 GPU 신원의 검증을 대신하지 않는다.
- `suggested_actions` JSON 문자열의 원문·순서를 보존한다. 파싱된 권고도 withheld/not_performed이며 실행 증거나 자동 reboot 지시로 사용하지 않는다.
- GPU UUID가 없는 PCI 주소·노드 표시 이름으로 GPU 신원을 만들지 않는다. `Healthy - ... skipped evaluation` 같은 문자열도 배포된 parser 계약 없이 정상 fact로 승격하지 않는다.
- 우선 콘텐츠 대상은 Xid, SXid, InfiniBand, NVML, NCCL, peermem이다. `accelerator-nvidia-dcgm-*` 콘텐츠는 후순위이며, 필요한 DCGM 메트릭의 보조 수집까지 금지한다는 의미는 아니다.
- Domain/Category는 Runbook 검색·관측 범위를 좁히는 분류로 활용한다. 9개 Domain/31개 Category를 검증된 운영 seed나 고정 상한으로 취급하지 않는다. 같은 DCGM field라도 producer별 label·unit·시각·sentinel을 검증하기 전 병합하지 않는다.
- `gpu_kb.*` 테이블 신설을 이번 실행부의 선결 조건으로 삼지 않는다. 현재 `knowledge_revisions.content`와 `content.schema`, `classification`, `search`, `observation_plan`을 재사용한다. 새 DB 계층·migration/API는 실제 조회·관리 요구와 소비자 계약을 정한 뒤 별도로 구현한다.
- 첨부 Knowledge DB 문서의 `validated:false` 전체 설정, snapshot.evidence만 소비한다는 과거 설명은 현재 코드와 다르다. 기본 D01~D13은 `validated:true`이며 alert/evidence를 모두 읽지만, 이것이 운영 의미 계약까지 검증됐다는 뜻은 아니다.
- Fleet REST 직접 adapter와 새 F/M/L query namespace는 이번에 도입하지 않는다. 현재 등록 D코드와 Grafana MCP를 유지한다. 기존 [Knowledge DB 참고 설계](drafts/knowledge-db-reference.md)와 [메트릭 매핑](references/domain-category-metric-mapping.md)의 생산자별 검증 기준을 따른다.

## 3. 개발 단계와 완료 기준

| 단계 | 이번 작업 범위 | 완료 기준 / 남은 의존성 |
|---|---|---|
| 입력 보완 | Incident node 라벨 매핑, RCA reason/component/action 단서 | 원문 hash 유지, 라벨 충돌 거부, Xid/SXid namespace 보존, action 미수행 |
| Runbook 연결 | 결정적 검색, v1 validator, pending compatibility, 명시적 일반 Runbook 선택 | 미승인/미고정/잘못된 schema는 실행 계획에 사용하지 않음. 새 원문 알람의 verified_facts는 신뢰하지 않음 |
| 병렬 실행 | 예산 분배, task 격리, 동시성 상한, 회수, 증거 정렬 | 병렬·부분 실패·예산 부족·취소 테스트 및 실제 NAT/MCP 통합 |
| 판단·합성 | 코드 충분성, 최대 2라운드, 도구 없는 Synthesis, 안전한 결과 변환 | 수집만으로 완료 금지; 위조 참조/숫자/causal status/추가 조회 출력 거부; LLM 미구성·원격 종료 불명 구분 |
| 저장·소비 | 기존 Worker/Store/JC 및 Ops 경로 재사용 | 같은 transaction의 근거·candidate 저장, JC publication, Report의 공개 ID/hash 참조 회귀 |
| 후속 1.4 | **이번 실행부는 기존 1.3 입력에서 구현** | Agent 목적 자동 선택·선택 trace, 목적 선택 전 bounded DB 이력, 1.4 소비자 검증이 끝나기 전 Worker가 1.4 지원을 광고하거나 Incident 운영 설정을 전환하지 않음 |
| 후속 데이터 의미 | Fleet 1.5.0-rc.1과 실제 image/source 일치, component별 parser·binding·freshness | Runbook 담당 세션의 콘텐츠 검토와 운영 fixture 필요. 기본 health parser는 오류 코드 fact를 생성하지 않는다 |
| 후속 운영 검수 | 로컬 LLM endpoint, 실제 Grafana 데이터, 승인 Runbook publication | 사용자가 endpoint를 나중에 제공하기로 함. fixture 검증과 구분하여 기록 |

일반 Runbook 콘텐츠를 `investigation_only: true`인 초안으로 추가했다. RCA는 이 콘텐츠의 관측 계획과 분석 지침을 소비하며 원인 판정용으로 승격하지 않는다. 테스트에서는 실제 JSON에 fixture cluster 호환성만 바인딩하며 운영 지식으로 발행하지 않는다. 초기 Runbook 초안과 검토 항목은 [Runbook README](../../../rcca-agent/runbooks/README.md), 실행 검증 결과는 [Agent QA](../../../agents/QA.md)에 기록한다.
