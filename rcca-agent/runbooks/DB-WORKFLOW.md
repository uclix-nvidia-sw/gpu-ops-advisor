# XID·SXID Runbook 작성과 Knowledge DB 등록

2026-09-28. 다른 PC에서 대화 기록 없이 이어가기 위한 문서다. **XID 173건·SXID 93건과 일반 1건, 총 267건이며 [전체 코드 목록](CATALOG.md)을 따른다.** 기존 Backend API로 초안을 등록하고 검토·발행한다. 문헌 미정의·출처 차이는 개별 항목에 보존했다. 운영 적용에는 환경별 parser/query/compatibility 검증이 필요하다.

## 1. 완료된 단계와 남은 경계

- 콘텐츠: 최초 세 JSON의 지침 보강 후 코드별 263건을 추가했다. 일반 조사까지 파일은 267건이다.
- 실행 의미: 모든 초안은 `investigation_only: true`다. 조건이 맞더라도 원인 supported 판정이나 기존 증거만으로 조기 종료하는 근거로 쓰지 않는다. 조사 지침은 최종 Synthesis에 전달한다. 현재 workflow는 조사용 콘텐츠의 recommendations를 최종 eligible 조치 목록으로 발행하지 않는다.
- DB 경로: JSON은 작성 원본이다. 실행 원본은 기존 `knowledge_revisions`의 승인·발행된 revision이다. Backend가 생성·갱신·상태 전이를 소유한다. 직접 SQL 적재, 새 테이블, migration, 자동 seed는 추가하지 않았다.
- 실제 검증: 격리 PostgreSQL에서 Backend 등록·검토·발행, JC revision 고정, 실제 RCA Worker/NAT/MCP 수집·Synthesis·결과 공개를 확인했다. 그래프 데이터와 모델 응답은 fixture다. 테스트 DB는 실행 후 정리하며 운영 DB에는 등록하지 않았다.
- 저장소 JSON의 compatibility는 여전히 비어 있다. 실제 배포 조건을 만들거나 검증했다고 주장하지 않으며 초안 저장은 가능하지만 승인·발행은 차단한다.

### 기존 DB와의 대응

Runbook 267건은 기존 `knowledge_revisions`에 저장하는 논리 지식 267건이다. 수정 이력이 쌓이면 각 지식의 revision 행이 늘어난다. [기존 migration](../../shared/migrations/001_backend.sql)의 테이블·컬럼·제약은 변경하지 않았다.

| 기존 필드 | 저장하는 값 |
|---|---|
| `knowledge_key` | `RB-XID-79`, `RB-XID-48-63-64`, `RB-SXID-11001` |
| `knowledge_id`, `revision`, `id` | 지식의 고정 ID, 수정 차수, 해당 revision의 고유 ID |
| `kind`, `state` | `runbook`, 기존 draft/in_review/reviewed/published/retired 상태 |
| `content` JSONB | `gpu-rca-runbook/1.0`의 코드 검색 정보·조사 계획·지침·출처 |
| `compatibility` JSONB | 검수한 환경별 적용 조건. 현재 저장소 초안은 `{}` |
| `content_hash`, `reviewed_content_hash` | 기존 본문 무결성·검토 후 변경 방지 계약 |

R코드·D코드도 기존 콘텐츠/실행 프로필의 식별자이며 테이블을 추가하지 않는다. Backend의 기존 JSON 검증과 `search.codes` 조회를 사용한다. DB 스키마 호환성과 운영 적용 가능성은 별개이며, 빈 compatibility 초안은 저장할 수 있어도 승인·발행할 수 없다.

## 2. 출처를 사용하는 기준

기존 [근거자료 카탈로그](../../docs/specs/rca-agent/references/runbook-source-catalog.md)와 [Fleet·GPUd 오류 카탈로그](../../docs/specs/rca-agent/references/fleet-gpud-error-catalog.md)를 먼저 읽는다. Fleet 소스가 없는 것이 아니다. 기존 분석 commit은 Fleet `84f99beef3e633071ad0998b10629b01fb294eaf`, GPUd `9606bb8f6813fdd944cc9a349566e35075917805`다. 이번 추가 GPUd 대조는 `0857190a63e3a01ee45dcaaae715e9f063f9eb5f`를 고정했다. 이들 commit과 실제 Fleet image/source revision이 같은지는 미확인이다.

| 출처 | 사용할 정보 | 혼동하지 않을 정보 |
|---|---|---|
| Fleet·GPUd 정적 정의 | 코드 의미·기본 event_type·기본 action·주석의 조건 | 현재 health·현재 action은 이력과 평가 로직의 결과일 수 있음 |
| NVIDIA Xid Catalog | 적용 제품·발생 조건·즉시/조사 분류·상세 절차 | GPUd repair enum과 별도 체계. Ampere 이상과 Volta 이하 경로 구분 |
| Fabric Manager 가이드 | SXID 분류·영향·복구 맥락 | 플랫폼·FM 버전·bare metal/VM·포트/partition 조건 필요 |
| 사건별 관측 | 실제 로그·메트릭·장비·시각·조치 기록 | 문헌이나 정적 action이 관측·실행 증거를 대신하지 않음 |

XID 79는 PCIe·장치·드라이버 후보를 구분할 근거를 요청한다. XID 48은 같은 장치의 63/64 동반·영향 영역·모델별 증거를 확인한다. SXID 11001은 Fatal 이벤트 분류와 전체 시스템 영향, 정적 재부팅/점검 목록과 재발 조건을 구분한다. 주석의 조건을 action 배열만으로 대체하지 않는다. 오류별 원문 위치와 확인 날짜는 각 JSON의 `content.sources`를 따른다.

문헌 URL은 `content.sources`에 넣는다. 최상위 `source_refs`는 DB evidence ID이며 common Knowledge에 사건 근거를 연결하지 않는다. 기존 소스 표 전체를 복제하거나 미확인 임계값을 새로 만들지 않는다.

## 3. 수집과 판단의 현재 지원 범위

| 단계 | 현재 코드 | 추가로 필요한 연결 |
|---|---|---|
| 코드 검색 | `xid:N`/`sxid:N` 분리, component·reason 단서; Backend `code` 필터도 `search.codes` 검색 | 실제 Fleet 버전의 parser·상태 평가 경로 대조 |
| 수집 계획 | D09 원본 로그, D05 상태, D02 선택 사용률 | PCIe/AER·ECC·FM 포트·토폴로지 등 실제 producer/query binding |
| 조건 평가 | 등록 문자열 fact의 `field/equals`, 정확한 compatibility 값 | 동반 코드·조치 전후·재발 시간 조건, 상세 decoder |
| 분석 | 코드 충분성, 제한된 재조사, 지침/한계를 Synthesis에 전달 | 실제 LLM endpoint·분석 품질 검수 |
| 결과 | 근거·후보 저장과 JC 공개; 조사용 콘텐츠의 원인 승격 금지 | 오류 확인·원인·조치 적합성·회복의 의미 검증 확대 |

`analysis_guidance`는 실행된 검사 결과가 아니다. 로그를 못 읽었으면 해당 오류가 없다고 판단하지 않는다. 기존 parser는 검증된 `error_code` fact를 생성하지 않으며 현재 초안은 그 공백을 숨기지 않는다. R코드는 조사 목적, D코드는 등록 쿼리다. 세부 지표가 필요하다고 임의의 D코드를 생성하지 않는다.

## 4. 검증 책임

| 위치 | 검사 |
|---|---|
| [Backend 검증기](../../backend/internal/api/runbook.go) | v1 구조·허용 필드·조건·출처·조사 계획·호환성 값 형식. 생성/PATCH 시 초안 검증, approve/publish 시 빈 compatibility 차단 |
| [관리 CLI](../src/rcca_agent/runbook_admin.py) | 기존 Python v1 검증기를 사용하고 지정한 프로필의 쿼리 등록 및 procedure들의 허용 query 집합을 확인. 승인/발행 전 DB 본문 재검사 |
| [RCA 검증기](../src/rcca_agent/runbook_contract.py)와 workflow | claim에 고정된 실제 프로필·선택 procedure 허용 목록, revision/hash·scope·실제 관측과 적용 조건 검사 |
| 운영 검토 | compatibility 값·문헌 조건·실제 생산자·수집 범위가 맞는지 확인. 형식 검사 성공은 운영 검증이 아님 |

Backend는 Worker별 query registry를 소유하지 않으므로 등록 여부를 판정하지 않는다. CLI의 허용 query 합집합 검사는 개별 procedure 적합성을 보증하지 않으며 Worker가 다시 검사한다. 기존 schema 없는 legacy 지식은 기존 경로를 유지하고 명시된 미지원 schema는 거부한다. Go와 Python의 구조 검증 변경 시 동일한 JSON을 사용하는 양쪽 테스트를 함께 갱신한다.

## 5. 다른 PC의 등록 절차

Python 3.12 환경과 설치 방법은 [Agent 안내](../../agents/README.md)를 따른다. 저장소 루트에서 아래 명령을 실행한다. Backend 주소는 실제 승인된 대상의 `/api/v1`까지 명시하며 자동 선택하지 않는다. 아래 `127.0.0.1:8080`은 사용자가 준비한 개발 Backend 예시다. 운영 환경에 개발 seed 스크립트를 실행하지 않는다.

### 폴더별 일괄 초안 등록

폴더는 `xid/`(173건), `sxid/`(93건), 상위의 일반 조사 JSON(1건)으로 구분한다. [일괄 등록 Python](../src/rcca_agent/runbook_import.py)은 하위 폴더의 `RB-*.json`을 모두 읽는다. 전체 검증이 끝난 뒤 기존 Backend API로 draft만 등록한다. DB 직접 SQL·자동 승인·발행은 없다.

```sh
# 전체 267건 형식 검사. 서버 접속/쓰기 없음.
python -m rcca_agent.runbook_import rcca-agent/runbooks --profile agents/config.example.json --dry-run

# 승인된 개발 Backend에 전체 초안 등록. 주소는 실제 대상에 맞게 지정.
python -m rcca_agent.runbook_import rcca-agent/runbooks --profile agents/config.example.json --backend http://127.0.0.1:8080/api/v1 --batch-key xid-sxid-20260928 --receipts .local/runbook-import-20260928
```

XID만 등록하려면 입력 폴더를 `rcca-agent/runbooks/xid`, SXID만이면 `rcca-agent/runbooks/sxid`로 바꾼다. 파일마다 `<batch-key>:<knowledge_key>`를 멱등 키로 사용한다. 성공 응답은 receipts 폴더에 파일별로 저장하며 개별 관리 CLI의 검토 명령 입력으로도 사용할 수 있다.

중단 후에는 **같은 대상·입력·batch key·receipts 경로**로 재실행한다. 기록된 성공 항목은 API 재호출 없이 건너뛴다. `resumed`는 저장된 응답 재사용 건수이며 현재 DB 상태를 다시 검사했다는 뜻은 아니다. 본문뿐 아니라 compatibility·대상 URL·revision 대상이 달라져도 receipt 불일치로 중단한다. 응답 유실 때에는 같은 요청 키로 재전송해 Backend receipt를 복구한다.

429 응답은 `Retry-After`를 따라 최대 3회 대기·재시도한다. 그 외 HTTP/통신/저장 오류는 중단하며 이미 등록한 초안을 삭제하지 않는다. Backend 기본 변경 요청 한도는 분당 120건이므로 전체 등록에 수 분이 걸릴 수 있다.

기존 knowledge_key는 다른 ID로 중복 생성하지 않는다. 새 revision이 필요하면 아래와 같은 JSON 파일을 작성해 `--knowledge-ids .local/existing-runbook-ids.json`을 추가하고 **새 batch key와 새 receipts 폴더**를 사용한다. 매핑에 없는 키는 신규 지식으로 생성한다. 기존 ID는 해당 Backend의 Knowledge API에서 확인한다.

```json
{"RB-XID-79": "기존 knowledge_id UUID"}
```

receipts는 입력 폴더 밖에 둔다. 폴더 이동은 작성 파일 정리일 뿐 knowledge_key와 DB ID를 바꾸지 않는다. 전체 코드·출처별 제한은 [CATALOG](CATALOG.md)를 따른다.

### 초안 검사와 등록

```sh
python -m rcca_agent.runbook_admin check rcca-agent/runbooks/xid/RB-XID-79.json --profile agents/config.example.json
python -m rcca_agent.runbook_admin draft rcca-agent/runbooks/xid/RB-XID-79.json --profile agents/config.example.json --backend http://127.0.0.1:8080/api/v1 --request-key xid79-draft-20260928 --output .local/xid79-draft.json
```

`.local`을 먼저 만든다. 다른 두 오류 파일에도 별도 request key를 사용한다. 응답 파일에는 knowledge ID·revision ID·revision·version·state·content hash를 저장한다. HTTP 오류/통신 실패 시 성공으로 처리하지 않는다. 응답 유실 시 같은 입력과 같은 key로 재전송한다. 같은 key에 다른 본문을 보내면 충돌한다.

기존 knowledge가 있으면 첫 생성 대신 `--knowledge-id <기존 knowledge_id>`를 붙여 새 draft revision을 만든다. 발행본을 덮어쓰지 않는다. 같은 knowledge_key를 다른 ID로 중복 생성하면 Backend의 유일 제약으로 거부된다. 기존 revision 확인은 Backend 목록 API에서 `kind=runbook`, `state=draft` 등 상태별로 조회한다.

### 적용 조건 확정 후 검토·발행

저장소 초안을 별도 파일로 복사해 검수한 compatibility를 채운다. 테스트 cluster 값을 운영 파일에 복사하지 않는다. `check ... --runtime`으로 실행 형식 검사를 하고, 앞의 `draft ... --knowledge-id`로 새 revision을 등록한다. 아래에서는 그 응답을 `.local/xid79-bound.json`으로 저장했다고 가정한다.

```sh
python -m rcca_agent.runbook_admin request .local/xid79-bound.json --profile agents/config.example.json --backend http://127.0.0.1:8080/api/v1 --request-key xid79-request-r2 --comment "대상과 수집 계약 검토 요청" --output .local/xid79-requested.json
python -m rcca_agent.runbook_admin approve .local/xid79-requested.json --profile agents/config.example.json --backend http://127.0.0.1:8080/api/v1 --request-key xid79-approve-r2 --comment "검토한 환경과 증거를 기재" --output .local/xid79-reviewed.json
python -m rcca_agent.runbook_admin publish .local/xid79-reviewed.json --profile agents/config.example.json --backend http://127.0.0.1:8080/api/v1 --request-key xid79-publish-r2 --output .local/xid79-published.json
```

각 명령은 별도로 실행한다. 예시 comment를 검토 증거로 간주하지 않는다. CLI는 자동 승인·자동 발행하지 않는다. 상태 변경에는 직전 응답의 version을 If-Match로 보내므로 다른 수정이 끼어들면 중단한다. 검토할 본문 hash가 바뀌면 새 응답을 확인해야 한다. 저장소 초안의 빈 compatibility 그대로는 approve/publish가 실패하는 것이 정상이다.

조회: `GET /api/v1/knowledge?kind=runbook&state=published&code=xid%3A79`. SXID는 `code=sxid%3A11001`로 조회하며 서로 섞이지 않는다. API에 저장돼도 JC claim에 발행 revision이 고정되고 Worker의 적용 검사를 통과해야 조사에 사용된다. Helm upgrade는 콘텐츠 발행을 수행하지 않는다.

### 수정과 회수

검토 중 수정 요청은 `request_changes <직전 응답 파일> --comment ...`를 사용한다. 발행본 회수는 `retire <발행 응답 파일> --comment ...`이며 두 경우 모두 backend/profile/request-key를 명시한다. retire 후 신규 선택에서는 제외되지만 실행 중인 claim의 고정 참조와 과거 결과는 보존한다. 수정은 새로운 draft revision에서 진행하고 삭제·과거 hash 변경으로 복구하지 않는다.

## 6. 재현 검사와 인수인계

단위: `python -m pytest -c agents/pytest.ini agents/tests -m "not e2e" -q` 및 Backend의 `go vet ./...`, `go test -race ./...`, `go build ./...`.

통합: [CI](../../.github/workflows/tests.yml)의 Agent job은 Backend·JC·Incident 바이너리를 빌드한다. `RUN_AGENT_E2E=1`, 격리 PostgreSQL, 공식 Grafana MCP로 전체 Agent 검사를 실행한다. Backend 바이너리 기본 위치는 `.local/backend-e2e`(Windows는 `.exe`)이며 `BACKEND_BINARY`로 지정할 수 있다. Windows 실행기는 [test.ps1](../../agents/scripts/test.ps1)이다. PostgreSQL scratch 디렉터리는 Windows에서 ASCII 경로를 권장한다.

신규 E2E는 세 JSON의 CLI 등록·같은 키 재전송·빈 호환성 승인 거부·새 revision·명시적 검토/발행·namespace 검색·실제 Worker의 지침 소비·원인 승격 방지·폐기를 검사한다. 사건 입력, 관측 및 모델은 fixture이며 운영 Fleet parser가 동작한다는 증명이 아니다. 기존 실제 Incident webhook 회귀는 별도 사례로 유지한다.

최신 실행 결과는 [Agent QA](../../agents/QA.md), [Backend QA](../../backend/QA.md)를 따른다. 이번 개발은 사용자 지시에 따라 다른 세션과 조율하지 않는다. 다른 PC에서는 [HANDOFF](../HANDOFF.md)와 `git status`, `git log`를 먼저 확인한다. 미커밋 파일은 원격 clone에 포함되지 않으며 commit/push/배포는 별도 단계다.

다음 입력: 실제 Fleet image와 source revision, 비밀을 제거한 원본 로그, 노드/GPU/NVSwitch 식별 연결, Grafana 수집 라벨·기간·완전성, 설치 플랫폼/드라이버/FM 버전. 이를 확보하면 query/parser와 세부 판정을 연결하고 운영 compatibility를 검토한다.
