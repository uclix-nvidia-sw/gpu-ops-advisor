# 수집 환경 근거

현행 설계의 데이터 가용성 판단에 필요한 기록과 DCGM Field catalog를 보존한다. 과거 명세·화면 시안·중복 ZIP은 Git 이력으로 확인한다.

- CPC-2 기록: Alloy 직접 수집·GPU↔Pod UID 검증, 마지막 재배포 뒤 Loki 확인 대기 등 실제 확인 범위.
- 메트릭 대조 목록: Exporter/Fleet 필드의 이름·출처·표본 등장 여부. 현재 활성 지표 전체 목록을 뜻하지 않는다.
- [CPC-1](dcgm/cpc-1-dcgm-dmon-field-catalog.txt)·[CPC-2](dcgm/cpc-2-dcgm-dmon-field-catalog.txt) DCGM Field catalog: `dcgmi dmon --list` 출력. 실제 수집된 sample이나 Mimir 시계열 목록을 뜻하지 않는다.

내용은 당시 기록이며 최신 환경 상태를 보장하지 않는다. v1.3에서 사용할 값·기간·CPC·단위는 [데이터 설계](../../output/deliverables-20260917-v1.3/03_데이터_설계서.md)와 [배포 원장](../../output/deliverables-20260917-v1.3/06_배포_운영_인계서.md)에서 재확인한다.

출처 기준 Git 커밋: `84c01c023f8b307fa6e8af41d891d52ec8d25730`. 아래 SHA-256은 이동 전 원문 바이트의 지문이다. 현 열람본은 이 안내와 현행 상대 링크를 추가했으므로 지문이 다르다.

| 보존 기록 | 이동 전 원문 SHA-256 |
|---|---|
| [CPC-2_수집검증_20260915.md](CPC-2_수집검증_20260915.md) | `3c43883e565db9762bf852b1cbdd4066e0ac378a932864b89139401bdfa21a14` |
| [GPU_메트릭_대조목록_20260915.md](GPU_메트릭_대조목록_20260915.md) | `d26abf95cae4e43e83c6343f1770f6be98b72032a1a4cdbffb25294a2df3b230` |
