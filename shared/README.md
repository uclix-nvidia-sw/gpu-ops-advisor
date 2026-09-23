# 공유 계약과 스키마

`contract`는 stdlib 기반 DTO·scope·시간 범위 정규화·해시 유틸리티다. `migrations`는 Backend(001/002)와 Job Controller(001/002/003)가 같은 스키마를 사용하게 하는 유일한 SQL 원본이다. Backend의 기존 internal/contract와 migrations 패키지는 호환 래퍼다.

DB 소유권: Backend는 설정·수동 요청 원본·일정/outbox, JC는 jobs·attempts·명령 receipt·Worker·capacity·reservation을 쓴다. Agent는 evidence·result_candidates를 저장하고 JC complete로 발행을 요청한다. 공개 candidate는 DB 트리거로 수정·삭제를 금지한다. Incident가 incident_evidence_versions의 실제 증거 snapshot을 먼저 저장해야 RCA를 접수할 수 있다.

Incident는 001/002/004/005를 시작 시 적용한다. `005_incident_episodes.sql`은 Incident 소유의 생명주기 테이블·관측 에피소드 열·열린 그룹 유일 인덱스·최초 snapshot revision 제약을 추가한다. 기존 1.3 행은 재분류하지 않으며, legacy 생명주기 귀속은 명시적 1.4 생산자 전환에서만 준비한다. JC/Worker의 1.4 접수·배분 계약은 이 migration에 포함하지 않는다. 적용 순서와 복구 조건은 [Incident 안내](../incident/README.md)의 에피소드 업그레이드를 따른다.

JC는 001/002/003/006을 시작 시 적용한다. `006_worker_contracts.sql`은 Worker의 지원 입력 계약을 저장하며 기존 Worker는 1.3으로 해석한다. 기존 job·snapshot·hash는 변경하지 않는다. 적용 순서와 복구 조건은 [JC 안내](../job-controller/README.md#rca-입력-계약-전환-준비)를 따른다.

루트 Go workspace가 없어도 각 모듈의 상대 `replace`로 빌드한다. Docker 빌드 context는 저장소 루트다.
