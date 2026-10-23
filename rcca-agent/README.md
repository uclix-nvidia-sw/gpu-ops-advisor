# RCA Agent

Incident가 접수한 장애의 로그·메트릭·host 이력을 모아 보고서를 작성한다. 코드 변경, 운영 배포와 Runbook revision 발행은 별도 단계다.

RCA의 출발점은 Fleet Intelligence가 판단한 장애다. 수집 목적은 장애 여부를 다시 판정하기 위한 근거 확보가 아니라, 로그·메트릭·DB 이력을 분석한 장애 보고서 작성이다. LLM은 같은 대상의 시간적 변화, 동반 오류와 메트릭의 관계, 과거 구간과의 차이와 반복 양상을 분석하고 디버깅 우선순위를 설명한다. 오류 정의와 런북 권고를 나열하는 데 그치지 않는다. 관측을 넘는 원인 단정과 수치 조작은 허용하지 않으며, 인과관계가 성립하지 않아도 유의미한 비교 분석을 제공한다.

## 현재 실행 흐름

1. JC claim의 사건 snapshot·대상·기간·예산·지식 revision을 고정한다. [workflow.py](src/rcca_agent/workflow.py)가 실행 경로를 소유한다.
2. [retrieval.py](src/rcca_agent/retrieval.py)에서 발행 Runbook을 선택하고 [runbook_contract.py](src/rcca_agent/runbook_contract.py)로 내용 hash·조회 ID·대상 적용 조건을 검사한다.
3. 선택한 observation plan을 한 번의 수집 단계에서 실행한다. 과거 발행본의 `required_queries`는 계획이 없는 경우의 입력 호환 필드이며 필수/선택 평가나 두 번째 수집 라운드로 이어지지 않는다. 실제 쿼리는 기존 binding·scope·query budget·deadline·동시성 제한을 따른다. 대상 식별이 충돌하면 조회 범위를 넓히지 않고 수집을 중단한다.
4. 대상 host가 식별되면 저장된 Incident 이력을 읽어 원본 evidence로 고정한다. 알람과 로그의 코드·PCI·UUID 대조 결과는 작성 자료다. 일치한다고 분석을 건너뛰거나 불일치한다고 새 조회를 선택하지 않는다.
5. [통합 작성](src/rcca_agent/combined_synthesis.py)에서 증거 해석과 분석·권고 자료를 한 번의 LLM 요청으로 작성한다. 과거 profile의 `generation_mode=separate`도 별도 해석 호출을 추가하지 않는다. 구조·근거 참조·식별자·숫자 표현은 코드로 검증하며, 잘못된 항목과 이에 의존하는 가설을 제외한다. HTTP 오류·출력 잘림에도 재전송하지 않는다.
6. [analysis_material.py](src/rcca_agent/analysis_material.py)와 `rca_result_frozen`에서 자료와 hash를 고정한다. [report_writer.py](src/rcca_agent/report_writer.py)는 이 자료만 사용해 보고서 LLM을 한 번 호출한다. 원본을 다시 조회하거나 새 원인을 추가하지 않는다. 작성 실패 시 같은 관측·런북 지침의 기본 보고서를 제공한다. Worker가 후보를 제출하고 JC가 기존 완료 검증 후 공개한다.

이 흐름은 **모든 RCA Runbook 발행본**에 적용한다. Xid 79/D44 또는 SXid 11001/D47 존재 여부가 평가 활성화 조건이 아니다. `analysis_review` 호출·평가 토큰 예약·평가 피드백 재작성·goal 판정·보완 조회 선택·런북 확장·별도 해석 LLM은 Worker에서 제거했다. 조회·작성·공개 실패와 원문 참조 검증은 유지한다. 정상적인 모델 실행은 작성 1회와 보고서 1회이며, 모델 미설정·예산 부족이면 실제 호출 수는 줄 수 있다.

## Xid 79·SXid 11001 비교 자료

[incident_dossier.py](src/rcca_agent/incident_dossier.py)의 30분 로그·지표 비교는 `required_queries`에 보고서 메트릭(`METRICS`)을 가진 XID/SXID 발행 계획에서 제공한다. D09만 필수인 기존 발행본은 기존 경로를 유지한다. 같은 쿼리·GPU 시계열은 exporter의 파드 라벨로 나뉘어도 하나로 합치고, 그 라벨은 `gpus`(모델·드라이버·PCI·GPU 번호)와 `workloads`(namespace·pod·container와 관측 구간, 할당이 아닌 관측)로 남긴다. GPU 모델은 DCGM의 `modelName`과 Fleet의 `model_name` 라벨을 모두 읽는다. 파드 라벨은 DCGM exporter 지표에만 있으므로, 그런 지표가 없으면 `workload_label_source`를 비워 파드 없음과 구분한다. `gpus`·`workloads`는 같은 노드의 모든 GPU를 담아 한 파드가 함께 쓰는 GPU와 다른 작업을 보이게 하고, 지표 비교는 XID면 알림 GPU만 쓴다. `onset`은 같은 노드·컴포넌트의 마지막 Healthy 보고와 첫 Unhealthy 보고(Loki 기록 시각)다. 알림 대조에서 kmsg 이벤트가 없더라도 구간 안에 Healthy→Unhealthy 전환이 있으면 `event_not_exported`(결손 아님)로, 전환도 없으면 기존 `event_not_found`로 기록한다. 기존 발행본의 의미·조회를 자동으로 새 revision 내용으로 바꾸지 않는다. 비교 자료가 필요하면 검수된 최신 계획을 발행해야 하지만, 평가 제거 자체에는 새 발행이 필요하지 않다.

- 첫 라운드: 고정 cutoff를 넘지 않는 조회 종료 시각까지 30분의 같은 노드 XID/SXID 로그(D09)와 관련 메트릭을 기존 Grafana MCP binding·공유 예산으로 함께 수집한다. XID 79는 PCIe replay(D44), 사용률(D02), 전력(D11); SXID 11001은 Fabric Manager 원시 상태 코드(D47), NVLink 수신/송신(D33/D34)이다. 그 밖의 코드는 오류 유형별 계획(ECC D36·D38·D40·D42·D23, 전원 D11·D48·D45·D04 등)을 쓰며 목록은 [Runbook CATALOG](runbooks/CATALOG.md#운영자-보고서-지침과-조회-계획-2026-10-22-개정)에 있다. 누적 카운터(ECC·PCIe replay)와 코드형 값(D45 비트마스크·D47)은 각각 counter·enum으로 표시한다. 알림 일치와 LLM 예산 부족도 이 수집을 생략시키지 않는다.
- 이력: RCA 전용 `RcaStore`가 기존 저장소 context를 읽은 뒤 별도 읽기 전용 트랜잭션에서 같은 host의 최근 14일 Incident를 가져온다. scope·cluster와 machine ID(없으면 node)를 고정하고 최대 500건을 저장한다. 사건 최초 snapshot의 코드·사유와 사건 ID를 사용한다. 현재 로그의 반복 전달 건수와 등록 사건 수를 합치지 않는다. 같은 cutoff로 기간을 제한하지만 두 DB 읽기가 하나의 트랜잭션은 아니다. 이력은 원본 evidence로 고정한다. 이전 기간 Loki/메트릭 재조회는 하지 않는다.
- 대상: XID는 각 원문의 `gpuInfo.gpus`와 PCI를 대조해 UUID가 유일하게 대응할 때만 GPU 이력·지표를 연결한다. 이는 보고된 재고의 연결이며 독립 실장비 검증이 아니다. SXID는 같은 machine/node·스위치 PCI(function 포함)를 비교하고 GPU 지표는 노드 참고값으로 표시한다. 다른 노드 조회는 추가하지 않는다.
- 고정 보고 자료: 이번 구간의 코드·메시지별 처음/마지막 보고와 원문 refs, 대상 GPU 관련 지표의 최소·최대·마지막 값·단위·표본 수를 코드로 만든다. 보고서 UI는 호스트 Incident 표를 최근 7일/14일과 코드로 필터링하고 사건 원문으로 연결한다. GPU UUID는 사건 target 또는 XID 원문에 유일하게 명시된 UUID를 표시한다. 메트릭은 클러스터·노드와 XID GPU 대응을 요구하고, machine_id 라벨이 있으면 충돌을 배제한다. 노드가 없는 경우 machine_id 일치를 요구한다. 반복은 호스트 전체 코드별 집계와 GPU UUID·오류 코드별 집계를 함께 제공한다. GPU UUID가 없는 사건만을 호스트 전체 건수로 표시하지 않는다. 보고 구간을 장애 지속 시간이나 재부팅·복구 증거로 바꾸지 않는다. 모델 실패에도 표와 공식 지침은 남는다.
- 단일 수집: 이 경로는 observation plan 전체를 한 라운드에서 실행한다. 여러 MCP 호출을 하나의 수집 단계로 묶는 것이며 단일 HTTP 요청을 뜻하지 않는다. D09 재시도·모델의 추가 조회 선택은 실행하지 않는다. `required_queries` 필드는 기존 발행 계약 호환과 새 계획 식별에만 남기며 이 경로의 필수/선택 수집 분기로 쓰지 않는다.
- NVIDIA Node Triage는 자동 복구 절차가 아닌 보고서 순서(사건·관련 관측·반복 이력·다음 대응)에 적용한다. Xid 79는 업무 배제와 진단 자료 확보/지원 전달, SXid는 Fabric Manager 메시지·스위치/포트·플랫폼별 지침을 연결한다. 새 계획의 작성 입력은 원본 출처별로 제한한 최대 24KB 뷰를 사용해 운영에서 관측된 32,768토큰 종료에 대비해 출력 여유를 확보한다. 이는 라우터의 설정 한도를 확정한 값이 아니다. 전체 원문은 evidence에 보존하며 이 상한 자체가 모델 성공을 보장하지는 않는다. Nemotron 작성은 수집 자료의 비교·관계·반복 양상 분석에 집중하고 수치·정렬·집계는 코드가 담당한다. 별도 모델 성능 우열이나 GPU 진단 전문성을 가정하지 않는다.

작성 입력의 `incident_brief`는 보존된 전체 표본에서 사건 전후 구간·단위·장치·메트릭 종류를 계산하고, 로그 보고 건수와 현재 사건을 제외한 DB 반복 이력을 구분한다. enum 매핑이 없는 값은 건강 상태나 심각도로 해석하지 않는다. 샘플링된 원문만으로 연속성·최댓값을 추정하지 않는다. 채택된 사건별 해석은 보고서 재작성에서 수치·의미가 바뀌지 않도록 고정한다. `value_token`은 장치·단위·값·실제 측정 구간을 코드가 만든 문구로 치환한다. 작성 모델은 해당 토큰과 원문 refs를 인용하고 의미를 설명한다. 등록되지 않은 숫자는 계속 거절한다. 같은 노드 GPU의 동일 측정 요약은 장치 목록을 보존한 채 묶어 입력 한도를 줄인다. 유일한 생산자 발생 시각이 있으면 이를 전후 구간 기준으로 쓰며, 없거나 여럿이면 알림 시각을 사용하고 기준을 명시한다. 독립된 미확인 항목 목록은 처리 상세에 두고 관측의 적용 범위는 분석 문장에 유지한다.

SXID 수집에서는 D47(없으면 같은 수집의 D33/D34)로 해석된 Grafana datasource·cluster selector·node 라벨을 재사용해 `pci_bus_id`를 MCP `query_prometheus`로 조회한다. 알림·오류 로그의 PCI 전체 주소를 정규화하여 같은 노드의 해당 주소만 조회하며 함수 번호도 비교한다. 공유 query budget·deadline·응답 상한을 사용하고 원문을 `nvswitch_pci_inventory` evidence로 보존한다. 일치하는 시계열이 없으면 로그의 스위치 주소를 유지한다. PCI 라벨의 관측은 장치 건강이나 GPU 인덱스 대응을 뜻하지 않는다. D47 datasource/노드 binding이 없으면 임의 원천으로 우회하지 않는다.

이전 RCA는 같은 노드의 이력에 속한 사건 중 cutoff 이전에 완료·발행된 최신 결과를 읽는다. 결과 ID·hash·job 링크·partial 여부와 원인 후보를 보존한다. 작성 입력은 동일 장치·동일 코드의 이전 RCA를 비교 자료로 사용하며 과거 후보를 현재 사실이나 수행된 조치로 승격하지 않는다.

LLM 단계 실패 처리: 결합 분석과 보고서 작성은 요청 1회를 유지하되 HTTP 429·500·502·503·504만 1초 뒤 1회 재시도한다. 그래도 HTTP 400·500이고 설정된 출력 상한이 8,192 토큰보다 크면 출력 상한 8,192로 한 번 더 요청한다(`reduced_output_retry`, 게이트웨이가 라우팅 모델의 출력 한도를 넘는 요청을 거절하는 경우). 실패하면 `http_status`와 게이트웨이 오류의 클래스·한도 종류(`error_type`, 예: `BadRequestError:output_tokens`)만 진단 기록에 남기며 오류 본문 문장은 저장하지 않는다. 결합 분석의 문장이 숫자 규칙(`numeric`)으로 모두 버려지면 고정 피드백으로 1회 다시 요청하고 같은 입력으로 다시 검증한다(`numeric_repair`). 그 밖의 같은 근거 재작성은 하지 않는다.

## 관측과 판단의 경계

- 수집은 여러 MCP 요청으로 구성된 한 단계다. DB 이력과 MCP가 단일 트랜잭션/HTTP 요청인 것은 아니다.
- 원본 evidence와 발행 내용·hash는 보존한다. 모델에는 크기가 제한된 뷰와 실제 근거 ID를 전달한다.
- 로그 수신 건수·보고 구간을 독립 장애 횟수·실제 장애 지속 시간·복구 증거로 바꾸지 않는다. SXid 스위치 주소를 GPU 주소로 대체하지 않는다.
- 기존 수집 계약과 노드·GPU 범위 검증을 유지하며 미지원 binding을 클러스터 전체 조회로 우회하지 않는다. 실제 장비 조치는 사람이 수행한다.

## 보고서와 조회 호환

보고서 화면 구성은 [Frontend README](../frontend/README.md)의 고정 6단 구성(한눈에 보기 → 대응 순서 → 관련 로그·메트릭 → 분석 및 해석 → 이전 사건 이력 → 참고 자료)을 따른다. 평가 상태·goal 달성 여부·근거 충분성·평가 예약 예산은 보고서 패널로 표시하지 않는다. 과거 저장 원문은 수정하지 않는다. 분석·비교 설명과 공식 참고 자료는 펼쳐진 본문으로 제공하며, 수집 원문과 처리 진단만 접을 수 있다. UUID를 임의의 GPU 번호로 바꾸지 않는다. 신규 실행은 `investigation_decision` 단계를 생성하지 않으며 완료 참조는 해당 `rca_analysis_draft`를 가리킨다.

기존 JC·Ops 소비자와의 계약을 변경하지 않기 위해 `quality.rca_evaluation` envelope는 유지한다. `review`는 항상 `skipped/not_requested`, 판정 `null`, 근거 목록 빈 배열이며 평가 성공을 뜻하지 않는다. `investigation.stop_reason=no_available_followup`은 기존 enum 호환값이다. 현재 실행에는 후속 조회나 goal 판정이 없다. 실제 수집·작성 상태는 collection·evidence·synthesis와 원문에 남는다.

[decision_policy.py](src/rcca_agent/decision_policy.py)는 기존 발행 JSON의 구조 검증만 맡는다. 목적 달성 판정 함수는 제거했다. 구 결과의 검토 계약 회귀를 위한 [legacy_review_fixtures.py](../agents/tests/legacy_review_fixtures.py)는 테스트 전용이며 Worker 패키지에 포함되지 않는다. Ops 구현·공통 결과 검증기를 변경하지 않는다.

## Runbook 관리

- [목록](runbooks/CATALOG.md) · [등록·검토·발행](runbooks/DB-WORKFLOW.md) · [구조 계약](src/rcca_agent/runbook_contract.py).
- 오프라인 계약 검사는 `python -m rcca_agent.runbook_audit --help`로 입력 형식을 확인한다. 운영 DB를 변경하거나 발행하지 않는다.
- `python -m rcca_agent.runbook_transition --snapshot published.json --profile profile.json --output new-review-directory`는 제공된 발행 snapshot으로 전환 검토안을 만든다. 입력 hash를 확인하고 새 출력 폴더만 사용한다. Backend 호출·승인·발행은 없다.
- [265개 전환 검토](runbooks/transition-review-20261014.json)는 196개 계약 통과 제안과 69개 보류(정의 미확정 64개·정보성 5개)를 기록한다. 의미 검토·운영 발행 완료를 뜻하지 않는다. 원인·필수 근거·출처를 보존하고 발행 전 최신 revision/hash와 다시 대조해야 한다.

## 비코드 Fleet 오류와 평가

XID/SXID가 없는 Fleet 컴포넌트 알림(disk, cpu, DCGM 건강 점검, InfiniBand 등)은 Runbook 1.2의 컴포넌트 목표로 처리한다. 검색은 `decision_policy.applies_when.reported_component`가 알림의 `component` 라벨과 정확히 같을 때만 허용한다. 사유 문자열은 여러 패턴이 쉼표로 묶이거나 같은 구간의 Healthy `ok` 보고와 섞이므로 컴포넌트 Runbook의 게이트로 쓰지 않는다. 보고 지침은 D09에서 같은 대상·컴포넌트의 Unhealthy 보고가 확인될 때 `matched`가 되어 보고서의 다음에 할 일에 실린다.

D09 보고는 `health_contracts.fleet-component-log-v1.components`에 등록된 컴포넌트만 파싱한다. 저장소 기본 프로필(`agents/config.example.json`과 차트 사본)은 XID/SXID 외에 컴포넌트 Runbook이 있는 17개 컴포넌트를 `component`로 등록한다. 등록만으로 현재 상태·원인 fact가 생기지 않는다(Healthy는 매핑이 없어 unknown). 비코드 사건은 XID/SXID 전용 30분 비교 자료와 6단 운영자 화면을 만들지 않으며, 평가 호출·추가 조회 선택도 하지 않는다. 운영 반영에는 새 프로필 배포와 컴포넌트 Runbook의 검토·발행이 각각 필요하며, 발행은 Worker가 등록된 프로필로 실행되고 [컴포넌트 알림 규칙](../incident/README.md#grafana-알림-규칙)이 켜진 것을 확인한 뒤에 한다. 등록 전에 발행하면 컴포넌트 Runbook이 보류 상태로 선택돼 일반 조사 Runbook을 대신하고 지침도 표시되지 않는다. 목록은 [CATALOG](runbooks/CATALOG.md#fleet-컴포넌트-runbook)를 따른다.

## 오프라인 RCA 재생

[rca_replay.py](../agents/tests/rca_replay.py)는 실제 Worker 흐름을 고정 조회·모델 응답으로 실행한다. 과거 `review_*` 사례는 테스트 폴더의 구 결과 호환 fixture만 실행한다. 실제 Grafana·Nemotron·DB 공개 검증을 대신하지 않는다. 출력은 합성·비식별 자료로 `.local/`에 둔다.

```bash
python agents/tests/rca_replay.py --case enough_budget --output .local/rca-replay/current
python -m pytest -c agents/pytest.ini agents/tests/test_rca_no_evaluation.py -q
```

## 실행·검증·남은 과제

설치·실행 설정은 [공통 Agent 안내](../agents/README.md), 검증 범위는 [Agent QA](../agents/QA.md)를 따른다. 과거 [평가 분리 설계](../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md#평가-분리-설계개발)는 저장 결과 호환을 읽는 참고이며 현재 실행 단계는 위 설명을 따른다. 운영 데이터·Nemotron 응답·공개 보고서 품질은 배포 후 별도 확인한다.
