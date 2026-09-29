# 사내 모델 인증과 실제 호출

API 키는 LiteLLM 등 모델 서버가 발급한 인증 값이고, Kubernetes Secret은 그 값을 저장·주입하는 리소스다. 키 값과 Secret 리소스 이름은 다르다. GUI는 키 원문 대신 `env:LLM_API_KEY` 참조만 저장한다. 현재 지원하는 배포 키는 하나이며 Backend와 RCA·보고서 Worker가 공유한다.

## 한 번 준비할 배포 설정

기본 namespace `gpu-ops-advisor`의 **Bash 터미널**에서 키를 숨김 입력한다. 키를 명령 이력이나 파일에 적지 않는다. 기존에 같은 Secret을 다른 용도로 사용하고 있다면 별도 이름을 선택한다.

```bash
read -rsp 'LiteLLM API key: ' MODEL_KEY; printf '\n'
printf '%s' "$MODEL_KEY" | kubectl -n gpu-ops-advisor create secret generic gpu-ops-advisor-llm \
  --from-file=LLM_API_KEY=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
unset MODEL_KEY
```

기존 배포 values에 아래 항목을 병합한다. 예시 주소/IP는 실제 모델 서버의 값으로 바꾼다. URL에 포트를 적지 않았으면 허용 호스트에도 기본 포트를 추가하지 않는다. 사설 DNS는 Backend Pod에서 조회되는 IP를 CIDR로 지정하며 여러 값은 쉼표로 구분한다.

```yaml
llm:
  existingSecret: gpu-ops-advisor-llm
  apiKeyKey: LLM_API_KEY
components:
  backend:
    env:
      DSX_MODEL_HOSTS: "llm.example.internal"
      DSX_MODEL_CIDRS: "192.168.20.171/32" # 실제 서버 IP로 교체
```

성공한 CI의 Backend·Frontend·두 Worker 이미지와 해당 chart를 함께 적용한다. 기존 DB·보고서 PVC 설정은 보존하고 [설치](helm-install.md)·[기존 설치 업그레이드](helm-upgrade-existing.md)의 해당 환경 절차를 따른다. 이 변경은 스키마 migration 없이 빈 모델 라우팅 행만 없을 때 생성하며 기존 설정은 유지한다. 이전 앱/chart로 복귀해도 프로필 데이터는 남지만 이전 Worker는 GUI 라우팅을 사용하지 않으므로 복구 시 기존 LLM 환경 설정을 확인한다.

## 화면에서 확인할 흐름

1. 모델 등록/편집에서 API 기본 주소와 모델명을 입력하고 **배포된 API 키 사용**을 선택한다. 이전에 인증 없이 저장한 모델은 이 값을 바꿔 저장해야 한다.
2. **연결 검사**를 실행한다. 짧은 실제 추론(최대 128 출력 토큰)을 요청하므로 과금/사용량이 발생할 수 있다. `transport.http_status=200`, `schema.status=ok`가 답변 수신 성공이다. 검사에는 30초 제한이 있으며 시간 초과는 원격 추론 종료 확인을 뜻하지 않는다.
3. **질의·Agent별 모델 지정**에서 RCA/보고서에 사용할 모델 revision을 저장한다. 모델 편집으로 revision이 바뀌면 사용할 새 revision을 다시 선택한다. 이미 접수된 작업은 이전 revision을 유지한다.
4. 새 보고서 또는 실제 Incident에서 생성한 RCA 작업을 실행해 JC의 succeeded·published_result_id와 저장 결과의 LLM 상태를 확인한다. 결정적 분석으로 LLM을 생략한 작업은 추론 성공 증거가 아니다. 연결 검사 성공만으로 실제 관측/분석 품질 검증까지 통과한 것은 아니다.

등록 시 MODEL_ENDPOINT_NOT_ALLOWED는 호스트 불일치, 검사 중 destination_not_allowed는 DNS IP 허용 실패다. MODEL_AUTH_NOT_CONFIGURED는 Backend에 키가 없는 상태다. authentication_failed/401은 인증 실패, permission_denied/403은 권한 부족, model_or_endpoint_not_found/404는 모델/경로 확인이 필요하다. invalid_completion은 정상적인 비어 있지 않은 답변을 받지 못한 상태다. 키나 서버의 원문 오류 본문은 UI·감사에 반환하지 않는다.

키 변경은 환경변수로 주입되므로 Backend와 두 Worker가 새 Secret 값으로 다시 시작되어야 한다. GUI 라우팅이 없는 기존 작업은 배포의 LLM_BASE_URL·LLM_MODEL·LLM_API_KEY를 계속 사용한다.
