# CI와 Helm 릴리스

현재 폴더 구조의 배포 단위는 `backend`, `frontend`, `job-controller`, `incident`, `rcca-agent`, `ops-agent`, `grafana-mcp`입니다. 이미지 목록·Dockerfile·빌드 context는 [components.json](../tools/ci/components.json)에서 관리합니다. 공통 Go/Python 코드는 라이브러리이며 별도 이미지로 발행하지 않습니다. PostgreSQL은 Helm이 공식 이미지를 사용합니다.

[로컬 검증 기록](ci-qa.md) · [Helm 설치 구성](../charts/gpu-ops-advisor/README.md)

## 실행 흐름

`ci.yml`은 모든 PR에서 먼저 Git 변경 범위를 계산한다. workflow 자체를 경로 필터로 건너뛰지 않으며, 마지막 `CI required`는 항상 실행한다. PR 비교는 base SHA와 검사 대상 merge SHA 사이의 전체 차이를 사용하며 삭제·이동의 이전 경로도 포함한다. 비교 대상 누락·빈 비교·분류하지 않은 경로는 전체 검증으로 처리한다.

| PR 변경 범위 | 모듈 검사 | 이미지 빌드 | Helm/CI 계약·문서 링크 |
| --- | --- | --- | --- |
| `frontend/**`만 변경(아래 설명 문서 포함 가능) | Frontend | Frontend 1개 | 항상 실행 |
| 설명 문서만 변경 | 생략 | 생략 | 항상 실행 |
| 서버·Worker·공유 코드·계약·설정·CI·그 밖의 경로 | Go 4개·Agent·Frontend 전체 | 7개 | 항상 실행 |

설명 문서는 `docs/**/*.md`, 루트의 `README.md`/`QA.md`, 기존 모듈 바로 아래의 `README.md`/`QA.md`만 허용한다. YAML·JSON·스크립트·알 수 없는 새 모듈은 전체 검증이다. Frontend 밖의 런타임 의존성은 아직 세분화하지 않는다. `main`·버전 태그·수동 실행은 이전 성공 결과에 의존하지 않고 전체 검증을 유지한다.

PR과 main 모두 테스트와 이미지 빌드를 metadata 뒤에서 병렬 실행한다. 빌드 단계는 registry 쓰기 권한과 로그인이 없으며 `push: false`로 Docker archive를 만든다. 모든 이미지의 archive를 실제로 load하고 revision label이 현재 `GITHUB_SHA`와 같은지 검사한다. PR에서는 필요한 이미지만 검사하며 발행하지 않는다.

main·태그는 빌드한 이미지 7개의 archive를 현재 workflow 실행의 임시 artifact(1일 보관, 압축 없음)로 전달한다. 별도 발행 작업이 **전체 테스트와 이미지 빌드 모두 성공한 후** archive를 다시 load하고 현재 SHA를 확인한 다음 로그인·push한다. 재빌드는 하지 않는다. 발행 후 registry digest를 기록하고, 7개가 모두 성공해야 digest를 고정한 Helm chart를 발행한다. archive 전송·적재·SHA 검증·push·digest 기록 실패도 CI 실패다. 일부 이미지 발행 후 다른 이미지가 실패할 수 있지만 해당 실행의 chart는 발행하지 않는다.

| 이벤트 | 테스트 / 이미지 빌드 | GHCR 이미지 | Helm artifact | OCI chart |
| --- | --- | --- | --- | --- |
| Frontend/문서 한정 PR | 위 표의 영향 범위 | 미발행 | 전체 이미지가 없어 생략; 공통 계약 검사는 실행 | 미발행 |
| 전체 검증 PR | 전체 병렬 | 미발행 | 검토용 `1.3.0-ci.<run>.<attempt>` | 미발행 |
| main push 또는 PR merge | 전체 병렬 | 테스트 성공 후 `sha-<full-commit-sha>` 발행 | 동일 CI 버전, registry digest 고정 | CI 버전으로 발행 |
| `v1.3.0` 버전 태그 push | 전체 병렬 | 테스트 성공 후 `v1.3.0` 발행 | `1.3.0` | 발행 |
| workflow_dispatch | 전체 병렬 | 미발행 | 검토용 CI 버전 | 미발행 |

선택된 검사에 대한 별도 `Planned tests required`가 Go/Agent/Frontend/Helm의 실패·취소·예상 밖 skip을 검사한다. 마지막 `CI required`는 metadata의 명시적인 계획과 각 단계의 결과가 일치해야 통과한다. 계획이 없거나 필요한 단계가 skip된 경우 통과하지 않는다. Branch protection의 필수 check 이름은 `CI required`를 유지한다.

이 변경은 PR 검사 결과를 main에서 재사용하지 않는다. main의 검사는 계속 수행하지만 빌드 대기를 겹친다. 따라서 Frontend PR은 무관한 Go/Agent 검사를 기다리지 않게 되며, main 단축 폭은 테스트·빌드 시간과 archive 전송 비용에 따라 달라진다. 실제 속도 개선은 적용 후 GitHub 실행으로 측정한다.

이미지 위치: `ghcr.io/<lowercase-github-owner>/gpu-ops-advisor-<component>:<tag>`.
Chart 위치: `oci://ghcr.io/<lowercase-github-owner>/charts/gpu-ops-advisor`.

main의 성공 실행은 고유한 `1.3.0-ci.<run>.<attempt>` chart와 이미지들을 발행한다. 버전 태그는 정식 버전을 사용하며 Actions의 chart 다운로드 산출물도 유지한다. Kubernetes 배포는 수행하지 않는다.

`frontend`만 `frontend/`를 Docker context로 쓰고, Go 서비스·Agent·MCP는 저장소 루트를 사용한다. 현재 플랫폼은 Linux/amd64 하나다. main에서 변경되지 않은 이미지도 모두 새 커밋 태그로 발행하므로 기존의 7개 이미지 metadata·chart 계약은 유지한다.

BuildKit의 GitHub Actions 캐시는 빌드 가속용이다. `cache-to`의 `ignore-error=true`는 캐시 업로드 실패만 허용한다. 실제 빌드·archive 검증·발행·digest·chart 실패는 계속 차단한다. [Docker 캐시 문서](https://docs.docker.com/build/cache/backends/gha/)와 [job 사이 이미지 전달](https://docs.docker.com/build/ci/github-actions/share-image-jobs/)을 따른다.

## 검증 범위

- Go: `shared`, `backend`, `job-controller`, `incident` 각각 vet·race 단위 테스트·빌드. Backend/JC/Incident는 PostgreSQL service container에 실제 DB E2E를 수행합니다.
- Python: 공통 패키지·두 Worker Ruff 검사 및 최소 단위/생명주기 테스트. PostgreSQL service container, 실제 Go JC, 실제 Worker, NAT, 체크섬 검증한 공식 Grafana MCP 1.4.2 프로세스로 E2E를 실행합니다. Grafana datasource 응답과 LLM 응답만 fixture이며 운영 외부 서비스는 호출하지 않습니다.
- Frontend: Prettier·Vitest·TypeScript/Vite build.
- Helm: strict lint, 실제 manifest 계약 검사, 기본/외부 DB·PVC·Ingress·Secret·digest 변형, 패키지 재렌더링, 릴리스 metadata 테스트.
- Actions: actionlint 1.7.11. 문서: 저장소 내부 링크·파일명 대소문자 검사.

Python 검사 job은 Worker 패키지 설치와 Go 바이너리 빌드·공식 MCP 다운로드/체크섬 검증을 같은 runner에서 병렬 준비합니다. 두 준비 작업의 종료 상태를 각각 확인하며 어느 쪽이든 실패하면 lint·테스트로 진행하지 않습니다. 실제 테스트 실행 순서와 이미지 발행 조건은 유지합니다.

런북 263개 일괄 등록 E2E는 해당 테스트의 격리 DB에서만 요청 한도를 1,000회/분으로 올리고 종료 시 원래 설정을 복원합니다. 전체 등록·조회/hash·재실행 중복 방지·RCA 소비 검증은 유지합니다. 실제 Backend의 429와 `Retry-After: 60`은 낮은 테스트 한도로 즉시 확인하고, CLI의 대기·동일 요청 재시도는 기존 단위 테스트에서 실제 대기 없이 검사합니다. 운영 기본 한도와 CLI 재시도 동작은 변경하지 않습니다.

Agent 프로세스 E2E는 각 테스트가 시작한 Backend·Worker를 테스트 종료 시(실패 시 포함) 종료하고 회수한다. 모듈 공통 JC·Incident·MCP는 유지하며, 테스트별 Backend DB pool이 누적되지 않게 한다. 종료 신호에 응답하지 않는 프로세스는 kill 후 wait로 회수한다.

Agent E2E는 `AGENT_E2E_DATABASE_URL`을 주면 외부 테스트 DB에 임시 schema를 생성하고 종료 시 삭제합니다. 해당 사용자는 schema 생성 권한이 필요합니다. Windows 로컬에서는 변수를 생략하면 기존 native PostgreSQL을 띄우는 방식을 유지합니다. 테스트 경로/바이너리는 [Agent QA](../agents/QA.md)를 참고하세요.

## 산출물

- `frontend-dist`: 정적 프론트엔드 빌드.
- `agent-test-results`: JUnit XML, 테스트 프로세스 로그; 실패 시에도 업로드합니다.
- `image-<component>`: 이미지 태그·digest·발행 여부 JSON.
- `helm-chart-<version>`: `.tgz`, `.tgz.sha256`, `rendered.yaml`, `release-manifest.json`.

패키징은 임시 chart 디렉터리에 이미지 metadata를 주입하므로 저장소의 values를 수정하지 않습니다. 7개 이미지 기록이 빠지거나 참조/체크섬 형식이 틀리면 패키징에 실패합니다. 발행된 이미지는 `repository@sha256:...`로 고정합니다. 검토용 패키지는 `deployable_images: false`이며 존재하지 않는 레지스트리 digest를 넣지 않습니다. PR 패키지를 그대로 설치할 용도가 아닙니다.

## 릴리스 방법

1. [Chart.yaml](../charts/gpu-ops-advisor/Chart.yaml)의 `version`/`appVersion`을 제품 릴리스 버전으로 변경하고 관련 검증을 수행합니다. [현재 협업 방식](team-development.md)에 따라 승인 후 main에 직접 push하거나 검증된 PR을 병합하고, 해당 main 커밋의 CI 성공을 확인합니다.
2. main에 반영한 커밋에 동일 버전의 태그(예: `v1.3.0`)를 push합니다. 태그와 chart version이 다르면 시작 단계에서 실패합니다.
3. 전체 테스트·7개 이미지 빌드/발행이 통과하면 chart artifact와 OCI chart가 만들어집니다. OCI chart 발행은 이 단계 이후에만 수행합니다.
4. [설치 안내](../charts/gpu-ops-advisor/README.md)에 따라 Secret·운영 프로필·PVC를 준비하고 패키지를 설치합니다.

GitHub Actions의 `GITHUB_TOKEN`으로 packages 쓰기 권한을 사용하며 별도 PAT는 필요하지 않습니다. 조직의 package 생성 제한이 있거나 기존 GHCR package가 다른 저장소에 연결되어 있다면 이 저장소에 package 쓰기 권한을 부여해야 합니다. Kubernetes 접속 정보는 CI에 필요하지 않고 자동 클러스터 배포는 포함하지 않습니다.

이전의 존재하지 않는 agent/aggregator/scheduler/TypeDB 이미지 경로와 예전 chart 작업을 제거했습니다. 자동 버전 수정/커밋 워크플로도 제거하고 버전 태그 하나를 릴리스 진입점으로 사용합니다. 별도 i18n placeholder 대신 문서 링크 검증을 공통 테스트에 포함했습니다.

구성 기준: [GitHub reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows), [Helm charts](https://helm.sh/docs/topics/charts/), [Helm OCI registries](https://helm.sh/docs/topics/registries/).
