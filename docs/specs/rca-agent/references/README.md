# RCA Agent 런북 작성 참고자료

이 디렉터리는 GPU 노드 RCA Agent의 실행 가능한 runbook을 작성할 때 사용하는 검토 자료를 보관한다. 현재 실행 계약과 우선순위는 상위 [RCA Agent 모듈 설계서](../11_RCA_Agent_모듈_설계서.md)를 따른다.

## 문서

- [Domain·Category·메트릭 매핑](domain-category-metric-mapping.md): 검색된 runbook 후보를 검증할 때 Domain·Category별로 조회할 metric·event·log 후보와 관측 순서를 정리한다.
- [런북 근거자료 카탈로그](runbook-source-catalog.md): 공식 문서, 조건부 자료, 보조 자료와 제외할 출처를 구분한다.

## 적용 범위

- 이 자료는 실행 가능한 runbook, 확정된 Knowledge DB seed, 새 DB schema가 아니다.
- `source-verified`는 소스 또는 공식 문서의 정의를 확인했다는 뜻이며, 현재 CPC에서 데이터가 수집된다는 뜻이 아니다.
- CPC-1·CPC-2에서 metric 존재 여부, label, unit, type, freshness와 장비 capability를 확인한 뒤 `observed`로 기록한다.
- 승인된 query ID, target binding, lookback, predicate와 부족한 증거 처리를 검증한 경우에만 `runbook-validated`로 기록한다.
- Agent는 권고와 근거를 제시하며 reset, reboot, power-cycle, 격리 같은 device remediation을 자동 실행하지 않는다.

## 기준

- 저장소 기준 commit: `d2007ff362127fb315647e17c163369341657ea1`
- 자료 검토일: 2026-09-22
- 기존 현장 근거는 [수집 환경 근거](../../../evidence/README.md)와 [GPU 메트릭 대조 목록](../../../evidence/GPU_메트릭_대조목록_20260915.md)을 참조한다.

외부 문서의 `latest` URL은 탐색용이다. runbook revision을 발행할 때는 실제 적용 제품과 software version, 문서 revision 또는 확인일, 근거 위치를 함께 보존한다.
