# CI와 Helm 릴리스

현재 폴더 구조의 배포 단위는 `backend`, `frontend`, `job-controller`, `incident`, `rcca-agent`, `ops-agent`, `grafana-mcp`입니다. 이미지 목록·Dockerfile·빌드 context는 [components.json](../tools/ci/components.json)에서 관리합니다. 공통 Go/Python 코드는 라이브러리이며 별도 이미지로 발행하지 않습니다. PostgreSQL은 Helm이 공식 이미지를 사용합니다.

[로컬 검증 기록](ci-qa.md) · [Helm 설치 구성](../charts/gpu-ops-advisor/README.md)

## 실행 흐름

`ci.yml` → `tests.yml` → `container-images.yml` → `helm-chart.yml` → `CI required` 순서입니다. 마지막 `CI required`는 실패·취소·건너뛴 필수 단계를 모두 실패로 처리합니다. Branch protection에서 이 check를 필수로 등록하면 됩니다. 문서 변경도 같은 검증을 거쳐 조건별 skip 때문에 필수 check가 대기하지 않습니다.

| 이벤트 | 테스트 / 이미지 빌드 | GHCR 이미지 | Helm artifact | OCI chart |
| --- | --- | --- | --- | --- |
| Pull request | 실행 | 미발행 | 검토용 `1.3.0-ci.<run>.<attempt>` | 미발행 |
| main push 또는 PR merge | 실행 | `sha-<full-commit-sha>` | 동일 CI 버전, 이미지 digest 고정 | CI 버전으로 발행 |
| `v1.3.0` 버전 태그 push | 실행 | `v1.3.0` | `1.3.0`, 이미지 digest 고정 | 발행 |
| workflow_dispatch | 실행 | 미발행 | 검토용 CI 버전 | 미발행 |

이미지 위치: `ghcr.io/<lowercase-github-owner>/gpu-ops-advisor-<component>:<tag>`.
Chart 위치: `oci://ghcr.io/<lowercase-github-owner>/charts/gpu-ops-advisor`.

`main`의 성공한 실행은 이미지와 Helm chart를 모두 GitHub Packages에 발행합니다. chart는 `1.3.0-ci.<run>.<attempt>` 형태의 고유 버전을 쓰며, 버전 태그 실행은 `1.3.0` 같은 정식 버전을 씁니다. Actions의 `helm-chart-<version>` 다운로드 산출물도 계속 유지합니다. OCI에서 CI 버전을 받을 때는 `helm pull ... --version 1.3.0-ci.<run>.<attempt>`처럼 해당 버전을 지정합니다.

`frontend`만 `frontend/`를 Docker context로 쓰고, Go 서비스·Agent·MCP는 저장소 루트를 사용합니다. Linux/amd64 이미지 7개를 각각 빌드합니다. PR·수동 실행도 OCI image exporter로 실제 이미지 생성까지 검사하지만 레지스트리에 올리지는 않습니다.

BuildKit의 GitHub Actions 캐시는 빌드 가속용이다. `cache-to`의 `ignore-error=true`로 캐시 업로드 실패만 허용한다. 실제 이미지 빌드·OCI 출력/레지스트리 발행·digest 기록·chart 패키징 실패는 계속 CI 실패로 처리한다. 옵션 의미는 [Docker 공식 문서](https://docs.docker.com/build/cache/backends/gha/)를 따른다.

## 검증 범위

- Go: `shared`, `backend`, `job-controller`, `incident` 각각 vet·race 단위 테스트·빌드. Backend/JC/Incident는 PostgreSQL service container에 실제 DB E2E를 수행합니다.
- Python: 공통 패키지·두 Worker Ruff 검사 및 최소 단위/생명주기 테스트. PostgreSQL service container, 실제 Go JC, 실제 Worker, NAT, 체크섬 검증한 공식 Grafana MCP 1.4.2 프로세스로 E2E를 실행합니다. Grafana datasource 응답과 LLM 응답만 fixture이며 운영 외부 서비스는 호출하지 않습니다.
- Frontend: Prettier·Vitest·TypeScript/Vite build.
- Helm: strict lint, 실제 manifest 계약 검사, 기본/외부 DB·PVC·Ingress·Secret·digest 변형, 패키지 재렌더링, 릴리스 metadata 테스트.
- Actions: actionlint 1.7.11. 문서: 저장소 내부 링크·파일명 대소문자 검사.

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
