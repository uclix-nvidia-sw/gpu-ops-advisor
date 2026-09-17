# Backend v1.3 검증 기록

2026-09-17 / Windows / Go 1.26.2 / native PostgreSQL 16.9 / Docker 미사용.

- Go 단위 테스트 2개: scope/시간 경계, 달력 DST gap/fold·23시간 완료일·월말·월요일 시작 주간: PASS.
- go vet 및 서버 빌드: PASS.
- 실제 HTTP + PostgreSQL E2E 1개, 아래 8개 subtest: PASS.

| 시나리오 | 확인 |
|---|---|
| v1.3 경계 | 인증 테이블 미생성·제거 API 404·등록 scope/중복/기간 422 |
| JC 접수/명령 | 커밋 후 응답 유실·동일 키/정규화 입력 복구·본문 충돌·queued·report 한정·receipt 우선·cursor |
| 최종 결과 | 후보 미노출·JC 발행 참조만 조회·Backend 재시작·HTML 이스케이프·CSV 수식 방어 |
| 지식 | 원자적 receipt·재전송·검토 hash 불일치 차단·발행본 불변 |
| 일정 복구 | 두 Backend 경합·단일 occurrence·outbox·마감 후 JC receipt로 accepted 복구·revision 보존 |
| 달력 backlog | catchup_window/max_catchup·중복 기간 missed/canonical 참조·일시 정지 후 pending 전달 |
| 모델/조치 | 불변 revision·라우팅 유지·사용 모델 비활성화 차단·secret_ref·용량 변경 거부·미인증 조치자 |
| 조회/장애 | dashboard/assets/workloads/quality/incident/procedure 조회·JC 미연결 503 |

실제 브라우저에서도 Frontend → Go → PostgreSQL 일정 생성 → 일시 정지 → 실행 시각 변경(revision 1→2→3)을 확인했습니다. 확인 중 등록 폼 시간대 누락을 수정했습니다. 검증용 일정 `16660c00-c133-4535-9804-91117afc3591`은 일시 정지 상태로 남겨 자동 실행을 막았습니다.

기존 로컬 DB에 보존 migration을 적용하고 새 Backend로 readiness 성공을 확인했습니다. frontend Vitest 3개·TypeScript/Vite build도 통과했습니다.

한계: JC/Incident/두 Agent는 실제 서비스가 연결되지 않았습니다. E2E의 JC는 PostgreSQL 커밋을 수행하는 계약 fixture이며 제품 JC 구현이나 실제 RCA/보고서 계산·LLM 실행 검수가 아닙니다. 실시간 관측, 운영 부하·배포·백업복원·원격 LLM 장애 시험은 NOT RUN입니다.
