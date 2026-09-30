# CI·Helm 검증 기록

## 2026-09-30 PR #28 이미지 캐시 저장 실패

[실패 실행 36680447708](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/actions/runs/36680447708)의 커밋 `7fd8f3e`에서 Go·Python·Frontend·Helm 검사는 모두 통과했다. 이미지 7개는 OCI 출력 후 `exporting to GitHub Actions Cache` 단계의 `failed to reserve cache`로 실패했고 chart는 건너뛰었다. 캐시 서비스가 예약을 거부한 구체적인 원인(용량·권한·일시 장애)은 로그만으로 확정하지 않는다.

공통 이미지 workflow의 cache-to에 Docker 공식 `ignore-error=true`를 적용했다. 캐시 내보내기만 선택적으로 처리하고 이미지 빌드·발행·digest 및 필수 CI gate는 유지한다. 최신 수정 커밋의 원격 CI 결과는 PR #28에서 별도 확인한다. 운영 배포는 하지 않았다.

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

## 첫 GitHub 실행 후 수정

[실행 35200636511](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/actions/runs/35200636511)은 main push로 자동 실행됐습니다. Frontend와 Helm 검증은 통과했지만 Go 4개 작업과 Agent 작업은 PostgreSQL 컨테이너 생성 단계에서 실패했습니다. 실제 오류는 `unknown shorthand flag: 'U' in -U`, exit 125였습니다.

`services.postgres.options`는 shell script가 아닌 Docker 프로세스 인자 문자열이므로 healthcheck의 작은따옴표가 인자 경계로 처리되지 않았습니다. 두 서비스 정의를 folded YAML의 `--health-cmd "pg_isready ..."`로 수정했습니다.

검증: YAML에서 수정된 options를 읽어 .NET ProcessStartInfo로 Docker CLI `create ... --help`에 전달했습니다. 기존 설정 exit 125, 수정한 Go/Agent 설정 모두 exit 0을 확인했습니다. 이 검사는 컨테이너를 생성하거나 Docker engine을 시작하지 않습니다. actionlint, 릴리스 단위 테스트 3개, diff 검사도 통과했습니다. 기존 실행의 Re-run은 이전 커밋의 잘못된 설정을 다시 사용합니다.

## GitHub 성공 실행과 chart 발행 조건

[실행 35201173393](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/actions/runs/35201173393)은 수정된 main 커밋 `9c9c44f`에서 전체 CI에 성공했습니다. Go 4개 작업, Agent E2E, Frontend, Helm 검사, Linux 이미지 7개 빌드/발행과 chart 패키징이 통과했습니다. [helm-chart-1.3.0-ci.2.1 artifact](https://github.com/uclix-nvidia-sw/gpu-ops-advisor/actions/runs/35201173393/artifacts/10488510711)도 생성됐습니다. 위 최초 로컬 검증 당시의 미실행 항목 중 GitHub 실행·Linux 이미지 빌드·GHCR 이미지 발행은 이 실행으로 확인됐습니다.

당시 main은 chart artifact만 생성하고 OCI chart는 버전 태그에서만 발행하는 설정이었습니다. 이후 main push/merge도 동일한 이미지 발행 조건으로 OCI chart를 발행하도록 변경했습니다. CI 버전으로 정식 버전과 구분하고, PR·수동 실행의 미발행 동작은 유지합니다. 이 추가 변경의 원격 OCI 발행은 새 커밋을 push한 실행에서 확인해야 합니다. Kubernetes 설치와 운영 외부 서비스 연결은 아직 미검증입니다.
