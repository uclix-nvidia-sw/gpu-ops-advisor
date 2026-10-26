# RCA Runbook 전체 작성 목록 (XID·SXID·Fleet 컴포넌트)

기준일: 2026-09-28. 이전 PR #15의 대표 오류 3건을 전체 코드 자료 범위로 확장했다. **XID 173건 + SXID 93건 = 오류별 266건**, 일반 GPU 노드 조사까지 **267건**이다. 기존 3건을 유지·보강하고 263건을 추가했다. 2026-10-22에 코드 없는 Fleet 컴포넌트 알림용 **17건**을 더해 전체 **284건**이다. 모든 파일은 기존 Knowledge API의 v1 JSON 봉투이며 새 DB 테이블이나 migration은 없다.

## 파일 구성

```text
runbooks/
  RB-GENERAL-GPU-NODE.json
  xid/RB-XID-*.json
  sxid/RB-SXID-*.json
  component/RB-COMPONENT-*.json
  catalog-manifest.json
```

`catalog-manifest.json`의 `fleet_event_type`(고정 Fleet 카탈로그 분류, 없으면 Fleet이 내보내지 않음)과 `fm_sxid_table`(FM 가이드 v2.6 표 번호)은 [Grafana 알림 규칙](../../incident/README.md#grafana-알림-규칙)의 RCA 허용 목록을 계산하는 입력이다. JSON에는 코드별 증거·분기·조치 조건·출처만 남긴다. DB 등록, 승인 정책, 런타임 역할, parser/query의 개발 상태 같은 공통 설명은 이 문서와 [DB-WORKFLOW](DB-WORKFLOW.md)에서 관리한다. 반복 설명 정리로 analysis_guidance와 limitations의 전체 글자 수를 약 61% 줄였다. 수집 품질·대상 일치, 문헌과 수행 증거의 구분, 자동 조치 금지는 기존 Worker 계약으로 유지한다.

## 자료 범위와 작성 결과

- 기존 [Fleet·GPUd 카탈로그](../../docs/specs/rca-agent/references/fleet-gpud-error-catalog.md): XID 172개·SXID 92개를 모두 포함했다. 저장소별 중복 정의를 별도 Runbook으로 늘리지 않았다.
- NVIDIA 최신 Xid 표의 **133**과 고정 GPUd 소스의 **SXID 22012**를 추가했다. 따라서 이번 합집합은 기존 264개보다 2개 많다.
- 기존 `RB-XID-48-63-64`의 검색 진입은 계속 **XID 48만**이다. XID 63과 64에는 각각 독립 콘텐츠를 작성했다. 동반 코드 관계는 조사 지침이며 equality 조건식의 자동 시간 판정 기능을 추가한 것은 아니다.
- 코드 Runbook의 범위는 제공된 자료의 XID/SXID 코드다. 코드 없는 Fleet 컴포넌트 알림은 아래 [Fleet 컴포넌트 Runbook](#fleet-컴포넌트-runbook) 17건이 다룬다. 수치 시계열로 판정하는 NCCL·IB 성능 Runbook이나 아직 자료에 없는 오류를 작성했다는 의미는 아니다.

각 파일은 코드 의미·출처별 event/action·적용 제품·필요 로그/메트릭·대상/시각·판별 절차·조건부 권고·부족 시 처리·조치 후 확인을 담는다. Reserved/Unused처럼 원문에 절차가 없는 항목은 원문·버전을 확인하는 절차까지 작성하고 진단 규칙을 만들지 않았다.

### 운영자 보고서 지침과 조회 계획 (2026-10-22 개정)

공식 문헌·고정 소스와 코드별로 대조한 결과, 출처에서 옮긴 사실(설명·NVIDIA 적용 제품·즉시/조사 조치 분류·Fleet event_type/action·GPUd 치명도)은 264건 모두 일치했다. 반면 `수집:`/`판단:` 문장과 제목은 증거 그룹마다 모든 코드가 같은 문장이었고, 259건의 조회 계획은 D09·D02뿐이었다. 각 런북의 한계 문장도 ECC·전력·NVLink 근거가 없다고 적고 있었다. RB-XID-79·RB-SXID-11001을 제외한 264건을 다음과 같이 고쳤다. 대조 방법·코드별 이전 값·해시는 [검토 기록](operator-report-review-20261022.json)에 있다.

| 보고서 유형 | 대상 | 조회 계획(D09 외) |
|---|---|---|
| ECC·메모리 | XID 48·63·64·92·94·95·140·156·157·168·171·172 | DBE D40(필수)·D42, SBE D36(필수)·D38, 메모리 온도 D23, 사용률 D02 |
| NVLink | XID 74·136·144~150·155·166·170 | NVLink 수신·송신 D33·D34, FM 상태 D47, D02 |
| C2C | XID 121·159·173 | 전력 D11, 온도 D04, D02 (C2C 카운터는 등록 지표 없음) |
| PCIe·버스 | XID 32·167 | PCIe replay D44, 전력 D11, 온도 D04, D02 |
| 전원·열·전력 평활 | XID 54·162~165 | 전력 D11, 전력 한도 D48, 클록 제한 사유 D45, 온도 D04, D02 |
| 드라이버·펌웨어 | XID 37·38·62·66·67·110·119·120·143·169 | D11, D04, D02 |
| GPU 응답 정지 | XID 46·109·158 | 메모리 사용량 D03, D11, D04, D02 |
| 애플리케이션·엔진 | 그 밖의 app 그룹 XID·137 | D03, D11, D02 |
| 가상화·정보성·미사용 | virtual·info·reserved 그룹 | D02 |
| NVSwitch | SXID 92건 | FM 상태 D47, NVLink D33·D34, 선택 D02(GPU 모델·드라이버·파드 라벨) (열 이벤트 10004·10005는 온도 D04 추가) |

- 조회는 배포 프로필에서 verified binding인 D만 쓴다(D46 등 candidate 제외). 검사: `test_every_code_has_operator_report_material_from_verified_queries`.
- `operator_guidance`는 오류 의미(NVIDIA 발생 조건 요약) → 진단 자료 보존 → 오류별 판단 기준(NVIDIA 조사 분기·GPU Node Triage) → 복구 조치(NVIDIA 즉시 조치 분류) → 재발 시 진단·공급사 전달의 고정 순서다. SXID는 FM 가이드 표 22~25의 분류별 영향·복구와 패브릭 상태 확인을 쓴다. 문헌 문장을 복사하지 않고 요약했으며 문헌에 없는 임계값·조치는 추가하지 않았다.
- 정정: SXID 22012는 FM 가이드 표 23(Potential Fatal)과 고정 Fleet 소스에 모두 정의돼 있어 `documented`로 바꾸고, "Fleet 카탈로그에 없음" 서술을 지웠다.
- 저장소 원본 개정이며 발행 revision은 바꾸지 않는다. 새 revision 발행 전에는 기존 발행본(D09만 필수)이 그대로 쓰이고, 보고서 6단 형식의 전체 화면은 새 revision이 메트릭 조회를 필수로 갖는 경우에만 만들어진다.

### 운영자 대응 재검토 (2026-10-22)

GPU Node Triage(Last updated on Oct 04, 2026) 표 1·2와 흐름도, Xid 카탈로그(Sep 09, 2026), Fabric Manager User Guide v2.6(Sep 21, 2026)의 bare metal 절차, nvidia-smi 문서, DCGM `dcgm_errors.h`와 다시 대조했다. 운영자가 그대로 따르면 틀리는 단계만 고쳤고, 파서가 읽는 `NVIDIA 적용:`·`NVIDIA 조치 분류:`·`Fleet 고정 카탈로그:` 줄은 바꾸지 않았다. 코드별 이전 값과 해시는 [검토 기록](triage-guidance-review-20261022.json)에 있다.

| 대상 | 고친 내용 |
|---|---|
| XID 79 | 운영자 순서로 재작성: 즉시 확인·격리(cordon, 실제 이탈·주입 시험 구분) → 자료 보존(`nvidia-bug-report.sh`의 `--safe-mode --extra-system-data`, SEL, FM 로그) → XID 154 복구 수준 → 반복·확산 판단 → RESTART_BM → 복구 확인 → 공급사 전달 |
| XID 64 | A100은 기록 실패 시 노드 즉시 재부팅(Triage A100 행). 기존 "노드 재시작까지는 필요하지 않습니다"는 A100에서 틀린 안내였다 |
| XID 95 | A100에서 MIG가 꺼져 있으면 노드 즉시 재부팅, 켜져 있으면 다른 인스턴스 배출 뒤 GPU 리셋(Triage). XID 94·95의 "2차 오류" 문장을 원인 조사 방향(동반 메모리 오류 우선)으로 정정 |
| XID 61·123 | 카탈로그상 Unused이지만 Triage 표 1이 보고와 GPU 리셋을 안내하므로 "복구 조치를 정하지 않습니다"를 CONTACT_SUPPORT·GPU 리셋 단계로 교체 |
| 묶음 2 (60건) | GPU 사용률만 수집하던 XID 중 38건에 의미별 밀접 지표: 푸시 버퍼·드라이버·비디오 엔진 25건은 GPU 메모리 사용량, 메모리 인터페이스 26·57·58은 ECC·메모리 온도·행 재매핑, 마이크로컨트롤러·펌웨어 33·59·61·122~124는 온도·전력·클록 제한 사유, InfoROM 93·125는 InfoROM 유효, PCIe 18은 replay, 45는 DBE. 전력·열 계획(XID 54·162~165, DCGM 열·전력)에 열·전력 제한 누적 시간(D61·D62). 항상 치명 SXID 15건(12020·22003·22011·23001~23012)의 복구를 Fabric Manager 가이드대로 bare metal access/trunk 포트와 가상화 절차로 나눔([검토 기록](runbook-batch2-review-20261024.json)). 디스플레이·미사용·예약·시험·가상화 33건은 데이터센터에서 드물거나 정보성이라 사용률만 유지 |
| 묶음 3 (15건) | DCGM 7건(메모리·NVLink·NVSwitch·PCIe·전력·열·InfoROM)과 라이브러리·이더넷·peermem·NCCL에 리셋·재부팅 전 진단 자료 보존 단계, NCCL에 복구 단계. CPU·메모리·OS를 즉시 확인→보존→판단→복구→복구 확인→공급사 전달로 넓히고 커널 문서(lockup watchdog·sysctl kernel·RAS·proc)와 Fleet 커널 로그 이벤트(soft lockup·hung task·OOM·VFS file-max·kernel panic)를 출처로 더함. OS의 PID 비율 분모(Fleet 기준 900,000)·파일 핸들 분모·좀비 임계(파일 핸들 한도의 20%·80%)를 Fleet 원본대로 정정. 지표: CPU D18·D19, 메모리 D63·D64, 이더넷 D65~D69, OS D70~D72([근거](../../docs/evidence/d-observation-expansion-20261025.md)). 일반 조사 Runbook에 운영자 지침과 노드 요약 지표([검토 기록](runbook-batch3-review-20261025.json)) |
| 원문 근거 문구 (246건) | 운영자 지침에서 장애 주입 시험 확인을 운영자가 직접 확인할 수 있는 원문 근거로 바꿈: XID는 커널 로그(NVRM: Xid 줄), SXID는 Fabric Manager 로그에 같은 오류가 없고 Fleet 보고만 있으면 복구 조치를 하지 않고 보고 경로부터 확인(XID 172·SXID 70·컴포넌트 4). CPU·메모리·NCCL 의미의 첫 문장을 '하드웨어 오류 보고가 아님'으로 시작하고 즉시 확인을 노드에서 통계가 직접 읽히는지로 바꿈. XID 14(주입한 가짜 오류가 정의)와 참조 문단은 유지([검토 기록](operator-evidence-wording-review-20261026.json)) |
| 수집 계획 125건 | 장애와 직접 관련된 지표를 선택 단계로 추가: 메모리 XID 12건·DCGM 메모리는 행 재매핑(D50~D54), NVLink XID 12건·SXID 93건·DCGM NVLink/NVSwitch는 NVLink 오류 누적값(D55~D57), DCGM InfoROM은 체크섬 유효(D58), disk는 마운트별 사용·여유(D59·D60). XID 13·31은 카탈로그대로 DCGM EUD → Field Diagnostics, XID 45는 DBE 동반 확인, XID 74는 적용 범위와 NVLink 오류 카운터 비교, 메모리 XID는 행 재매핑 값으로 리셋·RMA 판단을 연결([검토 기록](metric-coverage-review-20261024.json)). 새 조회가 든 프로필을 배포한 뒤에 발행한다 |
| XID 48 | 메시지의 `framebuffer` 여부로 DRAM·SRAM 분기, 행 재매핑 Pending(리셋 뒤 적용)·Remapping Failure(Field Diagnostics 확인 뒤 RMA), 구세대 GPU의 페이지 폐기, RMA 기준(뱅크당 UCE 재매핑 8개·재매핑 행 재시도·합계 512, Blackwell HBM 채널 수리), 함께 보는 Xid 63·64·94·95·160·171·172 추가. 카탈로그 요약의 'Xid 154 연계' 오표기를 적용 버전 문구로 정정([검토 기록](xid48-memory-review-20261023.json)) |
| XID 63·92 | 즉시 조치는 없지만 row remapping은 GPU 리셋 뒤 적용(63), Field Diagnostics 권고(92)를 복구 단계에 추가 |
| SXID 93건 | `nvidia-smi -q`의 Fabric State·Status는 R580에서 폐기됐으므로 Hopper 이후 Fabric Health 확인으로 교체. D47 값(0 미지원 ~ 6 NVML 버전 낮음) 읽는 법 추가. 2026-10-23 운영자 문장의 내부 조회 ID와 출처 제목의 DCGM 열거형 이름을 의미 이름으로 바꾸고 선택 D02를 추가([검토 기록](operator-wording-review-20261023.json)) |
| SXID 잠재적 치명 41건·11001 | 영향·복구를 bare metal 절차(access 포트: 해당 GPU와 같은 작업 GPU 리셋, trunk 포트: FM 정지 후 전체 리셋) 먼저, 공유 NVSwitch 가상화(guest VM) 절차를 다음에 적음 |
| SXID 11004·12028 | 비치명 SXID는 bare metal에서 정보성이고 FM이 작업을 중단하지 않음을 명시, guest VM 재시작은 가상화 절차로 분리 |
| SXID 19084·10003 | 전체 GPU·NVSwitch 리셋에 bare metal 절차(FM 정지 → `-i` 없는 `nvidia-smi -r` → FM 재시작) 추가 |
| SXID 항상 치명 20건·10003 | LLM 지침의 guest partition 전제를 bare metal(작업 배출 후 호스트 재시작) 우선으로 정정 |
| SXID 20034 | 의미 문장에 섞여 있던 FM 표 영어 원문을 정리 |

### Xid 카탈로그 즉시 조치 대조 (2026-10-23)

XID 173건을 NVIDIA가 배포한 [Xid-Catalog.xlsx](https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html)(Sep 09, 2026)의 행(니모닉·적용 제품·즉시/조사 조치·Xid 154 연계)과 GPU Node Triage 표 1에 하나씩 대조했다. 172개 코드의 카탈로그 필드는 모두 일치했고, 복구 단계가 즉시 조치 분류와 어긋난 63건을 고쳤고, 재검수에서 XID 154와 문장 끝맺음 8건을 더 고쳤다. SXID 93건은 Fabric Manager User Guide v2.6 표 22~25의 분류·오류 문자열과 모두 일치했고, 분류별 대응(비치명: 정보성, 잠재적 치명: access/trunk 포트별 리셋, 항상 치명: 호스트 재시작)도 모두 들어 있어 단일 비트 ECC 19건의 영향 문장만 고쳤다. 이전 값과 해시는 [검토 기록](xid-catalog-action-review-20261023.json)에 있다.

| 대상 | 고친 내용 |
|---|---|
| 미사용 코드 59건(즉시 조치 CONTACT_SUPPORT) | "정의가 확인되기 전에는 복구 조치를 정하지 않습니다"를 카탈로그대로 공급사 문의로 교체. 함께 보고된 다른 XID의 지침을 먼저 따르도록 명시 |
| XID 14 | 카탈로그 발생 조건이 "사용자 공간에서 주입한 가짜 오류"이므로 의미·원인·판단을 주입 시험 기준으로 다시 쓰고 즉시 조치 IGNORE 적용 |
| XID 108 | 즉시 조치 IGNORE, 조사는 XID_137_FLOW(원격 MMU fault 애플리케이션 점검) |
| XID 31 | Triage 표 1의 "하드웨어 공급사 연락"을 "의심되면"으로 약하게 적은 문장을 원문대로 정정 |
| XID 79 | 10-22 재작성에서 빠진 Xid 카탈로그 참고 항목 복원 |
| XID 154 | 복구 단계가 "XID 154의 복구 조치 문구를 따릅니다"로 자기 자신을 가리키던 것을 nvidia-smi GPU Recovery Action 값별 조치(None, Reset, Reboot, Drain P2P, Drain and Reset)로 교체 |
| XID 106·107·142·162~165·173 | 판단 단계의 "~한다." 끝맺음을 다른 단계와 같은 "~합니다."로 통일 |
| SXID 리셋 문장 42건·XID 79·XID 63 | 특정 서버(A100) 기준 문장을 모든 세대로 확장: Hopper 이후는 FM과 관계없이 개별 리셋(Triage 표 2), "DGX A100은 8개" 대신 장착된 GPU 전체, Triage의 A100 행을 row remapping을 쓰는 GPU에 적용 |
| SXID 단일 비트 ECC 19건 | "guest VM 영향이 없습니다"만 있던 영향 문장 앞에 FM 가이드의 bare metal 동작(실행 중인 작업을 중단하지 않고 새 작업도 막지 않음)을 추가 |

- 남은 범위: open-gpu-kernel-modules의 NVSwitch 드라이버는 SXID를 약 420개 정의하고, A100용 LR10 인터럽트 코드가 보고하는 164개 중 80개, H100용 LS10이 보고하는 221개 중 137개에는 전용 Runbook이 없다. 그러나 고정 Fleet SDK(`84f99bee`)와 최신 Fleet·GPUd의 SXID 매처는 자체 카탈로그 93개(이 저장소의 SXID Runbook과 같은 집합)에 없는 코드를 버리므로(`kmsg.go`의 `Match`가 `nil` 반환) 이 코드들은 D09 보고·알림·RCA로 들어오지 않는다. 전용 Runbook을 써도 생산자가 해당 코드를 내보내기 전에는 선택되지 않는다. FM 가이드는 이 코드들의 코드별 조치를 따로 싣지 않으며, 로그 줄의 Fatal/Non-fatal 표시와 포트 종류에 따른 일반 절차만 제공한다.
- XID 162~172는 카탈로그의 즉시 조치가 비어 있고, XID 173은 카탈로그(172번까지)에 없어 Fleet 고정 정의만 있다. 두 경우는 현재 서술을 유지한다.

## 출처 간 차이와 판정 제한

| 자료 상태 | 건수 | 의미 |
|---|---:|---|
| Unused·구세대 정의 확인 (`unused_or_legacy`) | 63 | 최신 Xid 표의 Unused. 구세대/Fleet 의미를 현행 장비에 바로 적용하지 않음 |
| 문헌/소스 정의 (`documented`) | 188 | 참조 자료에 정의가 있음. 운영 검증 완료를 뜻하지 않음 |
| 정의 차이 확인 (`definition_conflict`) | 13 | 현재 NVIDIA 표와 고정 Fleet의 정의 차이. 배포 버전 확인 전 전문 조치 보류 |
| 코드 소스만 확인 (`source_only`) | 2 | 참조 코드에는 있으나 이번 공식 표에서 직접 대응 항목을 확인하지 못함 |

특히 XID 142는 고정 Fleet/GPUd의 ECC 설명과 최신 NVIDIA의 NVENC3 설명이 다르다. XID 126–132·134–136·139·141은 고정 Fleet의 Reserved와 최신 표의 정의가 다르다. XID 173, SXID 20009는 코드 소스 근거와 공식 표의 범위를 분리했다. SXID 22012는 FM 가이드 표 23에 있어 문헌 정의로 분류한다. 미기재 action을 IGNORE로 변환하지 않는다.

SXID 10003은 GPUd EventType=Warning이어도 PotentialFatal/AlwaysFatal=true다. 이벤트 등급만으로 영향 범위를 결정하지 않는다. SXID 11001 등의 PotentialFatal은 source port의 access/trunk와 운영 모드(bare metal 또는 공유 NVSwitch 가상화)에 따라 판단하고, AlwaysFatal 그룹은 해당 FM 운영 모드의 전체 fabric 영향과 복구 전제를 설명한다. FM 가이드 표 22의 Guest VM 열은 가상화 모드의 영향·복구이며 bare metal 절차가 아니다. Single-bit ECC, TX replay, 열 시작/종료, 계획되지 않은 shutdown, 무시 가능한 interrupt는 별도 절차를 사용한다.

XID 144–150에는 NVIDIA Table 2의 버전별 decoder 행을 보존했다. R575 이전 V1과 이후 V2, intrInfo/errorStatus·action2·Xid154/동반 link-down 조건을 구분한다. 이것은 검토 가능한 문헌 지침이며 실행 중인 비트/시간 predicate 구현이 아니다. XID 74의 Hopper 레지스터 분기도 해당 문헌/장비 범위에 한정한다.

## DB 등록 및 실행 범위

비코드 Fleet 오류는 Runbook 1.2의 생산자·컴포넌트·비정상 보고 목표로 확장한다. 아래 17건은 작성 초안이며 아직 발행하지 않았다. 원천 컴포넌트 등록(기본 프로필 `health_contracts`), 출처 revision, Fleet 권고의 조건, 조치 후 확인을 검토한 뒤 새 revision을 발행한다. 상세 계약과 workflow 재사용은 [RCA README](../README.md#비코드-fleet-오류와-평가)를 따른다.

**284건 모두 `investigation_only: true`, `compatibility: {}`인 작성 초안**이다. 파일과 문헌 검토 범위의 콘텐츠 작성은 끝냈으며 실제 환경 연결은 별도 작업이다. Backend에 draft로 등록할 수 있고 적용 조건을 검수하기 전 승인·발행·RCA 런타임 적용은 차단한다. 환경 조건을 채워 발행한 뒤에도 조사용 콘텐츠 자체를 supported 원인·조기 완료·최종 eligible 조치의 근거로 쓰지 않는다.

현재 실행 가능한 공통 계획은 D09 원본 로그, D05 상태, D02 선택 사용률이다. Runbook이 추가로 요구하는 PCIe AER/ECC 카운터/FM 토폴로지/전력·열/앱 재현 자료는 운영 query와 parser가 실제 제공하는지 확인해야 한다. 임의의 D코드나 metric 이름을 만들지 않았으며 미연결 증거는 missing_inputs로 남긴다. 실제 조치 자동 실행은 없다.

전체 또는 종류별 draft 일괄 등록은 [runbook_import.py](../src/rcca_agent/runbook_import.py)를 사용한다. 재귀 검사·중단 후 재개·429 대기를 지원한다. 파일별 등록·revision·검토·발행·retire 명령은 [DB 등록 안내](DB-WORKFLOW.md)를 따른다. 예: `python -m rcca_agent.runbook_admin check rcca-agent/runbooks/xid/RB-XID-63.json --profile agents/config.example.json`. draft는 명시적 Backend 주소와 파일별 request key를 사용한다. 같은 knowledge_key가 이미 있으면 기존 knowledge_id의 새 revision으로 등록한다. 운영 적용 범위가 다른 파일에 fixture compatibility를 일괄 복사하지 않는다.

## 다른 PC에서 검토·수정하는 방법

[manifest](catalog-manifest.json)에 모든 코드→파일→knowledge_key, 근거 상태, NVIDIA 적용 제품/조치 분류, GPUd fatality와 참조 원문 SHA-256을 기록했다. 원문의 SHA는 수집 시점 식별용이며 운영 장비의 버전 증거가 아니다. 원문 HTML/Go 다운로드와 작업용 생성 도구는 `.local`에만 있으며 실행/DB 등록에 필요하지 않다. **Git에 있는 JSON 자체가 검토·수정할 작성 원본**이다. 런타임 자동 생성이나 자동 seed는 없다.

추가/수정 시 해당 JSON의 sources·checked_at·지침·limitations와 manifest를 함께 갱신한다. 기존 발행본은 덮어쓰지 않고 새 DB revision을 만든다. 다음 검사로 카탈로그 전체 누락·추가 코드·정확 검색·잘못된 원인/조치 승격 방지 계약을 확인한다.

```sh
python -m pytest -c agents/pytest.ini agents/tests/test_runbook_catalog.py agents/tests/test_runbook_contract.py -q
python tools/check_links.py
```

Backend 검증기도 전체 284개 JSON(컴포넌트 17개 포함)을 검사한다. 실제 DB E2E는 기존 migration의 격리 DB에서 신규 263건을 실제 일괄 등록 CLI로 draft 적재하고 재실행 시 중복 쓰기를 건너뛰는지 및 코드별 조회/hash를 확인하며, 기존 3건의 검토·발행·RCA 소비 검사를 계속 수행한다. 테스트 DB는 종료 후 재사용하지 않는다. 운영 DB 등록은 수행하지 않았고 모든 266건을 실제 장비에서 조사·회복 검증한 것은 아니다. 실제 실행 결과는 [Agent QA](../../agents/QA.md), [Backend QA](../../backend/QA.md)를 따른다.

## Fleet 컴포넌트 Runbook

코드 없는 Fleet 알림은 컴포넌트 이름으로만 선택된다(`decision_policy.applies_when.reported_component`). 보고 사유는 쉼표로 묶이거나 Healthy `ok` 보고와 섞이므로 게이트로 쓰지 않고, 사유별 분기는 운영자 지침 안에 둔다. "무엇이 알림을 냈는가"는 고정 Fleet SDK 소스(`84f99bee`)를, 의미와 다음 단계는 NVIDIA 문서·DCGM `dcgm_errors.h`(`9fae2867`)·커널 문서를 근거로 했다. 화면은 XID/SXID와 같은 6단 운영자 형식이며, 모든 컴포넌트가 즉시 확인 다음에 리셋·재부팅 전 진단 자료 보존 단계를 둔다.

| 컴포넌트 | Runbook | Unhealthy 보고 사유 | 조회 계획(D09 외) |
|---|---|---|---|
| `accelerator-nvidia-persistence-mode` | [RB-COMPONENT-PERSISTENCE-MODE](component/RB-COMPONENT-PERSISTENCE-MODE.json) | GPU lost, GPU requires reset, DCGM 조회 실패 | D02, D11 |
| `disk` | [RB-COMPONENT-DISK](component/RB-COMPONENT-DISK.json) | 읽기 전용 재마운트, RAID 실패, NVMe 경로·타임아웃·비활성화, 범위 밖 접근, 버퍼 I/O·superblock 오류 | D59, D60 |
| `accelerator-nvidia-dcgm-mem` | [RB-COMPONENT-DCGM-MEM](component/RB-COMPONENT-DCGM-MEM.json) | DCGM 메모리 건강 점검 FAIL(DBE, row remap 대기·실패, 격리 여부, SRAM) | D40, D36, D23, D50, D51, D52, D53, D54 |
| `accelerator-nvidia-dcgm-pcie` | [RB-COMPONENT-DCGM-PCIE](component/RB-COMPONENT-DCGM-PCIE.json) | DCGM PCIe 건강 점검 FAIL(replay 비율 등) | D44 |
| `accelerator-nvidia-dcgm-nvlink` | [RB-COMPONENT-DCGM-NVLINK](component/RB-COMPONENT-DCGM-NVLINK.json) | DCGM NVLink 건강 점검 FAIL(링크 다운, 오류율, BER) | D33, D34, D55, D56, D57 |
| `accelerator-nvidia-dcgm-nvswitch` | [RB-COMPONENT-DCGM-NVSWITCH](component/RB-COMPONENT-DCGM-NVSWITCH.json) | DCGM NVSwitch 치명·비치명 점검 FAIL | D33, D34, D55, D56, D57 |
| `accelerator-nvidia-dcgm-thermal` | [RB-COMPONENT-DCGM-THERMAL](component/RB-COMPONENT-DCGM-THERMAL.json) | DCGM 열 점검 FAIL(열 클록 제한, 온도 위반) | D04, D23, D45, D61 |
| `accelerator-nvidia-dcgm-power` | [RB-COMPONENT-DCGM-POWER](component/RB-COMPONENT-DCGM-POWER.json) | DCGM 전력 점검 FAIL(전력 클록 제한, 전력 값 읽기 실패) | D11, D48, D45, D62 |
| `accelerator-nvidia-dcgm-inforom` | [RB-COMPONENT-DCGM-INFOROM](component/RB-COMPONENT-DCGM-INFOROM.json) | DCGM InfoROM 점검 FAIL(InfoROM 손상) | D58 |
| `accelerator-nvidia-infiniband` | [RB-COMPONENT-INFINIBAND](component/RB-COMPONENT-INFINIBAND.json) | 활성 포트·속도 부족, 장시간 다운, flapping | 없음 |
| `accelerator-nvidia-nccl` | [RB-COMPONENT-NCCL](component/RB-COMPONENT-NCCL.json) | libnccl.so segfault | 없음 |
| `accelerator-nvidia-peermem` | [RB-COMPONENT-PEERMEM](component/RB-COMPONENT-PEERMEM.json) | nvidia-peermem invalid context | 없음 |
| `network-ethernet` | [RB-COMPONENT-NETWORK-ETHERNET](component/RB-COMPONENT-NETWORK-ETHERNET.json) | 모든 물리 이더넷 링크 다운 | D65, D66, D67, D68, D69 |
| `library` | [RB-COMPONENT-LIBRARY](component/RB-COMPONENT-LIBRARY.json) | libnvidia-ml.so·libcuda.so 없음 | 없음 |
| `os` | [RB-COMPONENT-OS](component/RB-COMPONENT-OS.json) | 좀비·PID·파일 핸들 임계 초과, OS 정보 조회 실패 | D70, D71, D72 |
| `cpu` | [RB-COMPONENT-CPU](component/RB-COMPONENT-CPU.json) | CPU 사용률·load 계산 실패(에이전트 수집 오류, 하드웨어 오류 아님). soft lockup·hung task는 별도 커널 로그 이벤트 | D18, D19 |
| `memory` | [RB-COMPONENT-MEMORY](component/RB-COMPONENT-MEMORY.json) | 가상 메모리·BPF JIT 정보 조회 실패(에이전트 수집 오류, 하드웨어 오류 아님). OOM은 별도 커널 로그 이벤트 | D63, D64 |

- Fleet 등록 컴포넌트 중 `accelerator-nvidia-dcgm-clock`·`-cpu`·`-prof`·`-utilization`은 수집 실패 외의 Unhealthy 판정이 없어 제외했다. 이 컴포넌트와 새 컴포넌트는 기존 일반 조사로 처리된다. 일반 조사 Runbook(RB-GENERAL-GPU-NODE)은 GPU Node Triage 순서의 운영자 지침(분류→보존→표 1 조치→표 2 리셋→DCGM 진단→공급사 전달 9항목)과 노드 요약 지표(D04·D11·D40·D18·D63)를 가지며, 전용 Runbook이 선택되지 않을 때만 `general_fallback`으로 표시된다. 패키지 기본 일반 조사(`general_runbook.json`)는 어떤 프로필에서도 검증되도록 이 지침·지표가 없는 이전 내용을 유지한다.
- 검사: `test_component_runbooks_are_registered_and_select_only_their_component`(등록·선택 범위), `test_shipped_component_guidance_survives_healthy_reports_before_failure`(Healthy 보고가 앞서는 실제 disk 구간에서 지침 표시).

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
| `sxid:22012` | [RB-SXID-22012](sxid/RB-SXID-22012.json) | fabric | 문헌/소스 정의 |
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
