# Runbook 개발 및 RCA 연계

> 2026-10-02 후속 설계: 이 폴더의 JSON은 추후 DB에 등록할 작성 원본이다. D 통합·확장에 따른 원본 수정, 오류 코드 없는 조사, DB 초안 등록·검토·발행의 순서는 [D 매핑 설계 §7](../../docs/specs/common/d-query-mapping.md#7-rca-runbook의-통합확장-매핑)과 [개발 계획](../../docs/specs/common/d-contract-redesign-plan.md)을 따른다. 현재 JSON과 아래 실행 절차는 아직 변경하지 않았으며, 신규 D가 구현·검증된 것으로 읽지 않는다.

## R 없는 조사 계획과 예상 밖 근거 — 2026-10-02

Runbook의 `observation_plan`이 수집 계획의 원천이다. R 코드나 procedure별 허용 D를 작성하지 않는다. 등록된 D는 모두 계획에 사용할 수 있지만 대상/기간/예산 제한을 우회할 수 없다. `required_evidence`는 판단에 필요한 근거이며 `fact_names`에 적었다고 자동 생성되지 않는다.

선택 필드 예시:

```json
"unexpected_evidence": {
  "on": ["unknown_value", "missing_evidence", "conflicting_evidence", "query_failed"],
  "additional_queries": ["D02"],
  "fallback": "general_runbook"
}
```

미등록 상태·해석 불가 응답, 부족 근거, 상충 관측, 조회 실패가 발생하면 등록된 추가 조회를 수행하고 일반 조사로 보완한다. `fallback=stop`은 지정 추가 조회 이후 더 확장하지 않는다는 뜻이다. 최대 한 번의 추가 라운드와 기존 예산을 사용하며, 해결되지 않은 근거·관측은 unknown/partial/blocked로 남긴다. 원본 값·실패와 실행한 정책을 evidence에 기록한다. 임의 쿼리/명령 실행과 원인·회복 추정은 허용하지 않는다.

필드가 없는 과거 발행본은 보수적인 일반 조사 전환 정책을 적용하고 유효 정책을 Plan에 기록한다. 변경한 콘텐츠는 새 revision으로 등록·검토·발행해야 하며 기존 DB/hash는 수정하지 않는다. 일반 Runbook의 패키지 사본은 content를 그대로 동기화하고 일치 테스트를 통과해야 한다.

2026-09-28 후속: XID 173건·SXID 93건과 일반 조사 1건, 총 267건의 문헌 기반 조사 초안을 작성했다. 기존 대표 3건을 보강하고 263건을 추가했다. 전체 파일·근거 상태·검토 절차는 [전체 코드 목록](CATALOG.md)을 따른다. 기존 Backend 등록·검토·발행·RCA 소비 경로를 사용한다. 저장 구조와 다른 PC의 재현 절차는 [DB 등록 안내](DB-WORKFLOW.md)를 따른다. 운영 DB 등록 및 실제 Grafana/LLM 검증은 수행하지 않았다.

아래는 기존 대표 사례이며 전체 범위는 CATALOG를 따른다.

| 파일 | 진입 단서 | 구현한 범위 |
|---|---|---|
| [RB-GENERAL-GPU-NODE.json](RB-GENERAL-GPU-NODE.json) | 전용 Runbook 미일치 | 일반 로그·상태·보조 사용률 조사. 원인 판정은 하지 않음 |
| [RB-XID-79.json](xid/RB-XID-79.json) | Xid 79 | 원본 오류·producer 상태 확인, 추가 조사 권고 |
| [RB-XID-48-63-64.json](xid/RB-XID-48-63-64.json) | Xid 48 | ECC 이벤트 조사, 동반 Xid 63·64와 모델별 증거 확인 안내 |
| [RB-SXID-11001.json](sxid/RB-SXID-11001.json) | SXid 11001 | NVSwitch·FM 원본과 포트·플랫폼 맥락 확인. 영향·fatality는 미확정 |

Xid 48 Runbook에서 63·64는 추가 확인 대상이다. 해당 코드만으로 검색·적용하거나 시간 순서를 판정하지 않는다. 모든 초안은 원인 확정이나 reset·재부팅·교체를 실행하지 않는다. 기술 출처는 [NVIDIA GPU Node Triage](https://docs.nvidia.com/deploy/gpu-debug-guidelines/gpu-node-triage.html)와 [Fabric Manager 가이드](https://docs.nvidia.com/datacenter/tesla/fabric-manager-user-guide/index.html)다. sources에 페이지 표시 개정일·절·확인 날짜를 기록했다. 참조 코드와 공식 표의 정의 차이는 CATALOG와 개별 콘텐츠에 기록했다. 변경 가능한 원문이므로 운영 검토 때 해당 버전을 다시 대조한다.

JSON은 `xid/`, `sxid/`에 종류별로 보관하며 일반 조사는 상위 폴더에 둔다. 전체 검사·DB 초안 일괄 등록은 `python -m rcca_agent.runbook_import`를 사용한다. [일괄 등록 절차](DB-WORKFLOW.md)를 따른다. JSON의 반복 개발 설명은 문서로 옮기고 코드별 조사 내용만 유지한다.

## 저장과 실행 경계

JSON은 기존 Backend Knowledge 생성 요청의 필드만 사용한다. 생성 API는 draft를 만들며, 별도 테이블·서비스·자동 seed를 추가하지 않았다. 파일을 놓았다고 Worker가 읽는 구조가 아니다. Worker는 기존 DB의 공개·고정된 revision/hash를 읽는다.

267개 파일의 compatibility는 의도적으로 빈 객체다. 실제 producer와 장비 범위를 확인한 뒤 정확한 값을 채워야 한다. 검증기의 authoring=True는 초안 구조 점검에만 사용하고, RCA 실행에서는 사용하지 않는다. 빈 호환성으로 운영 적용되는 것을 기본 검증기가 차단한다. 일반 조사도 검수한 cluster와 query 범위를 명시해야 한다. SXid 초안은 해당 오류 체계를 쓰는 플랫폼 및 FM 버전이 확인된 환경에만 바인딩하며 B200/B300에 포괄 적용하지 않는다.

최상위 source_refs는 **DB evidence ID**다. 문헌 URL을 넣지 않는다. 현재 common Knowledge는 사건 evidence를 연결할 수 없으므로 초안은 빈 배열이며 문헌 메타데이터는 content.sources에 둔다. 문헌 출처는 사건의 관측·실행 증거를 대신하지 않는다.

## RCA가 사용하는 계약

[runbook_contract.py](../src/rcca_agent/runbook_contract.py)의 공개 함수:

- schema_kind(content): schema 키가 없으면 legacy, 정확히 gpu-rca-runbook/1.0이면 v1. 그 외 명시된 값은 ValueError.
- validate_runbook(row, queries, allowed_queries): v1 구조·조건·호환성 선언·등록 query ID를 검증하고 독립된 observation_plan을 반환한다. 실패하면 ValueError. queries는 claim에 고정된 실행 프로파일의 레지스트리이며 allowed_queries는 선택된 procedure의 허용 ID다.
- compatibility_status(requirements, attributes): 검증된 대상 속성에 대해 compatible/pending/incompatible을 반환한다. 호출자가 이미 대상·시각·freshness·증거를 확인한 {속성명: {status: "known", value: 값}}을 전달해야 한다. 문자열·불리언 정확 일치만 지원한다. 배열 값은 OR, 속성 사이는 AND이며 알려진 불일치는 누락보다 우선한다.

v1 조건식은 기존 {field, equals} 형태다. 적용 조건은 AND이며 exclusion의 결합 의미는 RCA 평가기를 따른다. 임계값·정규식·시간 순서·미등록 연산자를 추가하지 않았다. error_code는 xid:79 또는 sxid:값처럼 정규화된 문자열이어야 한다. 현재는 producer_contract, error_code, normalized_health, component, severity의 문자열 조건만 허용한다.

현재 모든 콘텐츠는 `investigation_only: true`를 명시한다. 조사용 콘텐츠의 recommendations도 현재 workflow의 최종 eligible 조치 목록에는 포함하지 않는다. 이 경우에만 빈 applicability_conditions를 허용하며, 원인 supported 판정·기존 근거만으로 조기 완료하는 근거로 사용하지 않는다. `rca.general_runbook_key`에 지정한 v1 콘텐츠에 이 표시가 없으면 실행 계획에서 제외한다. 일반 조사도 schema·scope·hash·호환성 검증을 통과해야 한다.

선택된 계획의 `analysis_guidance`와 `limitations`는 revision·적용 상태와 함께 도구 없는 Synthesis 입력으로 전달한다. pending 계획의 조건은 미확인 상태이며 지침은 관측 사실이 아니다. LLM이 지침을 받았다고 parser 없는 오류 코드가 검증되지는 않는다.

observation_plan은 다음 필드를 갖는다:

| 필드 | 의미 |
|---|---|
| query_id | 등록 D코드. procedure 허용 목록에도 포함되어야 함 |
| priority | 양의 정수. 오름차순 실행 계획, 동률은 query_id 순 |
| required | 필수 관측 여부. false는 조건에 따라 선택할 보조 조회 |
| fact_names | 확보하려는 fact 이름. parser나 충족을 보장하지 않음 |
| purpose | 해당 관측의 조사 목적 |
| binding | execution_profile만 지원. 콘텐츠에 datasource나 임의 쿼리를 삽입하지 않음 |
| time_range | incident만 지원. 실제 범위는 claim·query 계약에서 결정 |
| freshness | query_contract만 지원. 콘텐츠가 자체 임계값을 만들지 않음 |

required_queries를 함께 쓰면 plan의 required=true인 ID 집합과 일치해야 한다. plan을 생략하면 required_queries의 원래 순서를 사용하며 fact_names를 추측하지 않는다. 모든 초안은 D09·D05를 필수 관측, D02를 선택 관측으로 제시한다. priority는 예산 배정 순서이며 필수 관측은 병렬 실행되므로 선행 완료 의존성을 뜻하지 않는다. 이미 유효한 증거로 목적과 원인 판정용 Runbook이 충족됐으면 RCA가 수집을 생략한다.

R코드는 RCA의 조사 목적이고, D코드는 등록 조회 ID다. Runbook마다 R01~R09 필드를 요구하지 않는다. 현재 D코드만으로 ECC·NVLink·IB 세부 수치나 복구를 입증할 수 없다.

## 병행 개발 연결 순서

RCA 담당은 DB revision/scope/hash 검사 → schema 분기 → v1 검증 → 검색·호환성/조건 평가 → 계획 소비를 연결한다. 알려지지 않은 schema나 잘못된 v1은 legacy equality로 대체하지 않고 진단을 남겨 보류한다. 검색 점수나 콘텐츠 검증 성공만으로 적용·원인 확정·증거 충족을 선언하지 않는다.

기존 증거가 부족하면 허용된 계획으로 Grafana MCP에서 병렬 수집하고, 코드 충분성·최대 1회 재조사 이후 Synthesis와 코드 검증을 수행한다. 부족하면 partial/blocked와 원인 미확정을 유지한다. 모든 정상 결과 경로는 evidence·candidate 저장 및 JC 공개를 거치며 보고서 Agent는 공개된 RCA 참조를 사용한다. 전체 실행부의 입력 1.3/1.4 및 운영 검증 경계는 [보완 계획](../../docs/specs/rca-agent/implementation-plan-20260928.md)을 따른다.

Runbook 담당 파일은 이 디렉터리, 검증기 및 [전용 테스트](../../agents/tests/test_runbook_contract.py)다. RCA 담당은 workflow/procedures/prompts와 런타임 테스트를 관리한다. JC/DB 저장 형식과 보고서 결과 계약은 변경하지 않는다.

## 검증 및 남은 조건

저장소 루트, 지원 Python 환경에서:

~~~powershell
python -m pytest -c agents/pytest.ini agents/tests/test_runbook_contract.py -q
ruff check rcca-agent/src/rcca_agent/runbook_contract.py agents/tests/test_runbook_contract.py
ruff format --check rcca-agent/src/rcca_agent/runbook_contract.py agents/tests/test_runbook_contract.py
python tools/check_links.py
~~~

전용 테스트는 실제 JSON → 결정적 검색 → 허용된 조회 계획 연결, 미등록/금지 조회·잘못된 조건·미실행 권고 규칙, 호환성 미확인 및 초안 런타임 차단을 검사한다. 네트워크·DB·LLM을 호출하지 않는다. fixture 속성은 운영 호환성 검증 자료가 아니다.

2026-09-28 초기 초안 검증은 전용 테스트 6건과 retrieval 테스트 18건, 총 24건이었다. 후속 검증은 실제 일반 조사 JSON에 테스트용 cluster 호환성만 부여해 격리 DB에 발행하고, RCA 계획·NAT/MCP·Synthesis·저장·보고서 참조를 검사한다. Xid/SXid JSON은 검색·계획 실행과 미검증 코드의 supported 승격 방지를 검사한다. 최신 결과와 fixture 경계는 [Agent QA](../../agents/QA.md)를 따른다. editable 설치 전에는 다음 명령으로 소스 경로를 지정할 수 있다.

~~~powershell
python -c "import sys; sys.path[:0]=['rcca-agent/src','shared/python/src','ops-agent/src']; import pytest; sys.exit(pytest.main(['-c','agents/pytest.ini','agents/tests/test_runbook_contract.py','agents/tests/test_runbook_retrieval.py','-q']))"
~~~

병행 RCA 작업의 후속 조사 대상은 Fleet image 1.5.0-rc.1의 accelerator-nvidia-error-xid, accelerator-nvidia-error-sxid, accelerator-nvidia-infiniband, accelerator-nvidia-nvml, accelerator-nvidia-nccl, accelerator-nvidia-peermem이다. 정확한 upstream 및 실제 로그 계약은 확인 전이다. labels.reason/component는 검색 단서로 정규화하며, k8s_node_name/machine_id/PCI BDF를 GPU UUID로 추측하지 않는다. suggested_actions는 외부 권고이며 수행 증거가 아니다. NAT의 병렬 실행·예산·재조사·합성은 orchestrator가 관리하며 이 콘텐츠 검증기는 실행 방식을 결정하지 않는다.

운영 발행 전 남은 조건:

1. CPC별 producer 계약·GPU 모델·버전·라벨·대상·freshness를 검증하고 compatibility를 채운다.
2. D09/D05 원본에서 같은 대상의 producer_contract/error_code/상태를 생성하는 parser와 evidence 참조를 검증한다. D02는 보조 사용률이며 원인이나 회복 증거로 단독 사용하지 않는다.
3. ECC 동반 코드의 순서·모델별 수치 판단은 별도 query/parser/조건 기능이 마련된 후 확장한다.
4. 부족·충돌·수집 실패·잘못된 대상 사건으로 RCA 통합 검증 후 기존 draft → in_review → reviewed → published 절차를 거친다.

Backend는 생성/PATCH 시 v1 구조를 검사하고 approve/publish 시 빈 compatibility를 거부한다. `code` 필터는 legacy `content.code`와 v1 `search.codes`를 정확히 조회한다. 테이블·컬럼·인덱스 추가는 없다. 동적 query registry/procedure 허용 목록은 관리 CLI와 Worker에서 검증하며, 형식 검사만으로 운영 호환성을 승인하지 않는다. [등록 절차와 검증 책임](DB-WORKFLOW.md)을 따른다.

설계 기준: [RCA 모듈 설계서](../../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md), [Runbook 설계 초안](../../docs/specs/rca-agent/drafts/gpu-node-rca-runbook-design.md).
