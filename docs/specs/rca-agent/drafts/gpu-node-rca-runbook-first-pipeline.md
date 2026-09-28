# GPU 노드 RCA Agent: Runbook-first BM25 파이프라인

> 2026-09-22 통합 안내: 현행 개발 기준은 [11. RCA Agent 모듈 설계서](../11_RCA_Agent_모듈_설계서.md)다. 아래는 제안과 당시 검증 이력이다. §6의 BM25 미구현 표현은 현재 기준으로 **검색 모듈 구현·workflow 미연결**이며 §9와 구분해 읽는다. 예시 query ID·UI 입력·YAML을 그대로 운영 계약으로 적용하지 않는다.

상태: 팀 검토용 설계 · 운영 코드/DB 미반영 · 작성일: 2026-09-21

2026-09-23 후속 합의: 전체 workflow와 종료·LLM·저장 계약은 [11번 문서 §2](../11_RCA_Agent_모듈_설계서.md#2-처리저장)를 따른다. 아래 조사 흐름은 그 합의에 맞춰 보완했으며 §6·§9의 과거 구현·검증 기록을 새 실행 결과로 바꾸지 않는다.

검증 범위: 사용자 제공 main (4) ZIP과 knowledge-db-reference 브랜치 ZIP. 검증에서 확인한 수정사항을 본문과 검색 코드에 반영했다. 현재 실행 가능한 부분은 독립 `retrieval.py`의 검색과 테스트이며, 전체 workflow 연결은 추가 구현 대상이다. example YAML은 NAT에서 로드하는 실행 설정이 아니다. 구현 범위와 검증 결과는 이 문서의 9절에 정리했다.

## 요약

GPU 노드 RCA Agent는 JC에서 작업을 claim하고 고정된 사건·증거·지식으로 조사를 시작한다. 먼저 DB 조회·결정적 검색(BM25 포함)으로 Runbook을 찾고 코드로 적용 조건을 검사한다. **기존 증거가 조사 목적까지 충족하면 MCP·LLM을 생략**한다. 부족하면 Runbook의 필요한 D코드 또는 등록 일반 조사로 수집 계획을 만들고, **수집 → 증거 정리 → LLM 분석 → 코드 검증·재평가 → 필요 시 재조사**한다. LLM 분석은 Runbook이 있는 추가 수집 경로에도 적용하며, 새로운 가설 조사의 진입 조건과 구분한다.

```text
Incident snapshot → JC claim → 목적·범위·기존 증거·지식 고정
  → Runbook DB 조회·결정적 검색 → 코드로 적용/증거 조건 검사
      ├─ 기존 증거 충분: 코드로 원인 후보·근거·권고 작성 (MCP·LLM 0회)
      └─ 부족 / 미일치: Runbook D코드 또는 등록 일반 조사로 계획
          → Grafana MCP → 정규화·품질 확인
          → 유효 증거가 있으면 LLM 분석 → 코드 검증·Runbook 재평가
              ├─ 목적 충족: 분석 결과 작성
              ├─ 추가 조회·예산 있음: 계획 보완 → 수집·분석 반복
              └─ 더 조사 불가: 부족·상충·종료 사유를 담은 미확정 결과
  → 공통 최종 검증 → evidence·candidate 저장 → JC complete·공개
  → Backend 이력 조회 / Report Agent가 공개 결과 참조
```

여기서 “런북이 매칭됐다”는 BM25 점수가 높다는 뜻이 아니다. **검색 후보가 됐고 적용 조건을 증거로 통과했다**는 뜻이다. BM25는 텍스트 검색 결과만 제공하며 원인 확률이나 조치 안전성을 의미하지 않는다.

모든 후보가 반증되면 가설 경로로 이동한다. 관측 실패·stale·식별자 누락 때문에 확인하지 못한 경우는 `insufficient_evidence`로 보류한다. 데이터 부족을 원인 가설의 근거로 사용하지 않는다. 한 webhook의 여러 Alert는 Incident에서 대상·시각별로 분리해야 한다. 검증과 관측은 후보별로 반복하며, 검색 앞에 전체 조사 계획 생성 단계를 두지 않는다.

유효한 기존·신규 증거가 전혀 없으면 근거 없는 LLM 분석 대신 추가 조회 가능성을 확인하고 불가능하면 미확정 종료한다. 모델 오류·검증 실패 시 분석 완료로 표시하지 않는다. 모든 정상 결과 경로는 저장·공개까지 수행하고 저장 실패·취소·lease 만료·원격 추론 종료 불명은 14의 실행 계약으로 처리한다.

## 1. 온톨로지에서 차용하는 것과 제외하는 것

제공된 인강 코드와 문서에서 다음 운영 원칙은 차용할 가치가 있다.

- 지식의 타입과 스키마를 명시하고 입력·출력을 검증한다.
- 지식과 action을 revision으로 관리하고, 검토된 내용만 published 상태로 사용한다.
- 실행 주체, 입력, 결과, 근거와 변경 이력을 감사 기록으로 남긴다.
- 조회 도구와 action을 allowlist로 제한하고, handler와 metadata의 계약을 함께 관리한다.
- Agent의 제안과 실제 실행을 분리하고 사람이 승인할 수 있게 한다.

다음 요소는 이번 GPU RCA에 도입하지 않는다.

- 범용 `object_type`·`property`·`link` 메타모델
- 객체 관계를 순회하는 ontology API와 schema prompt 주입
- GPU, 노드, 사건, 메트릭을 범용 ontology object로 변환하는 계층
- ontology action dispatcher를 통한 자동 복구

대신 기존 `knowledge_revisions`의 `runbook`, `data_dictionary`, `reference`, `policy`를 사용한다. GPU/node/metric 관계는 Incident snapshot과 관측 결과에 필요한 만큼만 명시한다. 강의의 코드는 구조적 참고 자료이며 그대로 이식하지 않는다.

## 2. 런북 검색 전에 만드는 검색 문서

검색 입력은 Alert 원문을 통째로 LLM이 요약한 문자열이 아니다. 재현 가능한 규칙으로 다음 필드를 모은다.

| 필드 | 예시 | 검색 사용 |
|---|---|---|
| `error_codes` | `xid:79`, `sxid:11012` | 가장 높은 boost |
| `event_names` | `gpu_fallen_off_bus`, `row_remap_failure` | 높은 boost |
| `alertname` | `GPUXidError` | 중간 boost |
| `summary`/`message` | 원본 Alert·Loki 메시지 | 기본 BM25 |
| `producer` | `fleet-intelligence`, `dcgm-exporter` | 검증된 contract의 호환성 검사; 현재 lexical 검색에서는 제외 |
| `cluster_id` | `cpc-1` | 검색 점수보다 적용 범위 필터 |
| `gpu_model` | `A100-SXM4-80GB`, `V100-PCIE-16GB` | 적용 범위 필터 |
| `node`/`gpu_uuid` | 실제 식별자 | 증거 조회용이며 본문 검색에는 사용하지 않음 |
| `input_origin` | `grafana`, `ui`, `fault_injection` | provenance 기록; 원인 점수에는 사용하지 않음 |

정규화 규칙은 원문을 보존한 채 별도 필드에 적용한다. `XID 79`, `Xid:79`, `xid_79`는 검색 토큰 `xid:79`를 추가한다. 대소문자, `_`/`-`, 알려진 NVIDIA 이름과 내부 별칭은 alias 사전으로 정규화한다. 일반 숫자는 오류 코드로 승격하지 않는다. Fault injection 입력은 실제 장애처럼 검색하되 결과에 `synthetic=true`를 계속 표시한다.

## 3. BM25가 검색하는 런북 문서

신규 작업은 접수 시 published이고 scope가 허용된 runbook revision을 고정한다. 실행 시에는 claim의 revision/hash와 검토 hash를 검사한다. 현행 저장소는 접수 후 retired가 된 지식도 이미 고정된 작업의 재현을 위해 읽는다. 신규 검색의 retired 제외와 기존 작업의 고정 revision 재생을 구분해야 한다. 이 검증은 호출부의 책임이며 현재 검색 함수에는 DB·권한·hash 검증이 없다. 한 런북의 검색 문서는 다음 필드를 결합한다.

```json
{
  "knowledge_key": "gpu.xid.79.fallen_off_bus",
  "title": "Xid 79: GPU fallen off the bus",
  "domain": "GPU_DEVICE",
  "category": "GPU_ACCESS_LOST",
  "codes": ["xid:79"],
  "aliases": ["fallen off the bus", "gpu access lost", "gpu disappeared"],
  "symptoms": ["nvidia-smi cannot access gpu", "device missing"],
  "supported_models": ["A100", "V100"],
  "producer_events": ["fleet-intelligence event name if verified"],
  "source_refs": ["pinned NVIDIA/gpud source revision"]
}
```

실험 가중치는 `codes 8`, `producer_events 5`, `aliases 4`, `title/category 3`, `symptoms 2`, 설명 본문 `1`이다. 수정 모듈은 필드별 BM25 점수를 계산한 뒤 가중 합산한다(BM25F 구현은 아님). query 중복은 제거하고 exact boost는 `search.codes`에 선언된 코드에만 부여한다. 설명에 비교·인용된 코드는 exact boost 대상이 아니다. Xid/SXid를 서로 구분하며 `Xid (PCI:0000:07:00): 79` 형식도 읽는다.

scope/hash는 검색 전 검사한다. 검증된 GPU 모델·producer contract 등은 호환성 필터에 쓸 수 있지만, unknown 값은 자동 탈락시키지 않고 후보별 최소 관측으로 확인한다. Alert의 임의 label을 검증된 contract로 승격하지 않는다.

초기 실험값은 `top_k=5`, exact boost `12`, BM25 `k1=1.2`, `b=0.75`다. 점수는 corpus에 따라 달라지므로 `min_score`는 평가 데이터로 결정한다. 현재 함수는 양의 점수 후보를 최대 top-k개 반환하며, 낮은 점수 거절·동점 확장·가설 전환·corpus fingerprint는 아직 없다. 한글은 형태소 분석 없는 단순 토큰 분리이므로 조사·동의어 recall을 검증해야 한다. 이 숫자를 운영 기준으로 확정한 것은 아니다.

## 4. 전체 파이프라인

### 4.1 입력 고정과 기본 검증

Incident snapshot의 hash, incident time, 허용된 cluster/time range를 고정한다. Grafana Alert, UI 요청, fault injection 모두 Incident 계약을 거쳐야 한다. Alert label은 신뢰되지 않은 단서로 시작하고 실제 관측을 거쳐 typed fact가 된다.

### 4.2 런북 후보 검색

1. 허용 scope와 접수 시 고정된 published revision/hash를 만족하는 런북을 가져온다.
2. 선언된 `search.codes`와 사건 코드의 exact 일치를 찾는다. 이벤트 이름은 BM25에 사용하고 별도 exact boost는 현재 없다.
3. 같은 후보군에서 BM25를 실행한다.
4. exact boost와 BM25 점수를 결합하되 각각을 결과에 따로 기록한다.
5. top-k와 동점 후보를 다음 단계에 넘긴다.

저장할 검색 근거는 `query_text_hash`, tokenizer/index revision, corpus revision, 후보별 BM25 점수, exact match, rank다. 원문 Alert의 민감값을 검색 로그에 중복 저장하지 않는다.

### 4.3 적용 조건 검증

상위 후보마다 다음을 확인한다.

- CPC, GPU 모델/세대, MIG, NVSwitch/Fabric Manager 조건
- 요구되는 error code와 동반 코드의 시간 순서
- 요구 메트릭·로그의 존재, freshness, 단위, GPU UUID/node identity
- 제외 조건과 반증
- source binding이 해당 CPC에서 `value_verified` 또는 허용된 검증 상태인지

조건을 통과한 런북만 `applicable`이다. `retrieved`, `applicable`, `rejected`, `insufficient_evidence`를 구분해 기록한다. 검색 결과가 있어도 필요한 데이터가 stale이면 매칭 성공으로 처리하지 않는다.

### 4.4 런북 경로

기존 증거가 Runbook 조건·품질과 선택된 조사 목적을 충족하면 추가 관측·LLM 없이 결과를 작성한다. 부족하면 `required_queries` 또는 추가 구현할 `observation_plan`에서 필요한 query를 계획하고 허용 범위·예산을 검사한다. 수집 후 유효 증거는 LLM 분석으로 이어지고, 코드가 근거 참조·원인 수준·Runbook 조건을 재검증한다. 첫 묶음의 분석으로 목적을 충족하면 확장 조회를 멈추고, 부족하면 유효한 추가 조회·예산이 있을 때만 반복한다. NVIDIA/gpud/Fleet action은 원문·버전·전제조건을 유지하며 `execution='not_performed'`로 남긴다.

#### 원천 suggested/repair action을 우선 재사용한다

**해당 장애에 gpud 또는 Fleet Intelligence의 `suggested_actions`·`repair_actions`가 정의되어 있으면 최대한 그대로 가져와 사용한다.** 원천 action이 있고 현재 장비·버전에 적용 가능한 경우, LLM이 같은 조치를 새로 작성하는 대신 그 action을 참조한다. 원천에 없는 절차와 현장 보충 사항은 내부 런북으로 작성한다.

- action 이름/ID(제공되는 경우), 원문 payload와 문구, 순서, 전제조건을 보존한다. 원문 배열의 순서를 지키되 그것이 실행 순서인지 대안 목록인지는 원천 의미를 따른다.
- 저장소·파일 경로·고정 commit/버전 및 확인 날짜를 기록한다. 실제 사건에서 수신한 action은 원본 이벤트 evidence도 연결한다.
- 한국어 설명·내부 운영 조건은 원문과 분리한다. 수정하거나 적용하지 않을 때는 변경 내용과 이유를 남긴다.
- 적용 조건이 불명확하거나 NVIDIA 지침과 충돌하면 임의로 합성하지 않고 검토 대상으로 남긴다. action의 존재가 실행 승인이나 원인 확정을 의미하지 않는다.

현재 구현 상태는 **재사용 원칙을 설계에 반영한 단계**다. gpud/Fleet action 전체 추출·DB 적재·참조 해결·권고 연결은 아직 구현하지 않았다.

#### Category별로 밀접한 메트릭과 데이터를 먼저 조회한다

**사건이 특정 장애 Category의 후보로 분류되면, 그 Category에 연결된 우선 관측부터 조회한다.** Category는 조회 대상을 좁히는 단서이며 확정된 원인은 아니다. BM25 런북 검색을 먼저 하고, 후보 런북의 적용 조건을 검증하는 시점부터 Category별 우선 관측을 사용한다. 처음부터 모든 도메인의 데이터를 수집하는 조사 계획을 만들지 않는다.

```text
BM25 런북 후보
  → 후보의 Category
  → Category별 우선 관측 + 런북 고유의 필수 증거
  → meaning_id → 해당 CPC의 source binding → 등록된 query_id
  → Grafana MCP로 Mimir/Loki 조회 → 증거 정리 → LLM 분석
  → 코드로 적용 조건·원인 후보 검증 → 종료 또는 계획 보완
```

관측 항목에는 `priority`, `meaning_id`, `query_id`, 조회 대상·기간, 단위, freshness, 판정 목적과 누락 시 동작을 기록한다. GPU 온도처럼 같은 의미의 Fleet/Exporter 메트릭이 있으면 검증된 primary binding을 사용하고, 허용된 조건에서만 fallback한다. Field ID는 binding 검증 근거이며 Agent가 Mimir 값에서 추측하지 않는다.

예를 들어 `GPU_ACCESS_LOST`는 Xid 원문·장치 접근 상태·동시 PCIe 오류를 먼저 보고, `ECC_DBE`는 ECC 데이터·동반 Xid와 메모리 복구 상태를 먼저 본다. `OVER_TEMPERATURE`는 `gpu.temperature.celsius`와 온도 한계·throttle 원인을 먼저 확인한다. 실제 metric 이름과 event 필드는 CPC별 binding에서 확인한다. 이름이 정의되어 있다는 이유만으로 수집 중이라고 간주하지 않는다.

Category 공통 관측은 기본 순서를 제공하고 런북 고유의 필수 증거는 생략하지 않는다. 복수 Category가 후보이면 필요한 관측을 합쳐 중복 query를 제거하고, 우선순위와 query budget에 따라 단계적으로 조회한다. 런북이 없을 때도 가설의 Category를 이용해 밀접한 관측부터 선택한다. 데이터가 없거나 stale이면 해당 판단을 보류하며 조회 실패를 새로운 원인의 증거로 사용하지 않는다.

현재 구현 상태는 **Category별 우선 조회 관계를 설계한 단계**다. 전체 Category→메트릭/query 매핑의 적재·검증과 순서 실행은 아직 구현하지 않았다.

### 4.5 가설 경로

이 절의 진입 조건은 **새로운 가설 조사**에 관한 것이다. Runbook이 있으나 증거가 부족한 경로도 수집 후 §4.4의 LLM 분석을 거친다. Runbook이 없으면 등록 일반 조사로 기본 증거를 먼저 확보하고, 유효 증거 안에서 후보와 구분용 query를 제안한다. 검색 점수 임계값은 검수·설정되기 전까지 실행 분기로 사용하지 않는다.

다음 중 하나면 가설 경로로 전환한다.

- 검색 결과가 없음
- 최고 후보가 평가된 임계값보다 낮음
- 모든 후보가 호환성/제외 조건에서 탈락
- 필요한 증거를 조회했지만 모든 후보가 반증됨

가설은 자유 서술 한 덩어리가 아니라 다음 계약을 가진다.

```json
{
  "hypothesis_id": "generated:<incident-id>:1",
  "claim": "PCIe 경로 또는 GPU 장치 접근 상실 가능성",
  "domain": "GPU_DEVICE",
  "supporting_clues": ["evidence-ref"],
  "contradicting_clues": [],
  "discriminating_queries": ["registered-query-id"],
  "confirmation_rule_ref": null,
  "status": "candidate",
  "missing_inputs": ["causal_confirmation_evidence"]
}
```

Agent는 장애 Domain/Category와 현재 증거를 이용해 최대 N개의 가설을 만들고, 가설 사이를 가장 잘 구분하는 **등록된 읽기 전용 query**만 선택한다. 가설이 plausible하다는 이유로 조치하지 않는다. 검토된 confirmation rule이 없으면 `confirmed`가 될 수 없다. 미해결 사건 결과는 추후 런북 초안의 입력이 될 수 있지만 자동 publish하지 않는다.

검색 장애·hash 불일치·scope 거부·관측 실패는 검색 미매칭과 구분해 오류/보류로 종료한다. 위 가설 JSON은 중간 표현이다. 저장 전에 현행 `cause_candidates`의 `id`, `causal_status`, `supporting_refs`, `contradicting_refs`, `missing_inputs` 등으로 변환하고 ref를 검증하는 adapter가 필요하다.

### 4.6 종료

결과에는 원인 후보·판단 수준·지지/반박 refs·목적별 평가·부족 입력·권고·종료 사유를 기록한다. 검색 후보와 탈락 이유, Runbook/query/model revision, LLM 사용/생략/실패, 계획 보완과 종료 결정은 기존 evidence snapshot/quality와 실행 기록에 연결한다. Runbook 단독·추가 수집/LLM·미확정 모두 최종 검증 → evidence·candidate 저장 → JC complete·공개를 거친다. 공개 결과만 Backend·보고서가 사용하며 미확정 원인을 확정으로 바꾸지 않는다.

종료 사유는 evidence_sufficient, missing_data, conflicting_evidence, unsupported_source, budget_exhausted, query_failed 등 기존 값을 유지한다. 데이터 부족의 유효한 부분/보류 결과와 저장 실패·취소·lease 만료 같은 실행 실패를 구분한다. 모든 실패 직전 중간 증거의 영속화를 보장하지 않으며, 유효 lease 없이 저장·공개하지 않는다.

## 5. 런북 content 최소 계약

초기에는 새 테이블보다 `knowledge_revisions(kind='runbook')`의 versioned `content`를 사용한다.

R코드는 Agent의 조사 목적이며 아래 Runbook의 필수 필드가 아니다. 필요한 fact는 `required_evidence`, 실행 관측은 실제 등록 D코드인 `required_queries`/`observation_plan`으로 연결한다. LLM 입력·출력과 충분 판정·재조사 기준은 11 §2를 따르며 Runbook마다 별도 실행 엔진이나 자유 SQL을 두지 않는다.

```json
{
  "schema": "gpu-rca-runbook/1.0",
  "title": "Xid 79: GPU fallen off the bus",
  "classification": {"domain": "GPU_DEVICE", "category": "GPU_ACCESS_LOST"},
  "search": {
    "codes": ["xid:79"],
    "aliases": ["fallen off the bus", "gpu access lost"],
    "symptoms": ["device missing"]
  },
  "required_evidence": ["error_code", "producer_contract"],
  "applicability_conditions": [
    {"field": "error_code", "equals": "xid:79"}
  ],
  "exclusion_conditions": [],
  "observation_plan": [
    {"priority": 1, "query_id": "GPU_XID_EVENTS", "purpose": "원문·GPU UUID·시각 확인"},
    {"priority": 2, "query_id": "GPU_INVENTORY_STATE", "purpose": "장치 접근 가능 여부 확인"},
    {"priority": 3, "query_id": "PCIE_ERROR_COUNTERS", "purpose": "동시 PCIe 이상 확인"}
  ],
  "claim": "GPU가 PCIe bus에서 이탈했을 가능성이 있습니다.",
  "recommendations": [
    {
      "text": "운영자가 작업 사용 중지 가능 여부를 확인하고 벤더 제출용 증거를 수집합니다.",
      "source_action_ref": "nvidia:gpu-node-triage:xid-79",
      "preconditions": [{"field": "error_code", "equals": "xid:79"}],
      "execution": "not_performed"
    }
  ]
}
```

조건은 현행 `{field, equals}`를 유지했다. 시간 순서·threshold는 추가 구현 대상이다. `observation_plan`과 위 query ID 3개는 제안이며 현행 registry에 없다. workflow는 `required_queries`만 읽고 procedure allowlist와 교차 검사하므로, 이 예시를 바로 발행해서는 동작하지 않는다. source action 참조 해결도 추가해야 한다. Kubernetes drain/cordon 실행은 GPU 노드 RCA 범위에 넣지 않는다.

## 6. 현행 코드와의 차이

현재 `rcca-agent`는 고정된 compatible runbook을 모두 순회해 적용 조건을 검사하고, applicable 런북이 없으면 procedure의 기본 query를 실행한다. **BM25 검색, 검색 점수 근거, 명시적 가설 객체, 코드 시간 순서 조건은 구현되어 있지 않다.** 현재 Loki query도 런북별 event pattern을 표현하지 않고 scope selector 중심이다.

통합 시 추가로 해결할 사항이 있다. `incident_source()`는 Grafana 입력을 `{alert: ...}`로 반환하므로 상위 producer contract가 없다. `compatible_runbooks()`는 비어 있지 않은 compatibility를 source 상위 필드와 비교하므로 그 결과를 그대로 BM25에 넘기면 후보가 사라질 수 있다. `health_facts()`는 `error_code`도 생성하지 않는다. parser와 unknown 처리, 관측 후 호환성 재평가를 함께 구현해야 한다. query는 set으로 모아 이름순으로 실행하므로 현재는 priority도 보존하지 않는다. 기존 Pod 연결 procedure는 그대로 존재하므로 GPU 노드 전용 query/purpose 제한 역시 필요하다.

이번 모듈은 workflow·DB·Helm·NAT 실행 설정을 변경하지 않는다. 제공 main ZIP의 Grafana 시간 정밀도·조회 처리 개선은 그대로 유지해야 한다.

따라서 변경 순서는 다음이 안전하다.

1. `gpu-rca-runbook/1.0` validator와 검색 문서 생성기를 추가한다.
2. published/pinned/scope-compatible revision만 대상으로 deterministic BM25 index를 만든다.
3. exact code boost와 top-k 결과를 evidence에 저장한다.
4. retrieval과 applicability를 분리하고 탈락 사유를 저장한다.
5. ECC·Xid·NVLink·IB 등 등록 query와 parser를 추가한다.
6. 새로운 가설 조사는 런북 미매칭/유효 반박 조건에서 제한한다. 2026-09-23 보완 기준에서는 런북이 있는 추가 수집 경로에도 LLM 분석·검증·재조사를 연결하고, 기존 증거 충분 경로에는 MCP·LLM 0회와 공통 저장을 구현한다.
7. golden incident 세트로 recall@k, wrong-runbook rate, abstention, evidence completeness를 평가한다.

## 7. 평가와 운영 기준

최소 평가 세트에는 CPC-1 A100 40/80GB, CPC-2 V100, 같은 문구의 producer 차이, 코드만 있는 Alert, 코드 없는 자연어 Alert, stale/missing 데이터, 복합 Xid, fault injection을 포함한다.

| 평가 항목 | 의미 |
|---|---|
| recall@5 | 정답 런북이 후보 5개 안에 있는 비율 |
| applicability precision | 실제 조건을 통과한 런북 중 적절한 비율 |
| wrong-runbook rate | 틀린 런북을 적용한 비율 |
| abstention quality | 증거 부족 때 안전하게 보류한 비율 |
| evidence completeness | 결론·권고가 유효한 evidence ref를 가진 비율 |
| source fidelity | 외부 action의 출처·revision·전제가 보존된 비율 |

BM25 `min_score`, field boost, top-k는 이 평가 결과로 고정하고 revision을 붙인다. 런북 내용이나 tokenizer가 바뀌면 index revision과 회귀 평가를 다시 만든다.

## 8. 팀이 결정할 사항

1. BM25 구현 위치(애플리케이션 또는 BM25 지원 엔진/확장)를 결정한다. PostgreSQL 기본 full-text의 `ts_rank`를 BM25로 표기하지 않는다. 혼합 언어 tokenizer와 index 재현성을 함께 검증한다.
2. 오류 코드 exact lookup을 별도 컬럼/테이블로 정규화할지, versioned JSON content에서 추출할지 결정한다.
3. `top_k`, 동점 처리, 미매칭 기준, 최대 가설 수와 query budget을 golden set으로 확정한다.
4. Fleet `/state`·`/event` 직접 조회를 추가할지 결정한다. 현재 기준 관측 경로는 Grafana MCP를 통한 Mimir/Loki다.
5. 가설 결과를 사건 결과에만 둘지 `case` 지식으로 검토 큐에 보낼지 결정한다. 어떤 경우에도 자동으로 published 런북이 되지 않는다.

## 9. 현재 구현 범위와 검증 결과

### 구현된 부분

- Alert의 지정된 단서 필드로 검색 입력을 만든다. node/UUID/시각·임의 `verified_facts` 블록은 검색 대상에서 제외한다.
- 필드별 BM25 점수를 가중 합산하고 query 중복을 제거한다.
- `search.codes`에 선언된 Xid/SXid만 exact boost 대상으로 삼는다. 실제 `Xid (PCI:…): 79` 형식을 처리하고 두 코드 namespace를 구분한다.
- 점수 구성요소와 tokenizer revision을 반환한다. 잘못된 top-k와 음수·NaN·무한대 boost는 거부한다.

이 동작은 [검색 모듈](../../../../rcca-agent/src/rcca_agent/retrieval.py)에 구현되어 있다. [example YAML](../../../../rcca-agent/configs/runbook-first-pipeline.example.yml)은 전체 흐름에 대한 설계용 명세이며, 이 파일을 놓는 것만으로 운영 Agent가 새 흐름을 실행하지 않는다.

### 통합할 부분

| 구성요소 | 현재 상태와 다음 작업 |
|---|---|
| 지식 로딩 | 호출부에서 scope·고정 revision·검토 hash를 검사해 검색 후보를 공급해야 함 |
| producer/오류 코드 fact | Grafana 단서와 실제 관측을 연결하는 parser, 대상·시각 검증 필요 |
| 적용 조건 | unknown 호환성의 후보 유지와 관측 후 재평가 필요 |
| 우선 관측 | 미등록 query 추가, `observation_plan` 변환과 순서 보존 필요 |
| 원천 action 재사용 | gpud/Fleet 원문 추출·버전 고정·적재·참조 해결 및 권고 연결 필요 |
| 가설 경로 | 생성기, query 제한, 현행 결과 계약으로의 adapter 필요 |
| 분석·종료·저장 | 기존 증거 충분 시 LLM 0회; 수집 증거 기반 LLM 분석·검증·재조사; 세 결과 경로의 공통 저장·JC 공개. 기존 설명용 fact ID 선택과 구분 |
| 검색 품질 | 임계값·한글/동의어·복합 오류·동점 처리 평가 필요 |
| 운영 경계 | GPU 노드용 query/purpose 제한, 운영 표본을 이용한 E2E 필요 |

관련 구현은 [workflow](../../../../rcca-agent/src/rcca_agent/workflow.py), [Incident/결과 모델](../../../../shared/python/src/agent_common/contracts.py), [health parser](../../../../shared/python/src/agent_common/parsers.py), [고정 지식 조회](../../../../shared/python/src/agent_common/store.py), [query registry](../../../../agents/config.example.json)를 따른다. 현행 개발 순서는 [11번 문서 §7](../11_RCA_Agent_모듈_설계서.md#7-개발-상세와-검수-순서)이 우선이며 아래 검증 기록은 당시 검색 모듈의 검증 범위다.

### 저장소와의 호환성

| 비교 자료 | 검증한 commit |
|---|---|
| main (4) ZIP | `886ed8e43fadd35a4387dfceb6ebb3bccf8aba40` |
| knowledge-db-reference ZIP | `18553d2c60ff57f389f15a27810ffc68a846c14e` |

두 commit의 `git merge-tree --write-tree`는 충돌 없이 성공했다. main의 Grafana 시간 변환·조회·Helm 변경이 유지되는 것을 확인했다. 이는 위 두 snapshot에 대한 결과이며 향후 commit까지 보장하지 않는다. 실제 병합이나 원격 반영은 수행하지 않았다.

### 수행한 검증

| 검증 | 결과 |
|---|---|
| 검색 회귀 테스트 | 수정 모듈 및 첨부 main에 신규 파일을 추가한 환경에서 각각 **18개 통과** |
| CI와 같은 Ruff 0.14.0 lint/format | 신규 Python 2개 파일 통과 |
| YAML 문법·설정/코드 정합성 | 파싱 통과, 가중치·tokenizer revision 일치 |
| 문서 JSON 예시 | 3개 파싱 통과 |
| 상대 링크·코드 블록 | 확인 완료 |
| patch 적용 검사 | reference ZIP 기준 `git apply --check --whitespace=error` 통과 |

운영 Mimir/Loki/DB E2E는 전체 workflow 연결과 실제 배포 표본 검증이 필요해 수행하지 않았다. 컨테이너 빌드·Helm·migration은 이번 변경에 실행 경로·배포·DB 수정이 없어 수행하지 않았다. 검색 단위 테스트 통과를 운영 RCA 파이프라인 전체 검증으로 해석하지 않는다.

### 개발자가 다시 검증하는 명령

Python 3.12 환경의 저장소 루트에서 실행한다.

```powershell
python -m pip install pytest PyYAML ruff==0.14.0
$env:PYTHONPATH='rcca-agent/src'
python -m pytest agents/tests/test_runbook_retrieval.py -q
python -m ruff check rcca-agent/src/rcca_agent/retrieval.py agents/tests/test_runbook_retrieval.py
python -m ruff format --check rcca-agent/src/rcca_agent/retrieval.py agents/tests/test_runbook_retrieval.py
python -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('rcca-agent/configs/runbook-first-pipeline.example.yml').read_text(encoding='utf-8'))"
git merge-tree --write-tree 886ed8e43fadd35a4387dfceb6ebb3bccf8aba40 18553d2c60ff57f389f15a27810ffc68a846c14e
```

통합 후 전체 테스트는 기존 설치 절차를 마친 환경에서 `python -m pytest -c agents/pytest.ini agents/tests -q`로 실행한다. 실제 프로세스 E2E는 `RUN_AGENT_E2E=1`과 전용 테스트 DB/JC/Incident/Grafana MCP를 준비하고 [CI 테스트 절차](../../../../.github/workflows/tests.yml)를 따른다.

공유 파일은 본 문서·런북 작성 기준·example YAML·검색 모듈·테스트의 5개다. 제공 patch의 기준은 reference commit `18553d2`이며 main에 적용할 때는 먼저 reference 문서 변경을 병합한다.

## 10. 참고 자료

- [기존 Knowledge DB 참고 설계](knowledge-db-reference.md)
- [GPU 노드 런북 설계 초안](gpu-node-rca-runbook-design.md)
- [NVIDIA GPU Node Triage](https://docs.nvidia.com/deploy/gpu-debug-guidelines/gpu-node-triage.html)
- [NVIDIA Xid Errors](https://docs.nvidia.com/deploy/xid-errors/latest/index.html)
- [gpud 고정 revision components](https://github.com/leptonai/gpud/tree/9606bb8f6813fdd944cc9a349566e35075917805/components)

사용자가 제공한 GitBook 페이지는 이 실행 환경에서 직접 열리지 않았다. 제공된 인강 ZIP의 코드와 문서에서 revision, metadata/handler 계약, typed action, proposal/review, audit 원칙을 확인해 위와 같이 제한적으로 차용했다.
