# DSX 전체 개발 구조 v1.3

2026-09-17 · [개발 산출물](../deliverables-20260917-v1.3/00_산출물_안내.md) 기준 · 구현 전 목표 구조

[고해상도 PNG](dsx-job-controller.png) · [HTML 원본](dsx-job-controller.html) · [벡터 SVG](dsx-job-controller.svg)

![DSX 큐 관리와 기존 자원 내 잡 배분](dsx-job-controller.png)

## 실행 경로

| 기능 | 경로·책임 |
|---|---|
| RCA 생성 | Grafana → Incident → Job Controller → RCA Agent |
| RCA 조회 | GUI → Backend → 저장 사건·결과 |
| 즉시 보고서 | GUI → Backend → Job Controller → 보고서 Agent |
| 정기 보고서 | Backend 내부 스케줄러 → 동일 보고서 큐 |
| 잡 배분 | 처리 여유가 있는 Agent가 pull, Job Controller가 한도 내 claim 응답 |
| 용량 변경 | 운영자가 Agent 배포 수·자원·동시성 설정을 수동 조정 |

Job Controller는 영속 큐·잡 배분·점유/완료·제한 재시도만 관리한다. CPU/GPU·Pod·레플리카를 생성하지 않는다. 자원이 부족하면 잡을 큐에 보존하고 다음 실행 기회를 기다린다. Chatbot·독립 달력 Scheduler·자동 확장·제품 인증은 이번 구조에 없다.

RCA·보고서 Agent는 독립 실행·배포 모듈이다. Agent가 DB의 jobs를 직접 점유하지 않고 Job Controller API로 인수한다. 결과 후보와 근거는 Agent가 저장하고 공개 final 참조는 Job Controller가 유효 attempt를 확인한 뒤 확정한다.

## 표시와 명세 연결

청색은 요청/잡 인수 응답, 회색 실선은 인수 요청·실행 상태, 회색 점선은 운영자의 수동 조정이다. [D]는 공유 업무 데이터, [Q]는 기존 관측 조회, [L]은 공유 추론이다. 반복 데이터 의존선과 조회 응답선은 생략했다. Agent 1…N은 운영자가 정하는 배포 수이며 자동 증가를 뜻하지 않는다.

[Backend·일정](../deliverables-20260917-v1.3/02_백엔드_API_작업명세서.md) · [Job Controller](../deliverables-20260917-v1.3/10_Job_Controller_모듈_설계서.md) · [RCA](../deliverables-20260917-v1.3/11_RCA_Agent_모듈_설계서.md) · [보고서](../deliverables-20260917-v1.3/12_보고서_Agent_모듈_설계서.md) · [Incident](../deliverables-20260917-v1.3/13_Incident_모듈_설계서.md) · [공통 계약](../deliverables-20260917-v1.3/14_모듈간_호출과_공통실행_계약.md)

HTML/SVG는 2640×2120, PNG는 5280×4240이다. 연결선/라벨 좌표와 브라우저 글자 경계를 검사했다. 원격 폰트가 로드되지 않는 환경은 설치된 대체 글꼴을 사용한다. 동일 외형으로 공유할 때는 PNG를 사용한다.
