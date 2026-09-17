# 공유 계약과 스키마

`contract`는 stdlib 기반 DTO·scope·시간 범위 정규화·해시 유틸리티다. `migrations`는 Backend(001/002)와 Job Controller(001/002/003)가 같은 스키마를 사용하게 하는 유일한 SQL 원본이다. Backend의 기존 internal/contract와 migrations 패키지는 호환 래퍼다.

DB 소유권: Backend는 설정·수동 요청 원본·일정/outbox, JC는 jobs·attempts·명령 receipt·Worker·capacity·reservation을 쓴다. Agent는 evidence·result_candidates를 저장하고 JC complete로 발행을 요청한다. 공개 candidate는 DB 트리거로 수정·삭제를 금지한다. Incident가 incident_evidence_versions의 실제 증거 snapshot을 먼저 저장해야 RCA를 접수할 수 있다.

루트 Go workspace가 없어도 각 모듈의 상대 `replace`로 빌드한다. Docker 빌드 context는 저장소 루트다.
