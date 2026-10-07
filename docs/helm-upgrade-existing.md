# 기존 설치의 Agent 기동 수정과 이름 변경

## 종류별 Agent 3개 배포 전환 — 2026-10-08

[values-independent-agents.yaml](../charts/gpu-ops-advisor/values-independent-agents.yaml)은 RCA 3개·Ops 3개, Worker당 1개, 종류별 3개·전체 6개를 위한 선택적 예시다. 기본 설치의 1개씩 구성·기존 PVC는 자동으로 바뀌지 않는다. 배포 승인·성공 CI 이미지와 설정 준비 전에는 운영에 적용하지 않는다.

- 기존 환경의 `configuration.jobController` 전체 override가 있으면 실행 프로필·revision·예산·lease를 보존하고 capacity 값만 맞춘다. 예시의 개발 기본값으로 교체하지 않는다. `JC_APPLY_CONFIG=false`인 환경은 새 설정/실행 정책 revision을 DB에 적용할 운영 절차를 준비한다.
- 여러 Ops Pod는 같은 보고서 파일을 보존할 수 있는 검증된 ReadWriteMany PVC를 사용한다. `artifacts.persistence.existingClaim`과 `existingClaimAccessMode: ReadWriteMany`를 명시한다. 이 값은 운영자가 확인한 접근 모드의 선언이며 Helm 렌더링이 실제 PVC나 StorageClass를 검증하는 것은 아니다. 새 저장소 서비스 설치나 기존 PVC 변경은 예시에 포함되지 않는다.
- 이미 외부 RWX claim을 쓰면 이름을 보존한다. **chart가 관리 중인 기존 RWO PVC를 existingClaim으로만 바꾸면 PVC 리소스가 릴리스에서 빠져 삭제될 수 있다.** 기존 DB·파일을 백업하고, 기존 PVC를 계속 보존할 중간 릴리스/별도 보존 절차와 새 RWX claim으로의 파일 복사를 검토·검증한 다음 전환한다. 기존 PVC의 access mode를 제자리 수정하거나 삭제 후 재생성하지 않는다. 저장소 전환 승인이 없으면 기존 설치에 이 예시를 적용하지 않는다.
- 새 JC 코드·설정을 같은 버전으로 반영한 후 두 Agent를 확장한다. 기본 UUID Worker 신원을 유지하며 정적 WORKER_ID를 복제본끼리 공유하지 않는다. 이 예시는 Helm 배포용이며 정적 WORKER_ID를 둔 기존 Compose 구성을 그대로 scale하는 절차가 아니다.
- 검수는 Pod 수뿐 아니라 종류별 3건 실행·네 번째 대기, 상대 종류가 멈춰도 자기 배분 진행, 실패한 시도 반환·늦은 결과 거부, 보고서 저장/다시 읽기/다운로드를 확인한다. 실제 Dynamo의 대기 요청·지연과 Mimir/DB 부하는 별도 측정한다. 슬롯 분리는 공유 모델 서버 자원 분리를 뜻하지 않는다.
- 축소/롤백은 먼저 신규 생산·claim을 제어하고 진행 작업 종료를 확인한 뒤 이전 복제 수·JC 설정·호환 코드로 맞춘다. 한도 축소만으로 실행 중 작업을 강제 종료하지 않지만 Deployment 축소는 Pod 종료를 유발할 수 있다. 이미 발행된 결과와 기존/새 PVC를 보존한다.

### Helm 관리 RWO 보고서 PVC를 RWX로 옮기는 순서

2026-10-08 운영자가 제공한 조회에서 `gpu-ops-artifacts`는 release `gpu-ops`가 관리하며 keep annotation이 없었다. StorageClass `ontap-nas-economy-sc`의 provisioner는 `csi.trident.netapp.io`, backendType은 `ontap-nas-economy`이고, 실제 PV의 protocol은 `file`, reclaim policy는 `Delete`였다. 이 드라이버는 [RWX를 지원](https://docs.netapp.com/us-en/trident-2410/trident-use/ontap-nas.html)하지만 새 claim의 Bound·다중 노드 mount·UID/GID 10001 쓰기는 아직 확인하지 않았다. PostgreSQL PVC `data-gpu-ops-postgres-0`은 그대로 유지한다. 이미 짧은 이름을 사용하는 이 설치에 옛 이름용 `upgrade-existing-values.yaml`을 추가하지 않는다.

아래는 **해당 변경이 main에 병합되고 CI 이미지/Chart가 발행된 후**, 운영자가 승인한 배포 시간에 실행할 절차다. 로컬 렌더링 검수만으로 서버 전환이 검증된 것은 아니다. 신규 접수·자동 일정을 제어하고 진행 중 작업이 끝난 것을 확인한 뒤 백업한다. Chart는 Recreate이므로 앱 재시작에 중단 시간이 있다.

1. 기존 운영 values 사본에 JC 종류별 한도 3·전체 6·Worker당 1만 반영한다. Agent binding·모델·실행 프로필·revision·예산·Secret·저장소 이름을 보존한다. 두 Agent replicas는 1로 유지하고 `existingClaim`은 비워 기존 PVC를 계속 렌더링한다. Chart가 발행한 새 이미지 digest를 구 digest override로 가리지 않는다.
2. **보존 업그레이드:** 아래 PVC 조회를 업그레이드 전에도 실행해 기존 UID·PV 이름을 기록한다. 아래처럼 `retainOnDelete=true`로 기존 PVC에 keep annotation을 기록한다. 이것은 PVC spec·이름·데이터를 변경하지 않는다. 새 JC readiness와 capacity 설정을 확인한다. `applyJobController=false`이면 새 revision을 적용할 별도 절차가 선행되어야 한다.

```bash
# CHART_PACKAGE: 이 변경이 포함된 성공한 main CI의 .tgz
# VALUES_FILE: 위 1번에서 준비한 기존 환경 설정의 사본
helm upgrade gpu-ops "${CHART_PACKAGE:?published chart package required}" \
  --namespace gpu-ops-advisor --values "${VALUES_FILE:?prepared environment values required}" \
  --set components.rcca-agent.replicas=1,components.ops-agent.replicas=1 \
  --set artifacts.persistence.existingClaim=,artifacts.persistence.retainOnDelete=true \
  --wait --timeout 10m

kubectl -n gpu-ops-advisor get pvc gpu-ops-artifacts \
  -o 'custom-columns=NAME:.metadata.name,UID:.metadata.uid,PV:.spec.volumeName,KEEP:.metadata.annotations.helm\.sh/resource-policy'
```

3. PVC UID·PV가 전과 같고 keep이 기록됐는지, **성공한 Helm revision의 manifest에도 같은 PVC와 keep이 있는지** 확인한다. [Helm keep](https://helm.sh/docs/howto/charts_tips_and_tricks/#tell-helm-not-to-uninstall-a-resource)은 자동 파일 복사를 뜻하지 않는다. `existingClaim` 전환과 keep 설정을 처음부터 한 번에 적용하면 기존 PVC manifest가 생성되지 않으므로 이 보존 단계를 건너뛰지 않는다. 전환 중 실제 PV reclaim policy도 운영 절차로 `Retain`으로 바꾸고 확인해 이중으로 보호한다. StorageClass 전체 정책이나 DB PV는 변경하지 않는다.
4. 같은 StorageClass에 별도 RWX claim(예: `gpu-ops-artifacts-rwx`, 최소 기존 10Gi와 실제 사용량 고려)을 만든다. `Bound`와 다중 노드 쓰기·읽기·UID/GID 10001 권한을 시험한다. 새 PV도 전환 기간에는 Retain으로 보호한다. 기존 RWO claim/PV의 accessModes는 제자리 변경하지 않는다.
5. 보고서 신규 접수를 멈추고 대기·실행 작업이 없는 상태에서 Ops를 정지한다. 기존 claim을 readOnly로, 새 claim을 쓰기 가능하게 연결한 임시 복사 Pod로 모든 보고서 파일의 상대 경로를 그대로 복사한다. 원본 파일을 지우지 않으며 파일 목록·크기·해시를 비교한다. 새 파일도 Worker UID/GID로 읽고 쓸 수 있어야 한다. 복사 Pod를 종료한 뒤 다음 단계로 간다.
6. 운영 values에 `existingClaim: gpu-ops-artifacts-rwx`, `existingClaimAccessMode: ReadWriteMany`, 양 Agent replicas=3을 반영하고 같은 새 Chart로 두 번째 업그레이드한다. JC 한도는 3/3/6과 Worker당 1을 유지한다. 보존된 기존 RWO PVC는 Helm 관리에서 벗어나므로 수동 삭제/자동 정리 대상에 넣지 않는다.
7. 기존 보고서 열기·다운로드, 새 보고서 발행, RCA/report 각각 3건과 네 번째 대기를 확인한다. 실패하면 신규 접수를 중지하고 원인·추가 생성 파일을 보존한다. 단순 Helm rollback은 파일을 되돌리지 않으므로 새 RWX의 보고서 파일을 잃지 않도록 복구한다. 현재 RWX에 연결한 채 replicas=1과 합당한 한도로 줄이는 방식도 검토하며 이전 PVC로의 복귀는 파일 동기화 후에만 한다.

`retainOnDelete` 기본값은 false이며 **명시적으로 켠 설치만** 보존 정책을 받는다. 이 절차의 실클러스터 실행·복사·복구 검증은 운영자 배포 단계로 남아 있다.

## Runbook-first 지원의 적용 순서 — 2026-10-02

로컬 변경 단계이며 운영 배포 승인은 별도다. JC 007 migration은 Worker 지원 계약 제약만 확장하며 job/snapshot/PVC를 변경하지 않는다. 적용 순서는 JC → 1.3/1.4/1.5 지원 RCA Worker → Incident 1.5 생산자 → 결과 화면이다. 기존 outbox는 원래 계약으로 전달된다. 변경된 Runbook은 Backend의 새 revision 검토·발행을 거친다.

실패 시 신규 Incident 접수를 멈추고 해당 설정·이미지를 복구한다. 이미 만들어진 1.5 작업은 지원 Worker를 유지하거나 대기시켜야 하며 구형 Worker로 강제 배분하거나 snapshot을 1.3으로 바꾸지 않는다. DB 제약 확장은 유지해도 기존 계약을 수용한다. 이전 JC/Worker로 복구하기 전에 1.5 Worker 등록·작업 상태를 확인한다. DB/PVC 삭제는 복구 절차가 아니다.

## Fleet RCA profile v3 반영 시 확인 (2026-09-30)

이번 변경에는 DB migration이 없다. 기존 DB/report PVC와 snapshot/hash를 유지한다. Agent 전체 override를 쓰는 경우 `builtin-grafana-v3`의 D05/D09 `json_target_fields`, `health_contract`, query revision과 `health_contracts`를 기존 설정에 병합한다. 기본 `loki_timestamp_is_observed_at=false`를 운영 시각 계약 검증 없이 켜지 않는다. [상세 설정](../rcca-agent/README.md#2026-09-30-fleet-rca-수집분석-보완)을 따른다.

배포는 별도 승인 후 CI 성공 이미지 digest로 RCA/Ops·Incident·Frontend를 갱신한다. 새 테스트 사건에서 실제 요청 범위/31건 같은 원본 건수/관측 참조/남은 D02 실행/R02 D08·D06 계획/보고서 공개를 확인한다. 근거 부족과 대상 매핑 미확인은 partial/blocked로 남아야 한다. 실패 시 기존 이미지와 전체 설정으로 복귀하며 DB/PVC를 재생성하지 않는다. 기존 결과는 자동 재분석하지 않는다. 운영 검수 담당자·대상·시점을 배포 전에 지정한다.

대상: release `gpu-ops`, namespace `gpu-ops-advisor`, 기존 접두사 `gpu-ops-gpu-ops-advisor`.

새 chart는 기본 접두사로 릴리스 이름만 사용한다. 앱 Deployment/Pod/Service는 `gpu-ops-ops-agent`, `gpu-ops-rcca-agent`, `gpu-ops-grafana-mcp` 등의 이름이 된다. `fullnameOverride`로 다른 접두사도 지정할 수 있다.

**기존 긴 접두사 `gpu-ops-gpu-ops-advisor`를 사용하는 설치만 [upgrade-existing-values.yaml](upgrade-existing-values.yaml)을 추가로 적용한다.** 이미 짧은 리소스 이름을 사용하는 설치에는 추가하지 않는다. 이 파일은 PostgreSQL StatefulSet/Service와 보고서 PVC의 기존 이름을 유지한다. DB Secret의 `DATABASE_URL`도 기존 `gpu-ops-gpu-ops-advisor-postgres:5432`를 그대로 사용한다. DB Pod 이름은 데이터 보존을 위해 이번 업그레이드에서는 유지한다. 새 설치는 기본값으로 `gpu-ops-postgres-0`과 `gpu-ops-postgres:5432`를 사용한다.

보고서 PVC를 유지하려고 현재 chart가 관리하는 PVC를 `existingClaim`으로만 바꾸면 chart의 PVC 리소스가 사라져 삭제될 수 있다. 이 overlay는 `nameOverride`로 동일 PVC를 계속 관리한다. 원래부터 외부 `existingClaim`을 사용했다면 그 설정을 그대로 유지한다. 기존 DB/PVC는 삭제하지 않는다.

## 업그레이드

수정 사항을 `main`에 반영하면 CI가 MCP·RCA·Ops를 포함한 이미지를 새로 빌드·발행하고, 그 실행에서 발행된 이미지 digest를 고정한 새 chart를 발행한다. 테스트나 이미지 빌드가 실패하면 chart 발행도 진행하지 않는다. 수동 `kubectl patch` 없이 새 chart 업그레이드로 기동 수정이 적용된다. 아래 파일 경로에는 **현재 설치에 사용한 환경 values**와 **수정 버전의 `.tgz`**를 지정한다. 이 과정은 앱 Deployment 이름이 바뀌므로 서비스 중단이 있다.

```bash
CHART_PACKAGE=./gpu-ops-advisor-REPLACE_NEW_VERSION.tgz
VALUES_FILE=./values.yaml
UPGRADE_VALUES=./docs/upgrade-existing-values.yaml

kubectl -n gpu-ops-advisor get sts,pvc
helm template gpu-ops "$CHART_PACKAGE" --namespace gpu-ops-advisor \
  --values "$VALUES_FILE" --values "$UPGRADE_VALUES" > rendered-upgrade.yaml

# 이름이 다른 구/신 Deployment가 동시에 작업하지 않도록 기존 앱을 먼저 정지
kubectl -n gpu-ops-advisor scale deployment \
  -l app.kubernetes.io/instance=gpu-ops --replicas=0

# 기존 앱 Pod가 종료됐는지 확인. PostgreSQL은 실행 상태를 유지한다.
kubectl -n gpu-ops-advisor get pods
# 앱 Pod가 아직 Terminating이면 종료될 때까지 기다린 후 다음 명령을 실행한다.

helm upgrade gpu-ops "$CHART_PACKAGE" --namespace gpu-ops-advisor \
  --values "$VALUES_FILE" --values "$UPGRADE_VALUES" \
  --wait --timeout 10m

kubectl -n gpu-ops-advisor get pods,pvc,svc
```

이후 업그레이드에서도 저장소 이름 override를 계속 유지한다. 모든 기존 이름을 그대로 두고 기동 수정만 적용하려면 `fullnameOverride: gpu-ops-gpu-ops-advisor`를 사용한다. 이 경우 앱 이름 변경을 위한 scale-down 절차는 필요 없다.

## 새 이미지와 chart에 포함된 MCP 수정

확인된 이벤트는 `Startup probe failed: HTTP probe failed with statuscode: 403`이다. 공식 Grafana MCP 1.4.2는 `/healthz`에도 Host 검증을 적용한다. 기존 probe가 보내는 Pod IP와 Agent가 사용하는 Service DNS가 기본 허용 목록에 없었다. startup probe 60회 × 5초 실패로 MCP가 재시작되고, Ready endpoint가 없어서 Agent도 연결에 실패했다. Grafana 토큰 오류를 의미하는 403이 아니다. [공식 HTTP 보안 설명](https://github.com/grafana/mcp-grafana/blob/v1.4.2/README.md#cli-flags-reference)을 참고한다.

MCP 이미지는 Docker 서비스 이름을 허용하고, chart는 실제 Helm Service DNS와 **`:8000` 포트까지** 포함한 허용 목록을 전달한다. 모든 MCP HTTP probe도 같은 Host 헤더를 사용한다. 새 설치와 기존 접두사를 유지하는 설치 모두 실제 공식 MCP 바이너리로 health check와 MCP 초기화·도구 목록 조회를 검증한다.

## Backend readiness 확인

기존 Backend는 C07 한도와 활성 클러스터가 모두 있어야 Ready가 되었고, 데모 seed를 끄면 두 항목을 자동 생성하지 않았다. 따라서 새 DB에 설치할 때 readiness가 503으로 유지되었다. 수정된 Backend 이미지는 데모 seed와 별도로 C07을 자동 초기화하며 기존 설정은 보존한다. 클러스터 0건은 정상 초기 상태로 허용하고 실제 분석 요청에서는 등록 여부를 계속 검사한다. 새 이미지가 포함된 chart로 업그레이드하면 추가 SQL 없이 기동된다.

Backend가 계속 Ready가 아니면 다음으로 설정 상태를 확인한다.

```bash
# 운영 데이터는 수정하지 않고 readiness에 필요한 상태만 조회
kubectl -n gpu-ops-advisor exec -i gpu-ops-gpu-ops-advisor-postgres-0 -- \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<'SQL'
SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version=2) AS schema_v2;
SELECT name, enabled, config FROM service_profiles WHERE kind='limits' AND name='C07';
SELECT id, enabled FROM cluster_registry;
SQL
```

실제 분석 대상 클러스터 ID는 환경에 맞게 등록한다. 기본 운영 한도는 자동 생성되며, 기존 C07이 비활성화되었거나 유효하지 않으면 운영 설정을 수정해야 한다. `seedDemoData: true`로 바꾸어 예제 클러스터를 운영 환경에 넣지 않는다.

## MCP 연결 확인

첨부 오류 `httpx.ConnectError: All connection attempts failed`는 Agent → MCP 연결 실패다. MCP의 비-loopback caller 인증 경고 뒤에 서버 시작 로그가 있다면 그 경고 자체가 TCP 연결 실패를 의미하지 않는다.

새 Worker Pod는 `wait-for-job-controller`와 `wait-for-grafana-mcp` init container에서 준비 상태를 기다린다. 앱 초기화 중 일시적 MCP 연결 오류도 2초부터 최대 30초 간격으로 재시도한다. 준비 전에는 JC 작업을 인수하지 않는다. 잘못된 설정이나 HTTP 401/403 같은 인증 오류는 무한 재시도로 숨기지 않는다.

```bash
kubectl -n gpu-ops-advisor logs deployment/gpu-ops-ops-agent -c wait-for-grafana-mcp
kubectl -n gpu-ops-advisor logs deployment/gpu-ops-ops-agent -c ops-agent --tail=100
kubectl -n gpu-ops-advisor logs deployment/gpu-ops-grafana-mcp --tail=100
kubectl -n gpu-ops-advisor get endpointslice \
  -l kubernetes.io/service-name=gpu-ops-grafana-mcp -o yaml
```

Endpoint가 Ready인데도 연결 실패가 계속되면 Pod 간 네트워크/NetworkPolicy/Service 라우팅을 확인한다. 준비 대기와 재시도는 네트워크 차단을 해제하지 않는다. 이름 변경 전 진단 명령은 리소스 접두사로 `gpu-ops-gpu-ops-advisor`를 사용한다.

## 설치 후 클러스터 등록

클러스터가 없는 최초 설치에서도 Backend가 Ready가 되고 화면에 “등록된 클러스터가 없습니다”가 표시된다. **클러스터 등록하기 → 연결·설정 → 데이터 연결 → 클러스터 등록**에서 실제 클러스터 ID를 입력한다. Grafana에서 조회하는 메트릭·로그의 클러스터 라벨 값과 일치해야 하며, Mimir/Loki URL이나 datasource UID는 입력하지 않는다. 등록 후 목록과 관측 범위가 갱신되며 서버 재시작은 필요 없다. 등록 전에는 분석 화면 대신 등록 안내를 표시한다.

이 흐름은 수정된 Backend와 Frontend 이미지가 모두 포함된 새 chart에 적용된다. 실제 클러스터에 데이터가 없거나 Grafana 권한이 부족한 경우 등록 자체는 가능하지만 수집 결과는 별도로 확인해야 한다.
