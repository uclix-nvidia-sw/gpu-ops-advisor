# XID·SXID Runbook 작성과 Knowledge DB 등록

> 2026-10-08 검토: 이 폴더는 DB 발행본과 별개인 작성 원본이다. 현재 원본의 D05 참조 제거와 구조 검사 통과는 오류별 내용 적합성이나 운영 발행 완료를 뜻하지 않는다. D 통합·확장 기준은 [D 매핑 설계 §7](../../docs/specs/common/d-query-mapping.md#7-rca-runbook의-통합확장-매핑)과 [개발 계획](../../docs/specs/common/d-contract-redesign-plan.md)을 따른다.

## D05 전환 후 내용 검토와 새 revision 순서

운영 DB 작업이 보류된 동안에는 아래 오프라인 검토만 수행한다. 기존 발행 revision과 과거 결과는 수정하지 않는다.

```sh
python -m rcca_agent.runbook_audit rcca-agent/runbooks --profile agents/config.example.json --authoring --review-manifest rcca-agent/runbooks/catalog-manifest.json
```

종료 코드 0은 구조 검사 통과만 뜻한다. `review.findings`는 별도 검토 항목이며 `operational_approval=not_assessed`는 그대로 유지한다. 카탈로그 분류는 저장된 문헌 검토 정보로, 최신 문헌 재검증 결과가 아니다.

1. 각 오류의 의미·적용 제품·드라이버/생산자 버전과 출처 충돌을 확인한다. `documented`도 운영 검증 완료는 아니다. Unused/구세대·정의 충돌·소스만 존재하는 코드는 현재 장비에 적용할 수 있는지 먼저 검토한다.
2. 오류별 필수 증거를 현재 D의 조회 범위와 대조한다. D09의 fact 이름 허용은 실제 fact 생성 보장이 아니다. Fleet 관측 시각, 대상, 코드와 상태 의미가 검증되지 않으면 미확정으로 남긴다. D02 사용률과 D03 메모리 사용량으로 접근 회복·ECC 정상 여부를 대체하지 않는다.
3. XID 79는 PCIe/AER 원문의 별도 수집 여부, XID 48·63·64는 동일 GPU·시간의 동반 오류와 ECC/row-remap 정보, SXID 11001은 switch/port·access/trunk·partition 관계를 검토한다. 현재 기본 D09/D02 계획만으로 이 자료가 모두 충족된다고 승인하지 않는다. 부족한 자료는 수집/해석 연결을 구현하거나 명시적인 미확정 조건으로 남긴다.
4. 대표 오류의 정상·자료 누락·다른 대상·오래된 표본·합성 오류 사례를 검증한 뒤 같은 증거 유형의 나머지 원본을 검토한다. 코드별 검토 기록 없이 267건을 일괄 승인하지 않는다.
5. DB 작업 재개 합의 후 기존 knowledge ID에 새 draft revision을 등록한다. 실제 생성된 revision 번호를 사용한다. 내용 해시와 compatibility를 검토하고 승인된 항목만 발행한 뒤 JC 고정 revision, Runbook 매칭, 실제 조회와 최종 결과를 확인한다. 구 revision의 retire는 검증 후 별도로 판단한다.

현재 오프라인 검토는 자동 발행 도구가 아니며, 이 절차는 운영 DB 변경 권한을 부여하지 않는다.

2026-10-08 로컬 원본 전수 점검: 267건 모두 구조 통과, compatibility 미설정, Fleet 관측 시각 검증 미완료로 확인했다. 저장된 manifest는 문헌 정의 187건·Unused/구세대 63건·정의 충돌 13건·소스만 확인 3건이며 일반 조사 1건은 오류 코드 manifest 대상이 아니다. 이는 267건의 오류별 문헌·실환경 검수가 끝났다는 뜻이 아니다. 후속 검토에서는 9개 원본의 조사 한계와 선택 조회 계획을 보강했다. DB 재개 후 새 초안 9건을 등록했으며 승인·발행은 수행하지 않았다. 대상과 검증 범위는 [검토 기록](REVIEW-20261008.md)을 따른다.

2026-09-28. 다른 PC에서 대화 기록 없이 이어가기 위한 문서다. **XID 173건·SXID 93건과 일반 1건, 총 267건이며 [전체 코드 목록](CATALOG.md)을 따른다.** 기존 Backend API로 초안을 등록하고 검토·발행한다. 문헌 미정의·출처 차이는 개별 항목에 보존했다. 운영 적용에는 환경별 parser/query/compatibility 검증이 필요하다.

## 1. 완료된 단계와 남은 경계

- 콘텐츠: 최초 세 JSON의 지침 보강 후 코드별 263건을 추가했다. 일반 조사까지 파일은 267건이다.
- 실행 의미: 모든 초안은 `investigation_only: true`다. 조건이 맞더라도 원인 supported 판정으로 승격하지 않는다. 현재는 모든 발행본의 계획을 한 단계에서 수집하며, 목표 달성·근거 충분성·별도 평가로 종료를 결정하지 않는다. 조사 지침은 최종 Synthesis에 전달한다. 현재 workflow는 조사용 콘텐츠의 recommendations를 최종 eligible 조치 목록으로 발행하지 않는다.
- DB 경로: JSON은 작성 원본이다. 실행 원본은 기존 `knowledge_revisions`의 승인·발행된 revision이다. Backend가 생성·갱신·상태 전이를 소유한다. 직접 SQL 적재, 새 테이블, migration, 자동 seed는 추가하지 않았다.
- 실제 검증: 격리 PostgreSQL에서 Backend 등록·검토·발행, JC revision 고정, 실제 RCA Worker/NAT/MCP 수집·Synthesis·결과 공개를 확인했다. 그래프 데이터와 모델 응답은 fixture다. 테스트 DB는 실행 후 정리하며 운영 DB에는 등록하지 않았다.
- 저장소 JSON의 compatibility는 여전히 비어 있다. 실제 배포 조건을 만들거나 검증했다고 주장하지 않으며 초안 저장은 가능하지만 승인·발행은 차단한다.

XID/SXID 작성 원본은 모두 전체 observation plan을 한 수집 단계에서 실행하고, 같은 호스트의 최근 14일 Incident 이력을 함께 보고서로 구성한다. 보고서 수집은 required_queries에 메트릭 조회가 있는 XID/SXID revision에서 켜지며 D09만 필수인 기존 발행본은 기존 경로를 쓴다. XID 79는 D09·D44·D02·D11, SXID 11001은 D09·D47·D33·D34를 사용하고, 나머지 264건의 유형별 계획은 [CATALOG](CATALOG.md#운영자-보고서-지침과-조회-계획-2026-10-22-개정)를 따른다. 새 경로에서 required_queries는 기존 계약과 기능 식별을 위한 필드이며 추가 조회 판단이나 재조사 루프에 쓰지 않는다. 보고서는 대상·로그 시각·반복 보고 구간·관련 메트릭·이력·공식 대응 지침을 제공한다. 구 발행본도 같은 단일 수집·분석·보고서 작성 흐름을 사용한다.

**Worker/UI 배포만으로 새 런북이 적용되지는 않는다.** 기존 knowledge ID와 검수된 compatibility를 유지하여 두 런북만 새 revision으로 등록·검토·발행한다. 빈 compatibility인 저장소 JSON을 그대로 발행하지 않는다. Worker/UI 배포를 먼저 완료하고 실제 실행 프로필에 각 D 조회가 허용되는지 확인한 뒤 발행한다. 신규 사건 또는 승인된 재실행에서 JC가 새 revision/hash를 고정하는지 확인한다. 기존 결과와 발행 revision은 수정하지 않는다. 문제 발생 시 새 revision을 retire하고 이전 발행 revision 선택과 이전 RCA 이미지로 복귀하는 절차를 확인한다. Ops 런북·설정·이미지는 변경하지 않는다.

XID 79·SXID 11001의 1.1 변경 hash와 이전 1.0 복원 정보는 [기존 검토 기록](incident-report-review-20261015.json)의 `decision_policy_update`에 연결했다. 이는 로컬 구조 검토이며 운영 발행 승인 기록이 아니다.

### 기존 DB와의 대응

Runbook 267건은 기존 `knowledge_revisions`에 저장하는 논리 지식 267건이다. 수정 이력이 쌓이면 각 지식의 revision 행이 늘어난다. [기존 migration](../../shared/migrations/001_backend.sql)의 테이블·컬럼·제약은 변경하지 않았다.

| 기존 필드 | 저장하는 값 |
|---|---|
| `knowledge_key` | `RB-XID-79`, `RB-XID-48-63-64`, `RB-SXID-11001` |
| `knowledge_id`, `revision`, `id` | 지식의 고정 ID, 수정 차수, 해당 revision의 고유 ID |
| `kind`, `state` | `runbook`, 기존 draft/in_review/reviewed/published/retired 상태 |
| `content` JSONB | `gpu-rca-runbook/1.0` 또는 `1.1`의 코드 검색 정보·조사 계획·지침·출처 |
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
| 수집 계획 | D09 로그와 검증 조건부 상태 fact, D02 및 오류별 선택 D 조회. D05는 현재 공통 설정에서 미등록 | PCIe/AER·ECC·FM 포트·토폴로지 등 실제 producer/query binding |
| 조건 평가 | 등록 문자열 fact의 `field/equals`, 정확한 compatibility 값 | 동반 코드·조치 전후·재발 시간 조건, 상세 decoder |
| 분석 | 코드 충분성, 제한된 재조사, 지침/한계를 Synthesis에 전달 | 실제 LLM endpoint·분석 품질 검수 |
| 결과 | 근거·후보 저장과 JC 공개; 조사용 콘텐츠의 원인 승격 금지 | 오류 확인·원인·조치 적합성·회복의 의미 검증 확대 |

`analysis_guidance`는 실행된 검사 결과가 아니다. 로그를 못 읽었으면 해당 오류가 없다고 판단하지 않는다. Fleet parser는 보고된 오류 코드를 추출하지만 현재 시각 검증 조건에서는 `health_facts`의 검증된 `error_code`·`normalized_health` 등으로 승격하지 않는다. 등록된 다른 producer의 조건 충족 여부와 구분하며 현재 초안은 그 공백을 숨기지 않는다. R코드는 조사 목적, D코드는 등록 쿼리다. 세부 지표가 필요하다고 임의의 D코드를 생성하지 않는다.

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

검증 범위는 [Agent QA](../../agents/QA.md)와 [Backend QA](../../backend/QA.md), 현재 실행은 [RCA 안내](../README.md)를 따른다. 저장소 내용과 운영 발행 revision을 구분한다.

다음 입력: 실제 Fleet image와 source revision, 비밀을 제거한 원본 로그, 노드/GPU/NVSwitch 식별 연결, Grafana 수집 라벨·기간·완전성, 설치 플랫폼/드라이버/FM 버전. 이를 확보하면 query/parser와 세부 판정을 연결하고 운영 compatibility를 검토한다.

## 7. Xid 79·SXid 11001 단일 수집 보고서 배포·발행

PR #170의 새 경로는 두 런북의 **전체 본문**과 RCA Worker/UI를 함께 적용한다. 아래 절차는 사용자가 실행하는 운영 인수 절차이며, 문서 작성이나 PR CI는 발행을 수행하지 않는다. Ops 이미지·설정·런북·보고서, DB schema와 PVC는 바꾸지 않는다.

### 7.1 적용 순서와 준비물

1. PR의 `CI required` 통과 후 병합하고, 해당 main 커밋의 CI 성공과 발행 이미지 digest를 확인한다. PR 빌드 이미지 자체는 레지스트리에 발행되지 않는다.
2. 기존 배포의 RCA Worker/frontend 이미지 digest와 두 런북의 발행 revision·hash를 보존한다. 공유 frontend 배포에는 RCA UI 변경을 포함하되 Ops 이미지·설정은 유지한다. 설치 전체를 기본 values로 덮어쓰지 않는다.
3. RCA Worker와 frontend를 배포한다. 기존 런북은 구 경로를 유지하므로 새 revision 발행 전에 Worker 교체와 준비 상태를 확인한다.
4. 실제 RCA Worker가 사용하는 query profile을 비밀 없는 로컬 JSON으로 확보한다. 아래 `$RcaProfile`은 `queries`가 있는 실제 프로필 파일이다. 예제 프로필을 운영 검증의 대용으로 쓰지 않는다. Xid는 D09/D44/D02/D11, SXid는 D09/D47/D33/D34가 등록되고 해당 procedure에서 허용되어야 한다. Loki/Mimir binding·대상 라벨·30분 범위도 확인한다. CLI check는 query 등록을 검사하지만 각 procedure 허용 집합까지 증명하지 않는다.
5. 두 런북의 기존 knowledge ID와 검수된 compatibility를 확인한다. 런북별로 아래 단계를 수행하며 새 revision 번호를 임의로 정하지 않는다.

### 7.2 기존 발행본 조회와 새 본문 준비 (PowerShell)

저장소 루트의 Python 3.12 환경에서 실행한다. `$RcaBackend`는 이번 배포 대상 UI의 Backend 주소다. `REPLACE_...` 값은 해당 환경에서 확인한 값으로 바꾼다. 이 단계는 GET과 로컬 파일 작성만 한다.

```powershell
$RcaBackend = 'http://192.168.20.186:30006/api/v1'
$RcaProfile = '.local/rca-runtime-profile.json'
$RcaCode = 'xid:79'
$RcaKey = 'RB-XID-79'
$RcaSource = 'rcca-agent/runbooks/xid/RB-XID-79.json'
$RcaPrefix = '.local/xid79-dossier'
New-Item -ItemType Directory -Force .local | Out-Null
$RcaPublished = Invoke-RestMethod "$RcaBackend/knowledge?kind=runbook&state=published&code=$([uri]::EscapeDataString($RcaCode))"
$RcaPublished.items | Select-Object knowledge_id, knowledge_key, revision, state, content_hash
# 응답의 대상 knowledge_key·scope·compatibility를 대조해 선택한 ID/revision을 입력한다.
$RcaKnowledgeId = 'REPLACE_WITH_EXISTING_KNOWLEDGE_UUID'
$RcaPreviousRevision = 'REPLACE_WITH_PUBLISHED_REVISION'
$RcaPrevious = Invoke-RestMethod "$RcaBackend/knowledge/$RcaKnowledgeId/revisions/$RcaPreviousRevision"
if ($RcaPrevious.knowledge_key -ne $RcaKey -or $RcaPrevious.state -ne 'published') { throw 'Wrong published Runbook' }
$RcaPrevious | ConvertTo-Json -Depth 100 | Set-Content "$RcaPrefix-previous.json" -Encoding utf8
$RcaNext = Get-Content $RcaSource -Raw | ConvertFrom-Json
$RcaNext.compatibility = $RcaPrevious.compatibility
$RcaNext.visibility = $RcaPrevious.visibility
$RcaNext.scope = $RcaPrevious.scope
$RcaNext | ConvertTo-Json -Depth 100 | Set-Content "$RcaPrefix-next.json" -Encoding utf8
python -m rcca_agent.runbook_admin check "$RcaPrefix-next.json" --profile $RcaProfile --runtime
if ($LASTEXITCODE -ne 0) { throw 'Runtime validation failed' }
```

기존 compatibility를 보존하는 것은 적용 조건 확대를 방지하기 위한 것이다. 새 조회에도 조건이 유효한지 검토한다. 기존 본문에 `decision_policy`만 추가하면 새 전체 조회 계획이 적용되지 않는다. 반드시 새 작성 원본의 전체 content와 기존 환경 적용 조건을 대조한다. 이전 응답과 이후 receipt는 로컬 보관하며 커밋하지 않는다.

SXid 11001은 다음 다섯 값을 바꾸고 **별도의 기존 ID/revision**으로 동일 절차를 반복한다.

```powershell
$RcaCode = 'sxid:11001'
$RcaKey = 'RB-SXID-11001'
$RcaSource = 'rcca-agent/runbooks/sxid/RB-SXID-11001.json'
$RcaPrefix = '.local/sxid11001-dossier'
# $RcaKnowledgeId와 $RcaPreviousRevision은 SXid 조회 결과에서 다시 지정한다.
```

### 7.3 새 revision 등록 → 검토 요청 → 승인 → 발행

아래는 현재 선택한 **한 런북**의 순서다. 각 명령을 따로 실행하고 종료 코드 0과 저장 receipt의 state/content_hash/revision을 확인한 후 다음 명령을 실행한다. `$RcaBatch`는 이번 본문에 고유한 이름이며 네트워크 응답 유실 시에는 같은 입력·같은 키로 재실행한다. 본문을 변경하면 새 batch를 사용한다.

```powershell
$RcaBatch = "$RcaKey-dossier-REPLACE_WITH_UNIQUE_BATCH"
python -m rcca_agent.runbook_admin draft "$RcaPrefix-next.json" --profile $RcaProfile --backend $RcaBackend --knowledge-id $RcaKnowledgeId --request-key "$RcaBatch-draft" --output "$RcaPrefix-draft.json"
```

receipt의 state가 `draft`이고 기존 knowledge ID에 새 revision이 생성됐는지 확인한다. 이후 검토 comment에는 실제 확인한 플랫폼/프로필 revision·조회 대상/지표·출처를 적는다.

```powershell
python -m rcca_agent.runbook_admin request "$RcaPrefix-draft.json" --profile $RcaProfile --backend $RcaBackend --request-key "$RcaBatch-request" --comment 'REPLACE_WITH_REVIEW_SCOPE' --output "$RcaPrefix-requested.json"
```

`in_review`와 검토 대상 hash를 확인하고, 운영 적용 조건과 조회 계획 검토를 마친 뒤 승인한다.

```powershell
python -m rcca_agent.runbook_admin approve "$RcaPrefix-requested.json" --profile $RcaProfile --backend $RcaBackend --request-key "$RcaBatch-approve" --comment 'REPLACE_WITH_VERIFIED_PROFILE_AND_EVIDENCE' --output "$RcaPrefix-reviewed.json"
```

`reviewed` 확인 후 발행한다.

```powershell
python -m rcca_agent.runbook_admin publish "$RcaPrefix-reviewed.json" --profile $RcaProfile --backend $RcaBackend --request-key "$RcaBatch-publish" --output "$RcaPrefix-published.json"
$RcaReceipt = Get-Content "$RcaPrefix-published.json" -Raw | ConvertFrom-Json
$RcaSaved = Invoke-RestMethod "$RcaBackend/knowledge/$RcaKnowledgeId/revisions/$($RcaReceipt.revision)"
if ($RcaSaved.state -ne 'published' -or $RcaSaved.content_hash -ne $RcaReceipt.content_hash -or $RcaSaved.reviewed_content_hash -ne $RcaReceipt.content_hash) { throw 'Publication mismatch' }
$RcaSaved | Select-Object knowledge_id, revision, state, content_hash, reviewed_content_hash
```

두 런북이 각각 이 검사를 통과해야 발행 완료다. 기존 발행 revision은 검수 완료 전 retire하지 않는다. API의 인증·접근 제어가 추가된 환경은 조직의 승인된 접속 방법을 사용하며 인증정보를 명령 기록이나 PR에 넣지 않는다.

### 7.4 배포 후 실제 보고서 검수 순서

시험을 위해 장비 장애를 만들지 않는다. 실제 신규 알림 또는 UI의 승인된 RCA 재실행으로 Xid79/SXid11001을 각각 확인한다. 기존 완료 보고서는 자동 갱신되지 않는다.

| 순서 | 확인할 실제 결과 | 합격 기준 |
|---|---|---|
| 1. 접수·선택 | Incident ID, 노드/장비, job/attempt, 고정 Runbook revision/hash | 새 발행 receipt와 일치하고 다른 장비/코드가 섞이지 않음 |
| 2. 수집 | 실행 기록의 observation plan과 각 D의 근거 | 해당 코드의 전체 계획이 한 수집 단계에서 실행됨. D09 일치만으로 조기 종료하거나 모델이 추가 조회를 선택하지 않음. 한 단계는 HTTP 호출 한 번이라는 뜻이 아님 |
| 3. 관련 자료 | 동일 조회 구간의 Loki 원문·Mimir 관측과 보고서 표 | 코드·시각·보고 구간·단위·수치 일치. Xid GPU는 gpuInfo/PCI/UUID 대조 대상, SXid GPU 지표는 같은 노드의 보조 관측으로 표시 |
| 4. 이력 | 해당 host의 14일 Incident 목록·최초 snapshot과 이력 표 | Incident ID 중복 없이 건수/날짜/장치 일치. 7일·코드 필터 및 동일 코드/GPU의 최근 등록 간격·범위 일치. 로그 수신 건수를 장애 횟수로 바꾸지 않음 |
| 5. 모델·공개 | 작성/검토/보고서 단계 기록, 최종 job 상태, 공개 result 참조와 다시 읽기 | 실제 모델 호출 결과와 실패 시 코드가 보존하는 사실을 구분해 검사. JC가 결과를 공개하고 새로고침/직접 링크에서도 동일 보고서를 읽음. auto-router 기록만으로 Super/Ultra 실행을 단정하지 않음 |
| 6. 운영자 읽기 | 보고서 첫 화면 → 관련 관측 → 이력 → 권고 → 원문 | 언제·어느 노드/장비·무슨 오류·어떤 보고 구간인지 찾기 쉬움. 관련 지표와 동반 로그, 반복 빈도와 간격이 바로 보이고 오류별 NVIDIA 지침에 연결됨. 일반적인 한계 문구가 핵심 정보를 밀어내지 않음 |
| 7. UI 동작 | 기간/코드 전환·원문 팝업·사건 링크·닫기 | 필터 건수와 행이 맞고 기간 변경 시 코드 선택 초기화. 원문은 해당 evidence를 열며 새 사건 링크가 맞는 장비로 연결됨 |

검수 기록은 Incident/job/result ID, Runbook revision/hash, 이미지 digest, 모델 기록, 조회 기간과 비교한 원문 참조를 보존한다. 보고서 생성 성공과 정보 전달 품질을 각각 판정하고 수정 후 같은 사건을 다시 대조한다. 실제 원문·노드 정보는 공개 PR에 붙이지 않는다.

### 7.5 실패 시 복귀

새 revision의 선택/수집에 문제가 있으면 해당 런북의 최신 발행 receipt를 사용해 `retire`한다. 다른 런북이나 Ops 상태는 변경하지 않는다.

```powershell
python -m rcca_agent.runbook_admin retire "$RcaPrefix-published.json" --profile $RcaProfile --backend $RcaBackend --request-key "$RcaBatch-retire" --comment 'REPLACE_WITH_FAILURE_REASON' --output "$RcaPrefix-retired.json"
```

구 발행본이 여전히 published인지, 다음 새 claim이 그 revision/hash를 선택하는지 확인한다. retire는 이미 실행 중인 claim의 참조나 과거 보고서를 되돌리지 않는다. 필요하면 보존한 RCA/frontend 이미지 digest로 복귀한다. DB 삭제·과거 결과 수정·PVC 재생성은 수행하지 않는다.

## 조사 완료 기준 1.1

과거 `decision_policy`와 goal은 발행 JSON 구조 호환을 위해 읽지만, 현재 모든 런북의 수집·분석·종료를 제어하지 않는다. D09만으로 목적 달성을 평가해 나머지 조회를 생략하는 절차는 폐기했다. 새 revision은 위의 전체 content 교체 절차로 발행한다.

검수에서는 선택된 revision/hash, 계획된 조회 실행, 로그·메트릭·DB 이력을 함께 사용한 분석, 보고서 공개와 원문 연결을 확인한다. 장애 여부의 재판정이나 원인 확정은 생성 성공 조건이 아니다. 기존 발행본과 과거 결과는 수정하지 않는다. 현재 실행은 [RCA README](../README.md#현재-실행-흐름)를 따른다.
