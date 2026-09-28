# XID·SXID Runbook 전체 작성 목록

기준일: 2026-09-28. 이전 PR #15의 대표 오류 3건을 전체 코드 자료 범위로 확장했다. **XID 173건 + SXID 93건 = 오류별 266건**, 일반 GPU 노드 조사까지 **267건**이다. 기존 3건을 유지·보강하고 263건을 추가했다. 모든 파일은 기존 Knowledge API의 v1 JSON 봉투이며 새 DB 테이블이나 migration은 없다.

## 파일 구성

```text
runbooks/
  RB-GENERAL-GPU-NODE.json
  xid/RB-XID-*.json
  sxid/RB-SXID-*.json
  catalog-manifest.json
```

JSON에는 코드별 증거·분기·조치 조건·출처만 남긴다. DB 등록, 승인 정책, 런타임 역할, parser/query의 개발 상태 같은 공통 설명은 이 문서와 [DB-WORKFLOW](DB-WORKFLOW.md)에서 관리한다. 반복 설명 정리로 analysis_guidance와 limitations의 전체 글자 수를 약 61% 줄였다. 수집 품질·대상 일치, 문헌과 수행 증거의 구분, 자동 조치 금지는 기존 Worker 계약으로 유지한다.

## 자료 범위와 작성 결과

- 기존 [Fleet·GPUd 카탈로그](../../docs/specs/rca-agent/references/fleet-gpud-error-catalog.md): XID 172개·SXID 92개를 모두 포함했다. 저장소별 중복 정의를 별도 Runbook으로 늘리지 않았다.
- NVIDIA 최신 Xid 표의 **133**과 고정 GPUd 소스의 **SXID 22012**를 추가했다. 따라서 이번 합집합은 기존 264개보다 2개 많다.
- 기존 `RB-XID-48-63-64`의 검색 진입은 계속 **XID 48만**이다. XID 63과 64에는 각각 독립 콘텐츠를 작성했다. 동반 코드 관계는 조사 지침이며 equality 조건식의 자동 시간 판정 기능을 추가한 것은 아니다.
- 범위는 제공된 자료의 XID/SXID 코드다. NCCL·InfiniBand·OS·디스크의 비코드 조건형 Runbook이나 아직 자료에 없는 오류를 모두 작성했다는 의미는 아니다.

각 파일은 코드 의미·출처별 event/action·적용 제품·필요 로그/메트릭·대상/시각·판별 절차·조건부 권고·부족 시 처리·조치 후 확인을 담는다. 앱/펌웨어/ECC/PCIe/NVLink/전원/가상화/정보 이벤트/NVSwitch/미정의 코드로 필요한 증거를 구분했다. 공통 문장에 코드 번호만 바꾼 항목이 아니라 코드별 출처 및 필요한 분기를 포함한다. 다만 Reserved/Unused처럼 원문에 절차가 없는 항목은 원문·버전을 확인하는 절차까지 작성하고 진단 규칙을 만들지 않았다.

## 출처 간 차이와 판정 제한

| 자료 상태 | 건수 | 의미 |
|---|---:|---|
| Unused·구세대 정의 확인 (`unused_or_legacy`) | 63 | 최신 Xid 표의 Unused. 구세대/Fleet 의미를 현행 장비에 바로 적용하지 않음 |
| 문헌/소스 정의 (`documented`) | 187 | 참조 자료에 정의가 있음. 운영 검증 완료를 뜻하지 않음 |
| 정의 차이 확인 (`definition_conflict`) | 13 | 현재 NVIDIA 표와 고정 Fleet의 정의 차이. 배포 버전 확인 전 전문 조치 보류 |
| 코드 소스만 확인 (`source_only`) | 3 | 참조 코드에는 있으나 이번 공식 표에서 직접 대응 항목을 확인하지 못함 |

특히 XID 142는 고정 Fleet/GPUd의 ECC 설명과 최신 NVIDIA의 NVENC3 설명이 다르다. XID 126–132·134–136·139·141은 고정 Fleet의 Reserved와 최신 표의 정의가 다르다. XID 173, SXID 20009·22012는 코드 소스 근거와 공식 표의 범위를 분리했다. 미기재 action을 IGNORE로 변환하지 않는다.

SXID 10003은 GPUd EventType=Warning이어도 PotentialFatal/AlwaysFatal=true다. 이벤트 등급만으로 영향 범위를 결정하지 않는다. SXID 11001 등의 PotentialFatal은 source port의 access/trunk·VM/partition에 따라 판단하고, AlwaysFatal 그룹은 해당 FM 운영 모드의 전체 fabric 영향과 복구 전제를 설명한다. Single-bit ECC, TX replay, 열 시작/종료, 계획되지 않은 shutdown, 무시 가능한 interrupt는 별도 절차를 사용한다.

XID 144–150에는 NVIDIA Table 2의 버전별 decoder 행을 보존했다. R575 이전 V1과 이후 V2, intrInfo/errorStatus·action2·Xid154/동반 link-down 조건을 구분한다. 이것은 검토 가능한 문헌 지침이며 실행 중인 비트/시간 predicate 구현이 아니다. XID 74의 Hopper 레지스터 분기도 해당 문헌/장비 범위에 한정한다.

## DB 등록 및 실행 범위

**267건 모두 `investigation_only: true`, `compatibility: {}`인 작성 초안**이다. 파일과 문헌 검토 범위의 콘텐츠 작성은 끝냈으며 실제 환경 연결은 별도 작업이다. Backend에 draft로 등록할 수 있고 적용 조건을 검수하기 전 승인·발행·RCA 런타임 적용은 차단한다. 환경 조건을 채워 발행한 뒤에도 조사용 콘텐츠 자체를 supported 원인·조기 완료·최종 eligible 조치의 근거로 쓰지 않는다.

현재 실행 가능한 공통 계획은 D09 원본 로그, D05 상태, D02 선택 사용률이다. Runbook이 추가로 요구하는 PCIe AER/ECC 카운터/FM 토폴로지/전력·열/앱 재현 자료는 운영 query와 parser가 실제 제공하는지 확인해야 한다. 임의의 D코드나 metric 이름을 만들지 않았으며 미연결 증거는 missing_inputs로 남긴다. 실제 조치 자동 실행은 없다.

전체 또는 종류별 draft 일괄 등록은 [runbook_import.py](../src/rcca_agent/runbook_import.py)를 사용한다. 재귀 검사·중단 후 재개·429 대기를 지원한다. 파일별 등록·revision·검토·발행·retire 명령은 [DB 등록 안내](DB-WORKFLOW.md)를 따른다. 예: `python -m rcca_agent.runbook_admin check rcca-agent/runbooks/xid/RB-XID-63.json --profile agents/config.example.json`. draft는 명시적 Backend 주소와 파일별 request key를 사용한다. 같은 knowledge_key가 이미 있으면 기존 knowledge_id의 새 revision으로 등록한다. 운영 적용 범위가 다른 파일에 fixture compatibility를 일괄 복사하지 않는다.

## 다른 PC에서 검토·수정하는 방법

[manifest](catalog-manifest.json)에 모든 코드→파일→knowledge_key, 근거 상태, NVIDIA 적용 제품/조치 분류, GPUd fatality와 참조 원문 SHA-256을 기록했다. 원문의 SHA는 수집 시점 식별용이며 운영 장비의 버전 증거가 아니다. 원문 HTML/Go 다운로드와 작업용 생성 도구는 `.local`에만 있으며 실행/DB 등록에 필요하지 않다. **Git에 있는 JSON 자체가 검토·수정할 작성 원본**이다. 런타임 자동 생성이나 자동 seed는 없다.

추가/수정 시 해당 JSON의 sources·checked_at·지침·limitations와 manifest를 함께 갱신한다. 기존 발행본은 덮어쓰지 않고 새 DB revision을 만든다. 다음 검사로 카탈로그 전체 누락·추가 코드·정확 검색·잘못된 원인/조치 승격 방지 계약을 확인한다.

```sh
python -m pytest -c agents/pytest.ini agents/tests/test_runbook_catalog.py agents/tests/test_runbook_contract.py -q
python tools/check_links.py
```

Backend 검증기도 전체 267개 JSON을 검사한다. 실제 DB E2E는 기존 migration의 격리 DB에서 신규 263건을 실제 일괄 등록 CLI로 draft 적재하고 재실행 시 중복 쓰기를 건너뛰는지 및 코드별 조회/hash를 확인하며, 기존 3건의 검토·발행·RCA 소비 검사를 계속 수행한다. 테스트 DB는 종료 후 재사용하지 않는다. 운영 DB 등록은 수행하지 않았고 모든 266건을 실제 장비에서 조사·회복 검증한 것은 아니다. 실제 실행 결과는 [Agent QA](../../agents/QA.md), [Backend QA](../../backend/QA.md)를 따른다.

## 코드별 파일

| 코드 | Runbook | 증거 그룹 | 자료 상태 |
|---|---|---|---|
| `xid:1` | [RB-XID-1](xid/RB-XID-1.json) | reserved | Unused·구세대 정의 확인 |
| `xid:2` | [RB-XID-2](xid/RB-XID-2.json) | reserved | Unused·구세대 정의 확인 |
| `xid:3` | [RB-XID-3](xid/RB-XID-3.json) | reserved | Unused·구세대 정의 확인 |
| `xid:4` | [RB-XID-4](xid/RB-XID-4.json) | reserved | Unused·구세대 정의 확인 |
| `xid:5` | [RB-XID-5](xid/RB-XID-5.json) | reserved | Unused·구세대 정의 확인 |
| `xid:6` | [RB-XID-6](xid/RB-XID-6.json) | reserved | Unused·구세대 정의 확인 |
| `xid:7` | [RB-XID-7](xid/RB-XID-7.json) | reserved | Unused·구세대 정의 확인 |
| `xid:8` | [RB-XID-8](xid/RB-XID-8.json) | app | 문헌/소스 정의 |
| `xid:9` | [RB-XID-9](xid/RB-XID-9.json) | reserved | Unused·구세대 정의 확인 |
| `xid:10` | [RB-XID-10](xid/RB-XID-10.json) | reserved | Unused·구세대 정의 확인 |
| `xid:11` | [RB-XID-11](xid/RB-XID-11.json) | app | 문헌/소스 정의 |
| `xid:12` | [RB-XID-12](xid/RB-XID-12.json) | reserved | Unused·구세대 정의 확인 |
| `xid:13` | [RB-XID-13](xid/RB-XID-13.json) | app | 문헌/소스 정의 |
| `xid:14` | [RB-XID-14](xid/RB-XID-14.json) | reserved | Unused·구세대 정의 확인 |
| `xid:15` | [RB-XID-15](xid/RB-XID-15.json) | reserved | Unused·구세대 정의 확인 |
| `xid:16` | [RB-XID-16](xid/RB-XID-16.json) | reserved | Unused·구세대 정의 확인 |
| `xid:17` | [RB-XID-17](xid/RB-XID-17.json) | reserved | Unused·구세대 정의 확인 |
| `xid:18` | [RB-XID-18](xid/RB-XID-18.json) | reserved | Unused·구세대 정의 확인 |
| `xid:19` | [RB-XID-19](xid/RB-XID-19.json) | reserved | Unused·구세대 정의 확인 |
| `xid:20` | [RB-XID-20](xid/RB-XID-20.json) | reserved | Unused·구세대 정의 확인 |
| `xid:21` | [RB-XID-21](xid/RB-XID-21.json) | reserved | Unused·구세대 정의 확인 |
| `xid:22` | [RB-XID-22](xid/RB-XID-22.json) | reserved | Unused·구세대 정의 확인 |
| `xid:23` | [RB-XID-23](xid/RB-XID-23.json) | reserved | Unused·구세대 정의 확인 |
| `xid:24` | [RB-XID-24](xid/RB-XID-24.json) | reserved | Unused·구세대 정의 확인 |
| `xid:25` | [RB-XID-25](xid/RB-XID-25.json) | app | 문헌/소스 정의 |
| `xid:26` | [RB-XID-26](xid/RB-XID-26.json) | reserved | Unused·구세대 정의 확인 |
| `xid:27` | [RB-XID-27](xid/RB-XID-27.json) | reserved | Unused·구세대 정의 확인 |
| `xid:28` | [RB-XID-28](xid/RB-XID-28.json) | reserved | Unused·구세대 정의 확인 |
| `xid:29` | [RB-XID-29](xid/RB-XID-29.json) | reserved | Unused·구세대 정의 확인 |
| `xid:30` | [RB-XID-30](xid/RB-XID-30.json) | reserved | Unused·구세대 정의 확인 |
| `xid:31` | [RB-XID-31](xid/RB-XID-31.json) | app | 문헌/소스 정의 |
| `xid:32` | [RB-XID-32](xid/RB-XID-32.json) | pcie | 문헌/소스 정의 |
| `xid:33` | [RB-XID-33](xid/RB-XID-33.json) | reserved | Unused·구세대 정의 확인 |
| `xid:34` | [RB-XID-34](xid/RB-XID-34.json) | reserved | Unused·구세대 정의 확인 |
| `xid:35` | [RB-XID-35](xid/RB-XID-35.json) | reserved | Unused·구세대 정의 확인 |
| `xid:36` | [RB-XID-36](xid/RB-XID-36.json) | reserved | Unused·구세대 정의 확인 |
| `xid:37` | [RB-XID-37](xid/RB-XID-37.json) | firmware | 문헌/소스 정의 |
| `xid:38` | [RB-XID-38](xid/RB-XID-38.json) | firmware | 문헌/소스 정의 |
| `xid:39` | [RB-XID-39](xid/RB-XID-39.json) | app | 문헌/소스 정의 |
| `xid:40` | [RB-XID-40](xid/RB-XID-40.json) | app | 문헌/소스 정의 |
| `xid:41` | [RB-XID-41](xid/RB-XID-41.json) | app | 문헌/소스 정의 |
| `xid:42` | [RB-XID-42](xid/RB-XID-42.json) | reserved | Unused·구세대 정의 확인 |
| `xid:43` | [RB-XID-43](xid/RB-XID-43.json) | app | 문헌/소스 정의 |
| `xid:44` | [RB-XID-44](xid/RB-XID-44.json) | app | 문헌/소스 정의 |
| `xid:45` | [RB-XID-45](xid/RB-XID-45.json) | info | 문헌/소스 정의 |
| `xid:46` | [RB-XID-46](xid/RB-XID-46.json) | app | 문헌/소스 정의 |
| `xid:47` | [RB-XID-47](xid/RB-XID-47.json) | reserved | Unused·구세대 정의 확인 |
| `xid:48` | [RB-XID-48-63-64](xid/RB-XID-48-63-64.json) | memory | 문헌/소스 정의 |
| `xid:49` | [RB-XID-49](xid/RB-XID-49.json) | reserved | Unused·구세대 정의 확인 |
| `xid:50` | [RB-XID-50](xid/RB-XID-50.json) | reserved | Unused·구세대 정의 확인 |
| `xid:51` | [RB-XID-51](xid/RB-XID-51.json) | reserved | Unused·구세대 정의 확인 |
| `xid:52` | [RB-XID-52](xid/RB-XID-52.json) | reserved | Unused·구세대 정의 확인 |
| `xid:53` | [RB-XID-53](xid/RB-XID-53.json) | reserved | Unused·구세대 정의 확인 |
| `xid:54` | [RB-XID-54](xid/RB-XID-54.json) | power | 문헌/소스 정의 |
| `xid:55` | [RB-XID-55](xid/RB-XID-55.json) | reserved | Unused·구세대 정의 확인 |
| `xid:56` | [RB-XID-56](xid/RB-XID-56.json) | reserved | Unused·구세대 정의 확인 |
| `xid:57` | [RB-XID-57](xid/RB-XID-57.json) | reserved | Unused·구세대 정의 확인 |
| `xid:58` | [RB-XID-58](xid/RB-XID-58.json) | reserved | Unused·구세대 정의 확인 |
| `xid:59` | [RB-XID-59](xid/RB-XID-59.json) | reserved | Unused·구세대 정의 확인 |
| `xid:60` | [RB-XID-60](xid/RB-XID-60.json) | app | 문헌/소스 정의 |
| `xid:61` | [RB-XID-61](xid/RB-XID-61.json) | reserved | Unused·구세대 정의 확인 |
| `xid:62` | [RB-XID-62](xid/RB-XID-62.json) | firmware | 문헌/소스 정의 |
| `xid:63` | [RB-XID-63](xid/RB-XID-63.json) | memory | 문헌/소스 정의 |
| `xid:64` | [RB-XID-64](xid/RB-XID-64.json) | memory | 문헌/소스 정의 |
| `xid:65` | [RB-XID-65](xid/RB-XID-65.json) | reserved | Unused·구세대 정의 확인 |
| `xid:66` | [RB-XID-66](xid/RB-XID-66.json) | firmware | 문헌/소스 정의 |
| `xid:67` | [RB-XID-67](xid/RB-XID-67.json) | firmware | 문헌/소스 정의 |
| `xid:68` | [RB-XID-68](xid/RB-XID-68.json) | app | 문헌/소스 정의 |
| `xid:69` | [RB-XID-69](xid/RB-XID-69.json) | app | 문헌/소스 정의 |
| `xid:70` | [RB-XID-70](xid/RB-XID-70.json) | app | 문헌/소스 정의 |
| `xid:71` | [RB-XID-71](xid/RB-XID-71.json) | app | 문헌/소스 정의 |
| `xid:72` | [RB-XID-72](xid/RB-XID-72.json) | app | 문헌/소스 정의 |
| `xid:73` | [RB-XID-73](xid/RB-XID-73.json) | reserved | Unused·구세대 정의 확인 |
| `xid:74` | [RB-XID-74](xid/RB-XID-74.json) | nvlink | 문헌/소스 정의 |
| `xid:75` | [RB-XID-75](xid/RB-XID-75.json) | app | 문헌/소스 정의 |
| `xid:76` | [RB-XID-76](xid/RB-XID-76.json) | app | 문헌/소스 정의 |
| `xid:77` | [RB-XID-77](xid/RB-XID-77.json) | app | 문헌/소스 정의 |
| `xid:78` | [RB-XID-78](xid/RB-XID-78.json) | virtual | 문헌/소스 정의 |
| `xid:79` | [RB-XID-79](xid/RB-XID-79.json) | pcie | 문헌/소스 정의 |
| `xid:80` | [RB-XID-80](xid/RB-XID-80.json) | app | 문헌/소스 정의 |
| `xid:81` | [RB-XID-81](xid/RB-XID-81.json) | reserved | Unused·구세대 정의 확인 |
| `xid:82` | [RB-XID-82](xid/RB-XID-82.json) | app | 문헌/소스 정의 |
| `xid:83` | [RB-XID-83](xid/RB-XID-83.json) | app | 문헌/소스 정의 |
| `xid:84` | [RB-XID-84](xid/RB-XID-84.json) | app | 문헌/소스 정의 |
| `xid:85` | [RB-XID-85](xid/RB-XID-85.json) | app | 문헌/소스 정의 |
| `xid:86` | [RB-XID-86](xid/RB-XID-86.json) | app | 문헌/소스 정의 |
| `xid:87` | [RB-XID-87](xid/RB-XID-87.json) | reserved | Unused·구세대 정의 확인 |
| `xid:88` | [RB-XID-88](xid/RB-XID-88.json) | app | 문헌/소스 정의 |
| `xid:89` | [RB-XID-89](xid/RB-XID-89.json) | app | 문헌/소스 정의 |
| `xid:90` | [RB-XID-90](xid/RB-XID-90.json) | reserved | Unused·구세대 정의 확인 |
| `xid:91` | [RB-XID-91](xid/RB-XID-91.json) | reserved | Unused·구세대 정의 확인 |
| `xid:92` | [RB-XID-92](xid/RB-XID-92.json) | memory | 문헌/소스 정의 |
| `xid:93` | [RB-XID-93](xid/RB-XID-93.json) | info | 문헌/소스 정의 |
| `xid:94` | [RB-XID-94](xid/RB-XID-94.json) | memory | 문헌/소스 정의 |
| `xid:95` | [RB-XID-95](xid/RB-XID-95.json) | memory | 문헌/소스 정의 |
| `xid:96` | [RB-XID-96](xid/RB-XID-96.json) | app | 문헌/소스 정의 |
| `xid:97` | [RB-XID-97](xid/RB-XID-97.json) | app | 문헌/소스 정의 |
| `xid:98` | [RB-XID-98](xid/RB-XID-98.json) | app | 문헌/소스 정의 |
| `xid:99` | [RB-XID-99](xid/RB-XID-99.json) | app | 문헌/소스 정의 |
| `xid:100` | [RB-XID-100](xid/RB-XID-100.json) | app | 문헌/소스 정의 |
| `xid:101` | [RB-XID-101](xid/RB-XID-101.json) | app | 문헌/소스 정의 |
| `xid:102` | [RB-XID-102](xid/RB-XID-102.json) | app | 문헌/소스 정의 |
| `xid:103` | [RB-XID-103](xid/RB-XID-103.json) | app | 문헌/소스 정의 |
| `xid:104` | [RB-XID-104](xid/RB-XID-104.json) | app | 문헌/소스 정의 |
| `xid:105` | [RB-XID-105](xid/RB-XID-105.json) | app | 문헌/소스 정의 |
| `xid:106` | [RB-XID-106](xid/RB-XID-106.json) | info | 문헌/소스 정의 |
| `xid:107` | [RB-XID-107](xid/RB-XID-107.json) | info | 문헌/소스 정의 |
| `xid:108` | [RB-XID-108](xid/RB-XID-108.json) | reserved | Unused·구세대 정의 확인 |
| `xid:109` | [RB-XID-109](xid/RB-XID-109.json) | app | 문헌/소스 정의 |
| `xid:110` | [RB-XID-110](xid/RB-XID-110.json) | firmware | 문헌/소스 정의 |
| `xid:111` | [RB-XID-111](xid/RB-XID-111.json) | reserved | Unused·구세대 정의 확인 |
| `xid:112` | [RB-XID-112](xid/RB-XID-112.json) | reserved | Unused·구세대 정의 확인 |
| `xid:113` | [RB-XID-113](xid/RB-XID-113.json) | reserved | Unused·구세대 정의 확인 |
| `xid:114` | [RB-XID-114](xid/RB-XID-114.json) | reserved | Unused·구세대 정의 확인 |
| `xid:115` | [RB-XID-115](xid/RB-XID-115.json) | reserved | Unused·구세대 정의 확인 |
| `xid:116` | [RB-XID-116](xid/RB-XID-116.json) | reserved | Unused·구세대 정의 확인 |
| `xid:117` | [RB-XID-117](xid/RB-XID-117.json) | reserved | Unused·구세대 정의 확인 |
| `xid:118` | [RB-XID-118](xid/RB-XID-118.json) | reserved | Unused·구세대 정의 확인 |
| `xid:119` | [RB-XID-119](xid/RB-XID-119.json) | firmware | 문헌/소스 정의 |
| `xid:120` | [RB-XID-120](xid/RB-XID-120.json) | firmware | 문헌/소스 정의 |
| `xid:121` | [RB-XID-121](xid/RB-XID-121.json) | nvlink | 문헌/소스 정의 |
| `xid:122` | [RB-XID-122](xid/RB-XID-122.json) | reserved | Unused·구세대 정의 확인 |
| `xid:123` | [RB-XID-123](xid/RB-XID-123.json) | reserved | Unused·구세대 정의 확인 |
| `xid:124` | [RB-XID-124](xid/RB-XID-124.json) | reserved | Unused·구세대 정의 확인 |
| `xid:125` | [RB-XID-125](xid/RB-XID-125.json) | reserved | Unused·구세대 정의 확인 |
| `xid:126` | [RB-XID-126](xid/RB-XID-126.json) | app | 정의 차이 확인 |
| `xid:127` | [RB-XID-127](xid/RB-XID-127.json) | app | 정의 차이 확인 |
| `xid:128` | [RB-XID-128](xid/RB-XID-128.json) | app | 정의 차이 확인 |
| `xid:129` | [RB-XID-129](xid/RB-XID-129.json) | app | 정의 차이 확인 |
| `xid:130` | [RB-XID-130](xid/RB-XID-130.json) | app | 정의 차이 확인 |
| `xid:131` | [RB-XID-131](xid/RB-XID-131.json) | app | 정의 차이 확인 |
| `xid:132` | [RB-XID-132](xid/RB-XID-132.json) | app | 정의 차이 확인 |
| `xid:133` | [RB-XID-133](xid/RB-XID-133.json) | app | 문헌/소스 정의 |
| `xid:134` | [RB-XID-134](xid/RB-XID-134.json) | app | 정의 차이 확인 |
| `xid:135` | [RB-XID-135](xid/RB-XID-135.json) | app | 정의 차이 확인 |
| `xid:136` | [RB-XID-136](xid/RB-XID-136.json) | nvlink | 정의 차이 확인 |
| `xid:137` | [RB-XID-137](xid/RB-XID-137.json) | nvlink | 문헌/소스 정의 |
| `xid:138` | [RB-XID-138](xid/RB-XID-138.json) | reserved | Unused·구세대 정의 확인 |
| `xid:139` | [RB-XID-139](xid/RB-XID-139.json) | app | 정의 차이 확인 |
| `xid:140` | [RB-XID-140](xid/RB-XID-140.json) | memory | 문헌/소스 정의 |
| `xid:141` | [RB-XID-141](xid/RB-XID-141.json) | app | 정의 차이 확인 |
| `xid:142` | [RB-XID-142](xid/RB-XID-142.json) | reserved | 정의 차이 확인 |
| `xid:143` | [RB-XID-143](xid/RB-XID-143.json) | firmware | 문헌/소스 정의 |
| `xid:144` | [RB-XID-144](xid/RB-XID-144.json) | nvlink | 문헌/소스 정의 |
| `xid:145` | [RB-XID-145](xid/RB-XID-145.json) | nvlink | 문헌/소스 정의 |
| `xid:146` | [RB-XID-146](xid/RB-XID-146.json) | nvlink | 문헌/소스 정의 |
| `xid:147` | [RB-XID-147](xid/RB-XID-147.json) | nvlink | 문헌/소스 정의 |
| `xid:148` | [RB-XID-148](xid/RB-XID-148.json) | nvlink | 문헌/소스 정의 |
| `xid:149` | [RB-XID-149](xid/RB-XID-149.json) | nvlink | 문헌/소스 정의 |
| `xid:150` | [RB-XID-150](xid/RB-XID-150.json) | nvlink | 문헌/소스 정의 |
| `xid:151` | [RB-XID-151](xid/RB-XID-151.json) | virtual | 문헌/소스 정의 |
| `xid:152` | [RB-XID-152](xid/RB-XID-152.json) | app | 문헌/소스 정의 |
| `xid:153` | [RB-XID-153](xid/RB-XID-153.json) | app | 문헌/소스 정의 |
| `xid:154` | [RB-XID-154](xid/RB-XID-154.json) | info | 문헌/소스 정의 |
| `xid:155` | [RB-XID-155](xid/RB-XID-155.json) | nvlink | 문헌/소스 정의 |
| `xid:156` | [RB-XID-156](xid/RB-XID-156.json) | memory | 문헌/소스 정의 |
| `xid:157` | [RB-XID-157](xid/RB-XID-157.json) | memory | 문헌/소스 정의 |
| `xid:158` | [RB-XID-158](xid/RB-XID-158.json) | app | 문헌/소스 정의 |
| `xid:159` | [RB-XID-159](xid/RB-XID-159.json) | nvlink | 문헌/소스 정의 |
| `xid:160` | [RB-XID-160](xid/RB-XID-160.json) | app | 문헌/소스 정의 |
| `xid:161` | [RB-XID-161](xid/RB-XID-161.json) | app | 문헌/소스 정의 |
| `xid:162` | [RB-XID-162](xid/RB-XID-162.json) | power | 문헌/소스 정의 |
| `xid:163` | [RB-XID-163](xid/RB-XID-163.json) | power | 문헌/소스 정의 |
| `xid:164` | [RB-XID-164](xid/RB-XID-164.json) | power | 문헌/소스 정의 |
| `xid:165` | [RB-XID-165](xid/RB-XID-165.json) | power | 문헌/소스 정의 |
| `xid:166` | [RB-XID-166](xid/RB-XID-166.json) | nvlink | 문헌/소스 정의 |
| `xid:167` | [RB-XID-167](xid/RB-XID-167.json) | pcie | 문헌/소스 정의 |
| `xid:168` | [RB-XID-168](xid/RB-XID-168.json) | memory | 문헌/소스 정의 |
| `xid:169` | [RB-XID-169](xid/RB-XID-169.json) | firmware | 문헌/소스 정의 |
| `xid:170` | [RB-XID-170](xid/RB-XID-170.json) | nvlink | 문헌/소스 정의 |
| `xid:171` | [RB-XID-171](xid/RB-XID-171.json) | memory | 문헌/소스 정의 |
| `xid:172` | [RB-XID-172](xid/RB-XID-172.json) | memory | 문헌/소스 정의 |
| `xid:173` | [RB-XID-173](xid/RB-XID-173.json) | nvlink | 코드 소스만 확인 |
| `sxid:10001` | [RB-SXID-10001](sxid/RB-SXID-10001.json) | fabric | 문헌/소스 정의 |
| `sxid:10002` | [RB-SXID-10002](sxid/RB-SXID-10002.json) | fabric | 문헌/소스 정의 |
| `sxid:10003` | [RB-SXID-10003](sxid/RB-SXID-10003.json) | fabric | 문헌/소스 정의 |
| `sxid:10004` | [RB-SXID-10004](sxid/RB-SXID-10004.json) | fabric | 문헌/소스 정의 |
| `sxid:10005` | [RB-SXID-10005](sxid/RB-SXID-10005.json) | fabric | 문헌/소스 정의 |
| `sxid:11001` | [RB-SXID-11001](sxid/RB-SXID-11001.json) | fabric | 문헌/소스 정의 |
| `sxid:11004` | [RB-SXID-11004](sxid/RB-SXID-11004.json) | fabric | 문헌/소스 정의 |
| `sxid:11009` | [RB-SXID-11009](sxid/RB-SXID-11009.json) | fabric | 문헌/소스 정의 |
| `sxid:11012` | [RB-SXID-11012](sxid/RB-SXID-11012.json) | fabric | 문헌/소스 정의 |
| `sxid:11013` | [RB-SXID-11013](sxid/RB-SXID-11013.json) | fabric | 문헌/소스 정의 |
| `sxid:11018` | [RB-SXID-11018](sxid/RB-SXID-11018.json) | fabric | 문헌/소스 정의 |
| `sxid:11019` | [RB-SXID-11019](sxid/RB-SXID-11019.json) | fabric | 문헌/소스 정의 |
| `sxid:11020` | [RB-SXID-11020](sxid/RB-SXID-11020.json) | fabric | 문헌/소스 정의 |
| `sxid:11021` | [RB-SXID-11021](sxid/RB-SXID-11021.json) | fabric | 문헌/소스 정의 |
| `sxid:11022` | [RB-SXID-11022](sxid/RB-SXID-11022.json) | fabric | 문헌/소스 정의 |
| `sxid:11023` | [RB-SXID-11023](sxid/RB-SXID-11023.json) | fabric | 문헌/소스 정의 |
| `sxid:12001` | [RB-SXID-12001](sxid/RB-SXID-12001.json) | fabric | 문헌/소스 정의 |
| `sxid:12002` | [RB-SXID-12002](sxid/RB-SXID-12002.json) | fabric | 문헌/소스 정의 |
| `sxid:12020` | [RB-SXID-12020](sxid/RB-SXID-12020.json) | fabric | 문헌/소스 정의 |
| `sxid:12021` | [RB-SXID-12021](sxid/RB-SXID-12021.json) | fabric | 문헌/소스 정의 |
| `sxid:12022` | [RB-SXID-12022](sxid/RB-SXID-12022.json) | fabric | 문헌/소스 정의 |
| `sxid:12023` | [RB-SXID-12023](sxid/RB-SXID-12023.json) | fabric | 문헌/소스 정의 |
| `sxid:12024` | [RB-SXID-12024](sxid/RB-SXID-12024.json) | fabric | 문헌/소스 정의 |
| `sxid:12025` | [RB-SXID-12025](sxid/RB-SXID-12025.json) | fabric | 문헌/소스 정의 |
| `sxid:12026` | [RB-SXID-12026](sxid/RB-SXID-12026.json) | fabric | 문헌/소스 정의 |
| `sxid:12027` | [RB-SXID-12027](sxid/RB-SXID-12027.json) | fabric | 문헌/소스 정의 |
| `sxid:12028` | [RB-SXID-12028](sxid/RB-SXID-12028.json) | fabric | 문헌/소스 정의 |
| `sxid:12030` | [RB-SXID-12030](sxid/RB-SXID-12030.json) | fabric | 문헌/소스 정의 |
| `sxid:12031` | [RB-SXID-12031](sxid/RB-SXID-12031.json) | fabric | 문헌/소스 정의 |
| `sxid:12032` | [RB-SXID-12032](sxid/RB-SXID-12032.json) | fabric | 문헌/소스 정의 |
| `sxid:14017` | [RB-SXID-14017](sxid/RB-SXID-14017.json) | fabric | 문헌/소스 정의 |
| `sxid:15001` | [RB-SXID-15001](sxid/RB-SXID-15001.json) | fabric | 문헌/소스 정의 |
| `sxid:15006` | [RB-SXID-15006](sxid/RB-SXID-15006.json) | fabric | 문헌/소스 정의 |
| `sxid:15008` | [RB-SXID-15008](sxid/RB-SXID-15008.json) | fabric | 문헌/소스 정의 |
| `sxid:15009` | [RB-SXID-15009](sxid/RB-SXID-15009.json) | fabric | 문헌/소스 정의 |
| `sxid:15010` | [RB-SXID-15010](sxid/RB-SXID-15010.json) | fabric | 문헌/소스 정의 |
| `sxid:15011` | [RB-SXID-15011](sxid/RB-SXID-15011.json) | fabric | 문헌/소스 정의 |
| `sxid:15012` | [RB-SXID-15012](sxid/RB-SXID-15012.json) | fabric | 문헌/소스 정의 |
| `sxid:15013` | [RB-SXID-15013](sxid/RB-SXID-15013.json) | fabric | 문헌/소스 정의 |
| `sxid:19047` | [RB-SXID-19047](sxid/RB-SXID-19047.json) | fabric | 문헌/소스 정의 |
| `sxid:19048` | [RB-SXID-19048](sxid/RB-SXID-19048.json) | fabric | 문헌/소스 정의 |
| `sxid:19049` | [RB-SXID-19049](sxid/RB-SXID-19049.json) | fabric | 문헌/소스 정의 |
| `sxid:19054` | [RB-SXID-19054](sxid/RB-SXID-19054.json) | fabric | 문헌/소스 정의 |
| `sxid:19055` | [RB-SXID-19055](sxid/RB-SXID-19055.json) | fabric | 문헌/소스 정의 |
| `sxid:19056` | [RB-SXID-19056](sxid/RB-SXID-19056.json) | fabric | 문헌/소스 정의 |
| `sxid:19057` | [RB-SXID-19057](sxid/RB-SXID-19057.json) | fabric | 문헌/소스 정의 |
| `sxid:19058` | [RB-SXID-19058](sxid/RB-SXID-19058.json) | fabric | 문헌/소스 정의 |
| `sxid:19059` | [RB-SXID-19059](sxid/RB-SXID-19059.json) | fabric | 문헌/소스 정의 |
| `sxid:19060` | [RB-SXID-19060](sxid/RB-SXID-19060.json) | fabric | 문헌/소스 정의 |
| `sxid:19061` | [RB-SXID-19061](sxid/RB-SXID-19061.json) | fabric | 문헌/소스 정의 |
| `sxid:19062` | [RB-SXID-19062](sxid/RB-SXID-19062.json) | fabric | 문헌/소스 정의 |
| `sxid:19063` | [RB-SXID-19063](sxid/RB-SXID-19063.json) | fabric | 문헌/소스 정의 |
| `sxid:19064` | [RB-SXID-19064](sxid/RB-SXID-19064.json) | fabric | 문헌/소스 정의 |
| `sxid:19065` | [RB-SXID-19065](sxid/RB-SXID-19065.json) | fabric | 문헌/소스 정의 |
| `sxid:19066` | [RB-SXID-19066](sxid/RB-SXID-19066.json) | fabric | 문헌/소스 정의 |
| `sxid:19067` | [RB-SXID-19067](sxid/RB-SXID-19067.json) | fabric | 문헌/소스 정의 |
| `sxid:19068` | [RB-SXID-19068](sxid/RB-SXID-19068.json) | fabric | 문헌/소스 정의 |
| `sxid:19069` | [RB-SXID-19069](sxid/RB-SXID-19069.json) | fabric | 문헌/소스 정의 |
| `sxid:19070` | [RB-SXID-19070](sxid/RB-SXID-19070.json) | fabric | 문헌/소스 정의 |
| `sxid:19071` | [RB-SXID-19071](sxid/RB-SXID-19071.json) | fabric | 문헌/소스 정의 |
| `sxid:19084` | [RB-SXID-19084](sxid/RB-SXID-19084.json) | fabric | 문헌/소스 정의 |
| `sxid:20001` | [RB-SXID-20001](sxid/RB-SXID-20001.json) | fabric | 문헌/소스 정의 |
| `sxid:20009` | [RB-SXID-20009](sxid/RB-SXID-20009.json) | fabric | 코드 소스만 확인 |
| `sxid:20012` | [RB-SXID-20012](sxid/RB-SXID-20012.json) | fabric | 문헌/소스 정의 |
| `sxid:20034` | [RB-SXID-20034](sxid/RB-SXID-20034.json) | fabric | 문헌/소스 정의 |
| `sxid:22003` | [RB-SXID-22003](sxid/RB-SXID-22003.json) | fabric | 문헌/소스 정의 |
| `sxid:22011` | [RB-SXID-22011](sxid/RB-SXID-22011.json) | fabric | 문헌/소스 정의 |
| `sxid:22012` | [RB-SXID-22012](sxid/RB-SXID-22012.json) | fabric | 코드 소스만 확인 |
| `sxid:22013` | [RB-SXID-22013](sxid/RB-SXID-22013.json) | fabric | 문헌/소스 정의 |
| `sxid:23001` | [RB-SXID-23001](sxid/RB-SXID-23001.json) | fabric | 문헌/소스 정의 |
| `sxid:23002` | [RB-SXID-23002](sxid/RB-SXID-23002.json) | fabric | 문헌/소스 정의 |
| `sxid:23003` | [RB-SXID-23003](sxid/RB-SXID-23003.json) | fabric | 문헌/소스 정의 |
| `sxid:23004` | [RB-SXID-23004](sxid/RB-SXID-23004.json) | fabric | 문헌/소스 정의 |
| `sxid:23005` | [RB-SXID-23005](sxid/RB-SXID-23005.json) | fabric | 문헌/소스 정의 |
| `sxid:23006` | [RB-SXID-23006](sxid/RB-SXID-23006.json) | fabric | 문헌/소스 정의 |
| `sxid:23007` | [RB-SXID-23007](sxid/RB-SXID-23007.json) | fabric | 문헌/소스 정의 |
| `sxid:23008` | [RB-SXID-23008](sxid/RB-SXID-23008.json) | fabric | 문헌/소스 정의 |
| `sxid:23009` | [RB-SXID-23009](sxid/RB-SXID-23009.json) | fabric | 문헌/소스 정의 |
| `sxid:23010` | [RB-SXID-23010](sxid/RB-SXID-23010.json) | fabric | 문헌/소스 정의 |
| `sxid:23011` | [RB-SXID-23011](sxid/RB-SXID-23011.json) | fabric | 문헌/소스 정의 |
| `sxid:23012` | [RB-SXID-23012](sxid/RB-SXID-23012.json) | fabric | 문헌/소스 정의 |
| `sxid:23013` | [RB-SXID-23013](sxid/RB-SXID-23013.json) | fabric | 문헌/소스 정의 |
| `sxid:23014` | [RB-SXID-23014](sxid/RB-SXID-23014.json) | fabric | 문헌/소스 정의 |
| `sxid:23015` | [RB-SXID-23015](sxid/RB-SXID-23015.json) | fabric | 문헌/소스 정의 |
| `sxid:23016` | [RB-SXID-23016](sxid/RB-SXID-23016.json) | fabric | 문헌/소스 정의 |
| `sxid:23017` | [RB-SXID-23017](sxid/RB-SXID-23017.json) | fabric | 문헌/소스 정의 |
| `sxid:24001` | [RB-SXID-24001](sxid/RB-SXID-24001.json) | fabric | 문헌/소스 정의 |
| `sxid:24002` | [RB-SXID-24002](sxid/RB-SXID-24002.json) | fabric | 문헌/소스 정의 |
| `sxid:24003` | [RB-SXID-24003](sxid/RB-SXID-24003.json) | fabric | 문헌/소스 정의 |
| `sxid:24004` | [RB-SXID-24004](sxid/RB-SXID-24004.json) | fabric | 문헌/소스 정의 |
| `sxid:24005` | [RB-SXID-24005](sxid/RB-SXID-24005.json) | fabric | 문헌/소스 정의 |
| `sxid:24006` | [RB-SXID-24006](sxid/RB-SXID-24006.json) | fabric | 문헌/소스 정의 |
| `sxid:24007` | [RB-SXID-24007](sxid/RB-SXID-24007.json) | fabric | 문헌/소스 정의 |
