# DSX 사이트 권한과 Mimir Tenant 설계

작성일: 2026-09-16. 상태: **목표 설계·구현 제안**. 인증 도입은 후순위로 유지하되 데이터·작업의 권한 범위를 지금 정의한다. CPC 내부 수집, Gateway 설정, Mimir/Loki tenant, Grafana, PostgreSQL을 실제 변경하지 않았다.

## 1. 사용자 요구와 적용 방향

하나의 CSC 역할로 여러 사이트를 운영한다. 사용자는 허용된 사이트만 조회하고, 통합 운영자는 별도 권한으로 여러 사이트를 비교한다. Backend는 기존 8개 기능과 API 서버·RCA Worker·보고서 Worker 구성을 유지한다.

**사이트가 독립된 접근·보관·운영 경계라면 사이트별 tenant를 두는 안을 우선 검토한다.** 하나의 사이트에 CPC·클러스터가 여러 개 있을 수 있으므로 `site = CPC = cluster`로 고정하지 않는다. tenant 내부에서도 `cluster_id`, Node, GPU UUID 등 관측 식별 라벨을 유지한다. CSC 역할 하나가 Mimir 프로세스나 물리 서버 한 대를 뜻하지 않는다.

전체 사이트 비교가 필요하다는 이유만으로 단일 tenant를 확정하지 않는다. Mimir는 승인된 다중 tenant 조회를 지원한다. Fleet Agent는 수집 주체이며, 사이트 비교 분석의 주체는 CSC의 RCA/운영보고서 Agent와 공통 조회 모듈이다.

## 2. 첨부 설명에서 채택·보정한 내용

| 첨부 설명 | 반영 기준 |
|---|---|
| SQL의 CREATE INDEX와 다름 | 채택. Mimir가 메트릭 이름과 라벨을 내부 인덱스로 관리하며 사용자 지정 SQL 인덱스를 만드는 기능과 구분한다. |
| 토큰 하나 = tenant 하나 | 보정. 인증 토큰과 tenant ID는 별개다. 여러 수집 자격증명이 같은 site tenant에 매핑될 수 있고 한 사용자가 여러 사이트 권한을 가질 수 있다. 토큰 회전으로 tenant를 새로 만들지 않는다. |
| 논리적이 아니라 물리적으로 완전히 분리 | 보정. tenant별 TSDB·블록·객체 영역은 분리되지만 프로세스·서버·CPU·메모리·스토리지와 장애 도메인은 공유할 수 있다. 전용 인프라나 자동 성능 격리라고 표현하지 않는다. |
| Mimir OSS는 사용자 토큰을 직접 검증하지 않음 | 채택. 외부 인증·인가 계층이 검증한 신원에서 tenant를 결정해야 한다. tenant 문자열의 형식 검증과 사용자의 접근 권한 검증은 다르다. |
| Gateway가 헤더 제거·덮어쓰기 | 채택. 쓰기뿐 아니라 조회 경로도 적용한다. 신뢰할 수 없는 tenant·사용자 헤더를 제거하고 검증된 권한으로 설정한다. 우회 접근도 제한한다. |
| 단일 tenant + cluster 라벨이 항상 더 적합 | 조건부 대안. 모든 사이트가 동일 신뢰·정책 경계일 때는 단순하지만 사이트 라벨은 자체 접근 통제가 아니다. 현재의 사이트별 사용자 격리 요구에는 추가 권한 강제가 필요하다. |
| tenant면 카디널리티 폭주가 다른 사이트를 죽이지 않음 | 보정. tenant별 제한과 자원 배분을 함께 설정해야 한다. 전체 자원 고갈과 장애 전파는 자동으로 사라지지 않는다. |
| 라벨 구분은 오버헤드 없음 / federation은 성능 이점 없음 | 보정. 라벨·시계열도 저장/검색 비용이 있고 tenant 수도 관리 비용을 만든다. federation 비용·지연과 분리 효과는 데이터량·쿼리·배치로 측정한다. |

Mimir의 tenant별 TSDB와 블록 인덱스는 [공식 아키텍처](https://grafana.com/docs/mimir/latest/get-started/about-grafana-mimir-architecture/)를 따른다. tenant별 블록 목록 조회에는 [bucket index](https://grafana.com/docs/mimir/latest/references/architecture/bucket-index/)가 사용될 수 있다. 인덱스가 있어도 넓은 기간·많은 시계열·복잡한 쿼리의 비용은 남는다.

## 3. 쓰기·조회 경계

### 쓰기

`사이트 Alloy → 인증/인가 Gateway → 사이트 tenant → Mimir`

Gateway는 서명·issuer·audience·만료 등 서비스 토큰을 검증하고, 서버에 등록된 서비스 신원과 사이트 관계로 쓰기 tenant를 결정한다. tenant 헤더를 송신자가 지정하도록 위임하지 않는다. 쓰기는 승인된 한 tenant로 한정하며 잘못된 신원·등록·범위는 기본 거부한다. 인증된 한 수집 요청에 여러 사이트 데이터가 섞이는 구조라면 헤더 하나만 바꾸지 말고 분리·검증 방법부터 확정한다.

CPC 내부 Fleet·KSM·Exporter·Alloy 수집 토폴로지는 유지한다. 인증 자격증명과 전송 계약의 향후 설정 필요 여부는 별도 확인하며, 현재 수집 내용을 손대지 않았다고 해서 인증 헤더가 이미 존재한다고 가정하지 않는다.

### 조회

`사용자/작업 → 기능·사이트 권한 검사 → 허용 site를 저장소 tenant로 매핑 → 조회`

`X-Scope-OrgID`는 데이터 영역 선택 헤더이며 비밀 인증 토큰이 아니다. 인증된 요청자에게 허용된 사이트 집합 안에서만 대상 tenant를 선택한다. 다중 tenant 조회는 설치 버전·설정 확인 후 `tenant-federation.enabled=true`와 승인된 tenant 목록을 사용하는 설계다. `site-a|site-b`는 설명용 조회 예이며 배포 설정이 아니다. [Mimir 인증·인가](https://grafana.com/docs/mimir/latest/manage/secure/authentication-and-authorization/)

Grafana 직접 접속도 동일한 원칙을 적용한다. 구현 방법은 조직/데이터 소스에 고정된 제한 자격증명 또는 사용자 신원을 검증하는 조회 프록시 등 실제 Grafana 구성에 맞춰 정한다. 사이트별 조직을 만들어도 데이터 소스가 모든 tenant를 조회할 수 있으면 격리가 완성되지 않는다. Backend 조회만 보호하고 Grafana나 원본 저장소로 우회할 수 있게 두지 않는다. Dashboard 변수·URL·Frontend 선택값은 권한 근거가 아니다.

## 4. Backend 8개 기능에 반영할 계약

| 위치 | 사이트 권한 처리 |
|---|---|
| ① 사용자 API·대화 | Keycloak 등에서 검증한 신원과 PostgreSQL 정책을 결합. 기능 권한과 사이트 범위를 모두 검사. 일반 대화·도구 호출에도 적용. |
| ② Incident | Grafana 송신 신원, 등록 규칙/사이트 관계와 이벤트 범위를 확인. 임의 payload의 site_id를 신뢰하지 않음. 사이트를 포함한 사건·중복 키 사용. |
| ③ 작업 관리 | `requester_id`, 요청/허용 `site_ids`, 권한 정책 버전, 대상·기간을 작업에 보존. 큐에서 꺼내 실행할 때 현재 권한과 비교해 재검증. 예약 작업에는 명시적 소유자·사이트 범위 적용. |
| ④⑤ Agent Worker | 작업 범위와 현재 허용 범위 안에서 실행. Worker 서비스 계정이 넓은 접근권을 가져도 사용자 작업의 범위를 확대하지 않음. 모델이 권한을 결정하지 않음. |
| ⑥ 조회·계산 | `site_id → 저장소별 tenant` 매핑, 검증된 쿼리와 매개변수 사용, 결과·캐시를 권한 범위별로 분리. 통합 분석에서는 site/tenant·cluster 원본 식별을 유지. |
| ⑦ Knowledge | 공용 발행 지식과 사이트 전용 자료·검증 사례의 검색/발행 권한을 구분. |
| ⑧ LLM 호출 | 허용된 근거만 모델에 전달. 출력·근거 파일·보고서에 사이트 범위를 유지. 호출량 제어의 토큰 수와 인증 토큰을 구분. |

결과 목록·상태·열람·다운로드·공유에도 현재 권한을 검사한다. 권한 회수·작업 취소 뒤의 늦은 결과를 임의 공개하지 않는다. 사이트 전체 자료로 만든 비교 보고서를 권한이 좁은 사용자에게 일부 화면만 숨겨 제공하지 않는다.

PostgreSQL에는 사이트 원장, 저장소별 tenant 매핑, 사용자/그룹·역할·사이트 권한 관계를 두고 업무 데이터의 site 귀속을 보존한다. 다중 사이트 보고서는 실행-사이트 관계로 범위를 기록한다. 관계 키·캐시·근거 참조에도 범위를 포함한다. 사이트별 PostgreSQL 서버를 기본으로 늘리지 않는다.

## 5. Tenant와 라벨의 선택

| 항목 | 사이트별 tenant | 단일 tenant + site/cluster 라벨 |
|---|---|---|
| 데이터 영역 | tenant별 TSDB·블록/객체 분리 | 같은 tenant 안에서 라벨로 선택 |
| 권한 | Gateway가 승인 tenant를 강제 | 모든 쿼리·탐색 경로에 라벨 범위 권한 강제 필요 |
| 수집·조회 한도 / 보관 | 지원 설정을 tenant별 적용 가능 | tenant 공통 정책이 기본 |
| 사이트 비교 | 승인된 federation 또는 사이트별 조회 후 비교 | 같은 tenant에서 라벨별 비교 |
| 비용·성능 | tenant별 관리 비용, 공유 자원은 별도 제한 | 라벨·시계열 비용, 범위 검사 누락 방지 필요 |

Mimir 메트릭 보존은 전역 또는 tenant별 설정이다. 라벨만으로 시계열별 보존 정책이 생기지 않는다. [보존 설정](https://grafana.com/docs/mimir/latest/configure/configure-metrics-storage-retention/)

tenant별 수집/시계열/쿼리 한도, 기간·동시 조회·Agent 실행 한도와 캐시를 함께 설계한다. 자원 격리를 더 강화해야 할 때 배포 방식에 맞는 [shuffle sharding](https://grafana.com/docs/mimir/latest/configure/configure-shuffle-sharding/)·리소스 할당·추가 인스턴스를 검토한다. 설치 버전·classic/ingest-storage 구성에 따라 적용 가능한 제어가 달라지므로 tenant 수만으로 성능을 보장하지 않는다.

## 6. ID와 현행 환경 확인

Tenant ID는 150바이트 이내의 지원 문자만 사용한다. 영숫자와 `! - _ . * ' ( )`가 허용되고 `.`·`..`·`__mimir_cluster`는 사용할 수 없다. 운영 식별자는 읽기 쉬운 소문자 영숫자·하이픈으로 제한하는 안을 권한다. 표시명 변경이나 인증 토큰 회전과 tenant ID 변경을 연결하지 않는다. [Tenant ID 제약](https://grafana.com/docs/mimir/latest/configure/about-tenant-ids/)

멀티테넌시 비활성화 시 기본 단일 tenant 동작이므로 사이트별 분리를 가정하지 않는다. 실제 버전·설정을 확인한다.

사용자가 인용한 `CPC-KSM-to-CSC-Mimir.md:105`의 `dsx` 값은 제공된 설명의 주장으로 보존한다. 이번 작업에서 해당 원문/실배포 설정은 확인하지 못했다. 기존 진행 기록에는 다른 tenant 명칭도 있으므로 `dsx`를 현재 모든 Mimir/Loki 경로의 값으로 덮어쓰지 않는다. 저장소·수집 경로·시점별 현행 값을 조사해야 한다.

기존 단일 tenant에 저장된 과거 데이터는 새 토큰이나 헤더로 자동 분리되지 않는다. 전환 시점, 과거 조회 권한, 필요하면 이전/재수집, 중복 방지와 Grafana 데이터 소스·알림 규칙을 별도 계획한다. 신규 기록을 사이트별로 나누는 것만으로 과거 격리가 해결됐다고 표시하지 않는다.

## 7. 관련 산출물

- [전체·Backend·사이트 tenant 구조도 v2](<../architecture-backend-20260916-v2/DSX_Full_Backend_Tenant_20260916_v2.html>)
- [두 Agent 공통 판단 기준](<DSX_Agent_공통판단기준과_인사이트사례_v1.0.md>)

이 문서는 제공된 설명을 검증해 반영한 설계 기록이다. 첨부문의 명령·설정 예를 실행하지 않았으며 사이트별 tenant 전환 완료를 의미하지 않는다.
