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

[incident_dossier.py](src/rcca_agent/incident_dossier.py)의 30분 로그·지표 비교는 D44/D47을 포함한 해당 발행 계획에서 제공한다. 기존 발행본의 의미·조회를 자동으로 새 revision 내용으로 바꾸지 않는다. 비교 자료가 필요하면 검수된 최신 계획을 발행해야 하지만, 평가 제거 자체에는 새 발행이 필요하지 않다.

- 첫 라운드: 고정 cutoff를 넘지 않는 조회 종료 시각까지 30분의 같은 노드 XID/SXID 로그(D09)와 관련 메트릭을 기존 Grafana MCP binding·공유 예산으로 함께 수집한다. XID 79는 PCIe replay(D44), 사용률(D02), 전력(D11); SXID 11001은 Fabric Manager 원시 상태 코드(D47), NVLink 수신/송신(D33/D34)이다. 알림 일치와 LLM 예산 부족도 이 수집을 생략시키지 않는다.
- 이력: RCA 전용 `RcaStore`가 기존 저장소 context를 읽은 뒤 별도 읽기 전용 트랜잭션에서 같은 host의 최근 14일 Incident를 가져온다. scope·cluster와 machine ID(없으면 node)를 고정하고 최대 500건을 저장한다. 사건 최초 snapshot의 코드·사유와 사건 ID를 사용한다. 현재 로그의 반복 전달 건수와 등록 사건 수를 합치지 않는다. 같은 cutoff로 기간을 제한하지만 두 DB 읽기가 하나의 트랜잭션은 아니다. 이력은 원본 evidence로 고정한다. 이전 기간 Loki/메트릭 재조회는 하지 않는다.
- 대상: XID는 각 원문의 `gpuInfo.gpus`와 PCI를 대조해 UUID가 유일하게 대응할 때만 GPU 이력·지표를 연결한다. 이는 보고된 재고의 연결이며 독립 실장비 검증이 아니다. SXID는 같은 machine/node·스위치 PCI(function 포함)를 비교하고 GPU 지표는 노드 참고값으로 표시한다. 다른 노드 조회는 추가하지 않는다.
- 고정 보고 자료: 이번 구간의 코드·메시지별 처음/마지막 보고와 원문 refs, 대상 GPU 관련 지표의 최소·최대·마지막 값·단위·표본 수를 코드로 만든다. 보고서 UI는 호스트 Incident 표를 최근 7일/14일과 코드로 필터링하고 사건 원문으로 연결한다. GPU UUID는 사건 target 또는 XID 원문에 유일하게 명시된 UUID를 표시한다. 메트릭은 클러스터·노드와 XID GPU 대응을 요구하고, machine_id 라벨이 있으면 충돌을 배제한다. 노드가 없는 경우 machine_id 일치를 요구한다. 반복은 호스트 전체 코드별 집계와 GPU UUID·오류 코드별 집계를 함께 제공한다. GPU UUID가 없는 사건만을 호스트 전체 건수로 표시하지 않는다. 보고 구간을 장애 지속 시간이나 재부팅·복구 증거로 바꾸지 않는다. 모델 실패에도 표와 공식 지침은 남는다.
- 단일 수집: 이 경로는 observation plan 전체를 한 라운드에서 실행한다. 여러 MCP 호출을 하나의 수집 단계로 묶는 것이며 단일 HTTP 요청을 뜻하지 않는다. D09 재시도·모델의 추가 조회 선택은 실행하지 않는다. `required_queries` 필드는 기존 발행 계약 호환과 새 계획 식별에만 남기며 이 경로의 필수/선택 수집 분기로 쓰지 않는다.
- NVIDIA Node Triage는 자동 복구 절차가 아닌 보고서 순서(사건·관련 관측·반복 이력·다음 대응)에 적용한다. Xid 79는 업무 배제와 진단 자료 확보/지원 전달, SXid는 Fabric Manager 메시지·스위치/포트·플랫폼별 지침을 연결한다. 새 계획의 작성 입력은 원본 출처별로 제한한 최대 24KB 뷰를 사용해 운영에서 관측된 32,768토큰 종료에 대비해 출력 여유를 확보한다. 이는 라우터의 설정 한도를 확정한 값이 아니다. 전체 원문은 evidence에 보존하며 이 상한 자체가 모델 성공을 보장하지는 않는다. Nemotron 작성은 수집 자료의 비교·관계·반복 양상 분석에 집중하고 수치·정렬·집계는 코드가 담당한다. 별도 모델 성능 우열이나 GPU 진단 전문성을 가정하지 않는다.

## 관측과 판단의 경계

- 수집은 여러 MCP 요청으로 구성된 한 단계다. DB 이력과 MCP가 단일 트랜잭션/HTTP 요청인 것은 아니다.
- 원본 evidence와 발행 내용·hash는 보존한다. 모델에는 크기가 제한된 뷰와 실제 근거 ID를 전달한다.
- 로그 수신 건수·보고 구간을 독립 장애 횟수·실제 장애 지속 시간·복구 증거로 바꾸지 않는다. SXid 스위치 주소를 GPU 주소로 대체하지 않는다.
- 기존 수집 계약과 노드·GPU 범위 검증을 유지하며 미지원 binding을 클러스터 전체 조회로 우회하지 않는다. 실제 장비 조치는 사람이 수행한다.

## 보고서와 조회 호환

보고서는 사건 요약 → 분석 결과·런북 권고 → 관련 로그·메트릭 → host 이력 → 원문 상세 순서다. 평가 상태·goal 달성 여부·근거 충분성·평가 예약 예산은 보고서 패널로 표시하지 않는다. 과거 저장 원문은 수정하지 않는다.

기존 JC·Ops 소비자와의 계약을 변경하지 않기 위해 `quality.rca_evaluation` envelope는 유지한다. `review`는 항상 `skipped/not_requested`, 판정 `null`, 근거 목록 빈 배열이며 평가 성공을 뜻하지 않는다. `investigation.stop_reason=no_available_followup`은 기존 enum 호환값이다. 현재 실행에는 후속 조회나 goal 판정이 없다. 실제 수집·작성 상태는 collection·evidence·synthesis와 원문에 남는다.

[decision_policy.py](src/rcca_agent/decision_policy.py)는 기존 발행 JSON의 구조 검증만 맡는다. 목적 달성 판정 함수는 제거했다. 구 결과의 검토 계약 회귀를 위한 [legacy_review_fixtures.py](../agents/tests/legacy_review_fixtures.py)는 테스트 전용이며 Worker 패키지에 포함되지 않는다. Ops 구현·공통 결과 검증기를 변경하지 않는다.

## Runbook 관리

- [목록](runbooks/CATALOG.md) · [등록·검토·발행](runbooks/DB-WORKFLOW.md) · [구조 계약](src/rcca_agent/runbook_contract.py).
- 오프라인 계약 검사는 `python -m rcca_agent.runbook_audit --help`로 입력 형식을 확인한다. 운영 DB를 변경하거나 발행하지 않는다.
- `python -m rcca_agent.runbook_transition --snapshot published.json --profile profile.json --output new-review-directory`는 제공된 발행 snapshot으로 전환 검토안을 만든다. 입력 hash를 확인하고 새 출력 폴더만 사용한다. Backend 호출·승인·발행은 없다.
- [265개 전환 검토](runbooks/transition-review-20261014.json)는 196개 계약 통과 제안과 69개 보류(정의 미확정 64개·정보성 5개)를 기록한다. 의미 검토·운영 발행 완료를 뜻하지 않는다. 원인·필수 근거·출처를 보존하고 발행 전 최신 revision/hash와 다시 대조해야 한다.

## 오프라인 RCA 재생

[rca_replay.py](../agents/tests/rca_replay.py)는 실제 Worker 흐름을 고정 조회·모델 응답으로 실행한다. 과거 `review_*` 사례는 테스트 폴더의 구 결과 호환 fixture만 실행한다. 실제 Grafana·Nemotron·DB 공개 검증을 대신하지 않는다. 출력은 합성·비식별 자료로 `.local/`에 둔다.

```bash
python agents/tests/rca_replay.py --case enough_budget --output .local/rca-replay/current
python -m pytest -c agents/pytest.ini agents/tests/test_rca_no_evaluation.py -q
```

## 실행·검증·남은 과제

설치·실행 설정은 [공통 Agent 안내](../agents/README.md), 검증 범위는 [Agent QA](../agents/QA.md)를 따른다. 과거 [평가 분리 설계](../docs/specs/rca-agent/11_RCA_Agent_모듈_설계서.md#평가-분리-설계개발)는 저장 결과 호환을 읽는 참고이며 현재 실행 단계는 위 설명을 따른다. 운영 데이터·Nemotron 응답·공개 보고서 품질은 배포 후 별도 확인한다.
