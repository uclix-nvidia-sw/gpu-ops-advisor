# 프론트엔드 검증 기록

검증일: 2026-09-17 · 기준: DSX FE/GUI v1.1 · 실행 환경: Windows, Node 24, Codex 내장 Chromium 브라우저.

이 기록은 **프론트엔드 데모 검증**입니다. 명세 05의 실환경 T01~T40, API/DB/LLM 통합 또는 인증 검수 PASS를 의미하지 않습니다.

## 자동 검사

| 검사 | 결과 |
|---|---|
| TypeScript strict + noUnusedLocals + noUnusedParameters | PASS |
| Vite production build | PASS |
| Vitest 11개 도메인 테스트 | PASS |
| Prettier 코드 형식 | 적용 완료 |

테스트는 같은 날짜의 KST 달력 범위, `[start,end)`와 역전 기간, CPC/Namespace 조합 보존, 월간 말일 및 주간 다음 실행, HTML escaping/CSV 수식 방어, 실행 완료+근거 부족, 취소 확정, 기한 만료, terminal 결과 불변을 확인합니다.

## 브라우저 확인

| 시나리오 | 결과·관측 |
|---|---|
| 기본 대시보드 | 1440px 데스크톱에서 요약, 우선 검토, 추이, 클러스터 현황, 사건 표 시각 확인 |
| CPC-2만 선택 | GPU 32개/4 Nodes, dgx-05~08 차트 대상으로 갱신 |
| 미배치 Pod 조사 | `finetune-bert-queue`에서 Node/GPU 선택 없이 접수·작업 상세로 이동 |
| 직접 조사 결과 | `succeeded + blocked`, 설명 생략, 관계/영향/원인 근거 부족을 독립 표시 |
| 새로고침 | 생성한 작업·직접 결과가 저장된 ID로 다시 열림 |
| 보고서 조건 | O01~O11 체크, 일회/정기 방식, 동일 시작·종료일 입력 확인 |
| 월간 일정 | 31일 요청이 2026년 9월 30일 09:00 KST로 계산됨 |
| 일정 일시중지 | 사유 저장 후 활성→일시중지, revision 1→2, 재개 버튼 표시 |
| 지식 관리 | 초안→검토 요청→승인→발행, 발행본의 새 revision 버튼 표시 |
| 모델 연결 검사 | 백엔드 미연결로 실행 불가 안내, 설정은 보존, 성공 표시하지 않음 |
| 조회자 역할 | 새로고침 후 역할 유지, 조사 제출 버튼 비활성 |
| 모바일 Assistant | 320px에서 dialog로 열림, 메시지 전송, 입력창이 화면 안에 유지됨 |
| Escape·포커스 | Assistant 종료 후 원래 Assistant 버튼으로 포커스 복귀 |
| 미저장 폼 | 앱 내부 확인창에서 계속 편집 시 입력 유지, 버리고 닫기 시 종료 |
| 데모 초기화 | 별도 앱 내부 확인 후 초기 fixture로 복원 |
| CSV 출력 버튼 | 파일 생성·다운로드 요청 UI 동작 확인. 내장 브라우저의 다운로드 완료 이벤트/디스크 파일은 확인하지 못함 |

320px에서 다음 16개 경로의 `document.documentElement.scrollWidth === 320`을 확인했습니다. 표는 자체 컨테이너 안에서만 가로 스크롤합니다.

`/dashboard`, `/fleet/assets`, `/fleet/workloads`, `/fleet/quality`, `/cases`, `/analyses/new`, `/reports`, `/reports/new`, `/schedules`, `/jobs`, `/knowledge`, `/settings/models`, `/settings/routing`, `/settings/data`, `/incidents/{id}`, `/reports/{id}`.

추가로 일정 상세와 직접 조사 상세의 정상 렌더링을 확인했습니다. 시험 중 만든 데모 레코드는 초기화했으며 최종 화면은 대시보드로 둡니다.

## 후속 통합·미검증

- 실제 principal/grant/access_revision, 세션 전환·권한 철회와 서버 캐시 경계.
- 실제 `/api/v1` DTO 연동, 멱등 응답 유실 복구, ETag 경합, 429/Retry-After, 서버 폴링.
- 서버 작업 원장, Worker 재시작·취소 경합, 실제 예약 실행·DST·발생 이력.
- 실환경 GPU/Pod 관측·지식 호환·모델 품질·실제 추론, 서버 export 접근 검사.
- 정식 스크린리더 및 WCAG AA 전수 감사, 실제 브라우저 200% 확대, 모바일 OS 키보드.
- 컨테이너 빌드·실행: Docker CLI가 환경에 없어 NOT RUN. Dockerfile/nginx SPA 경로 구성은 포함.
- 일반 Chrome/Edge의 HTML/CSV 다운로드 파일 검증.

기본 브라우저 `confirm()`의 내장 브라우저 상호작용 중단을 발견해 모든 확인 흐름을 `<dialog>` 기반의 앱 내부 UI로 교체했습니다. HMR 시 React root 중복 생성도 root 재사용으로 수정했습니다.
