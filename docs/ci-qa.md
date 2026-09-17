# CI·Helm 검증 기록

2026-09-17 / Windows / Python 3.12 / Go 1.26.2 / Helm 3.17.3.

| 검증 | 결과 |
| --- | --- |
| GitHub Actions actionlint 1.7.11 | PASS; 로컬은 shellcheck 미설치, CI에서는 기본 shellcheck도 실행 |
| Helm strict lint·기본 8 Pod 렌더링 | PASS |
| 외부 DB·임시 저장소·기존 PVC·Ingress·Secret·이미지 digest 변형 | PASS |
| 실제 packager 실행·7개 이미지 digest 주입·SHA256·패키지 재렌더링·원본 보존 | PASS; 격리된 임시 디렉터리의 fixture 이미지 metadata 사용 |
| 릴리스 metadata·태그 불일치·누락/다른 이미지 차단 단위 테스트 | 3 PASS |
| Python Ruff·format | PASS |
| Agent 단위/생명주기 + native DB 프로세스 E2E | 11 PASS, 78.76초 |
| CI의 외부 DB 경로로 Agent E2E | 3 PASS, 18.05초 |
| Go 4개 모듈 vet·단위 테스트·build | PASS |
| Backend + JC DB E2E | 2 suite PASS, 4.445초 |
| Incident + Backend + JC DB E2E | 1 suite PASS, 2.756초 |
| Frontend Prettier·Vitest·TypeScript/Vite build | PASS; Vitest 3개 |
| 저장소 문서 링크 검사 | PASS |

외부 DB E2E 경로는 실제 임시 PostgreSQL 서버를 사용해 CI service container와 동일한 URI 주입·별도 schema 생성/정리 방식을 검증했습니다. 공식 Grafana MCP·NAT·Go JC·Worker는 실제 프로세스이고 Grafana datasource 응답과 LLM 응답은 fixture입니다. 테스트용 프로세스는 종료했습니다.

로컬 검토용 chart는 `dist/gpu-ops-advisor-1.3.0-local.tgz`와 SHA256 파일로 생성합니다. 이 패키지는 원본의 이미지 namespace placeholder를 포함하므로 설치 전 실제 발행된 이미지로 설정해야 합니다. CI artifact는 해당 실행에서 생성한 실제 이미지 metadata로 자동 패키징합니다.

GitHub 원격 workflow 실행, GHCR 이미지/OCI chart 발행, Linux 컨테이너 빌드/실행, Kubernetes 실제 설치, 운영 Grafana/Mimir/Loki/LLM 연결은 이번 로컬 검증에서 **미실행**입니다. 로컬 Go는 일반 테스트이며 `-race`는 Linux CI에 구성했습니다. 기존 Windows Docker 환경 문제는 재설정하지 않았습니다.
