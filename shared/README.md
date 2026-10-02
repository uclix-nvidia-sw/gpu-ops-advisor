# 공유 계약과 스키마

## Runbook-first 입력 지원 — 2026-10-02

JC의 추가 migration `007_runbook_contract.sql`은 Worker 지원 계약 제약에 RCA 1.5를 추가한다. 새 테이블이나 기존 job/snapshot/hash 변경은 없다. 기존 1.3/1.4 계약은 유지한다. 신규 Incident 요청은 R 없이 1.5로 전달하고, Python Worker는 1.3/1.4/1.5를 구분해 검증한다. RCA 결과의 assessments는 Runbook 질문 기준이며 과거 purpose_id는 화면에서 읽기 호환한다.

## RCA 관측 호환 보완 (2026-09-30)

공통 Python 수집기는 밀리초 정밀도 축소의 실제 요청 범위와 개별 관측 사용 가능 여부를 기록한다. 원본 기간 complete=false는 유지하고 RCA health 해석만 사용 가능 범위를 구분한다. Ops 집계/매핑 완전성 요구는 유지한다. 등록 Fleet JSON adapter와 기존 producer JSON parser를 함께 지원한다. [RCA 계약](../rcca-agent/README.md#2026-09-30-fleet-rca-수집분석-보완)을 따르며 DB 테이블·migration·소유권 변경은 없다.

`contract`는 stdlib 기반 DTO·scope·시간 범위 정규화·해시 유틸리티다. `migrations`는 Backend(001/002)와 Job Controller(001/002/003)가 같은 스키마를 사용하게 하는 유일한 SQL 원본이다. Backend의 기존 internal/contract와 migrations 패키지는 호환 래퍼다.

DB 소유권: Backend는 설정·수동 요청 원본·일정/outbox, JC는 jobs·attempts·명령 receipt·Worker·capacity·reservation을 쓴다. Agent는 evidence·result_candidates를 저장하고 JC complete로 발행을 요청한다. 공개 candidate는 DB 트리거로 수정·삭제를 금지한다. Incident가 incident_evidence_versions의 실제 증거 snapshot을 먼저 저장해야 RCA를 접수할 수 있다.

Incident는 001/002/004/005를 시작 시 적용한다. `005_incident_episodes.sql`은 Incident 소유의 생명주기 테이블·관측 에피소드 열·열린 그룹 유일 인덱스·최초 snapshot revision 제약을 추가한다. 기존 1.3 행은 재분류하지 않으며, legacy 생명주기 귀속은 명시적 1.4 생산자 전환에서만 준비한다. JC/Worker의 1.4 접수·배분 계약은 이 migration에 포함하지 않는다. 적용 순서와 복구 조건은 [Incident 안내](../incident/README.md)의 에피소드 업그레이드를 따른다.

JC는 001/002/003/006을 시작 시 적용한다. `006_worker_contracts.sql`은 Worker의 지원 입력 계약을 저장하며 기존 Worker는 1.3으로 해석한다. 기존 job·snapshot·hash는 변경하지 않는다. 적용 순서와 복구 조건은 [JC 안내](../job-controller/README.md#rca-입력-계약-전환-준비)를 따른다.

루트 Go workspace가 없어도 각 모듈의 상대 `replace`로 빌드한다. Docker 빌드 context는 저장소 루트다.
