# 생산자별 메트릭 의미와 근거

이 문서는 Runbook과 D binding에서 생산자별 관측을 구분하는 기준이다. 별도 Knowledge DB ontology·테이블·Fleet 직접 API가 구현됐다는 의미가 아니다. 실행 binding은 [공통 D 런타임](../../common/d-binding-runtime.md), DB 구조는 [데이터 계약](../../common/03_데이터_설계서.md)을 따른다.

## 같은 의미와 같은 관측의 구분

Fleet `dcgm_fi_dev_gpu_temp`와 DCGM Exporter `DCGM_FI_DEV_GPU_TEMP`는 검토한 소스에서 DCGM Field ID 150을 사용한다. 이름의 대소문자만 비교한 결론이 아니다. 같은 Field ID라는 근거가 있어도 서로 다른 producer의 장비·시각·라벨·무효값·지원 상태·실측값이 같다는 증거는 아니다.

두 생산자의 표본을 합산하거나 독립된 장애 근거로 중복 가산하지 않는다. 선택한 binding과 출처를 기록하고, fallback은 해당 환경에서 검증된 계약이 허용할 때만 적용한다. 원천 값 0, 미관측, 지원하지 않는 값, 잘린 응답을 구분한다.

## 확인할 근거

- [메트릭 매핑](domain-category-metric-mapping.md): 도메인·카테고리와 원천 메트릭 관계.
- [CPC binding 조사](../../../evidence/d-binding-cpc-20261006.md): 실제 원본의 형태와 당시 검증 범위.
- [Fleet/DCGM 문서 대조](../../../evidence/fleet-dcgm-pdf-audit-20261006.md): 문서·생산 코드·원본 관측의 차이.
- [CPC-1 field catalog](../../../evidence/dcgm/cpc-1-dcgm-dmon-field-catalog.txt) · [CPC-2 field catalog](../../../evidence/dcgm/cpc-2-dcgm-dmon-field-catalog.txt).

소스 정의 확인, 실제 관측 확인, Runbook 판단에 사용할 수 있는지의 검증은 별개다. 해당 배포의 단위·표본 시각·신원·reset·유효값 계약을 확인한 범위만 판단에 사용한다.
