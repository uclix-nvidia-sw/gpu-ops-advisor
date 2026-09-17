# 10. Chatbot Agent 모듈 설계서

문서 버전: 1.2 · 모듈 ID: chatbot · 대응: F09, F03/F05/F06/F10 연계 · 독립 실행·배포

## 1. 역할과 경계

GUI의 Agent Chatbot 버튼은 S16 대화 UI를 연다. 브라우저는 Backend를 호출하고 Backend는 Chatbot 내부 API를 호출한다. Chatbot은 일반 질문·화면 맥락·허용 조회·기존 결과 설명을 처리하며 대화와 메시지의 소유자다. 긴 원인 조사나 보고서 집계는 직접 구현하지 않고 RCA/보고서 Agent에 전달한다.

Backend에는 Chatbot의 프롬프트·추론 루프·대화 생성 처리기를 넣지 않는다. Chatbot 장애는 일반 관측 조회와 직접 RCA/보고서 요청을 막지 않는다. 채팅 세션 수와 모듈 복제 수는 별개다. 모델 라우팅의 기존 `assistant` 키는 Chatbot의 모델 역할 키로 유지한다.

## 2. 내부 API

아래 경로 앞에 `/internal/v1`을 붙인다. 외부 경로는 02에 정의하며 Backend가 현재 principal·scope와 요청 키를 보존해 중계한다.

| Method·경로 | 입력 | 결과 |
|---|---|---|
| GET/POST /conversations | 현재 본인 범위 / scope·제목 | 목록 / 201 conversation_id |
| GET/POST /conversations/{id}/messages | cursor / text·context·scope·time_range·멱등 키 | 저장 메시지 / 동기 답변 또는 202 message_id |
| GET /conversations/{id}/messages/{message_id} | 본인·현재 범위 | 메시지 상태·response·dispatch_ref·job_id |
| GET /dispatches/{id} | 현재 해당 메시지/결과 권한 | 전달 상태·근거 참조·job_id |
| POST /dispatches/{id}/cancel | If-Match·멱등 키·사유 | 15의 전달 취소 또는 Agent job 취소 결과 |
| GET /health/live, /health/ready | 서비스 내부 | 프로세스·DB/계약 준비 상태 |

메시지 입력·오류·대화 맥락의 공통 스키마는 02·03·07을 따른다. `message_id`는 질문과 답변을 연결하는 기준이며 임의로 다음 assistant 행을 찾아 결합하지 않는다.

## 3. 일반 대화 처리

Chatbot은 제한 시간 내 동기 JSON 응답을 사용한다. 접수 시 사용자 메시지·정규화 context/scope/time·본문 hash·모델/라우팅 revision을 먼저 저장하고 처리권을 한 번만 점유한다. 같은 `(principal,conversation_id,key)`의 같은 입력 재전송은 저장 응답을 반환하며 처리 중이면 202와 message_id·복구 URL을 반환한다. 질문·맥락·기간·범위가 다르면 409다. Chatbot의 처리 lease가 만료된 일반 메시지만 failed로 복구하며 같은 키로 생성 처리를 자동 중복 실행하지 않는다. 다시 생성은 새 키·이전 메시지 참조를 사용한다.

메시지 상태는 accepted/processing/completed/failed다. GET messages/{id}는 `message_id,status,text,response,context,model_ref,evidence_refs,dispatch_ref,job_id,error,created_at,completed_at`을 반환한다. response가 없으면 null이다. 전문 요청은 메시지와 전달 의도를 먼저 함께 저장한다. 목적지 Agent가 jobs.source_message_id와 source_dispatch_id의 유일성을 검증하여 접수하고, Chatbot은 접수 확인 후 메시지의 job 참조를 갱신한다. 한 메시지당 전문 전달과 job은 각각 한 건이다. 두 업무가 필요하면 사용자가 별도 요청으로 구분한다. 이미 연결된 job을 재전송 때문에 새로 만들지 않는다.

패널 닫기·응답 대기 중단은 로컬 표시 중단이며 서버 메시지나 전문 job 취소가 아니다. 다시 열면 같은 conversation/message를 조회한다. 전문 작업 취소는 명시적인 jobs/{id}/cancel을 사용한다. 화면 범위 변경은 이후 메시지에만 반영하며 과거 메시지 맥락·근거·모델을 변경하지 않는다.

일반 메시지 처리를 소유하는 프로세스는 Chatbot이다. Backend 재시작만으로 메시지를 failed로 바꾸지 않는다. Chatbot 복제본별 processing 점유·heartbeat를 보존하고 죽은 점유만 회수한다. 일반 답변의 자동 중복 생성은 하지 않으며 만료된 처리만 failed로 확정한다. accepted 저장 후 처리권 점유 전에 종료된 경우도 message_deadline_at 이후 failed로 확정한다. 완료·실패 기록은 현재 processing 소유자/lease와 상태 조건으로 경합을 막고, 이미 저장된 전문 전달의 복구는 계속한다. 모델 호출의 timeout·unknown 예약·예산은 15의 공유 규칙을 적용한다.

## 4. 전문 Agent로 전달

1. Chatbot이 요청 의미를 해석하되 대상·기간·목적/주제를 명시한다. 도구 결과나 모델 텍스트는 권한 근거가 아니다.
2. 요청자의 전문 작업 생성 권한을 재검증한다. 조회자는 설명·허용 조회만 가능하다.
3. 사용자 메시지와 목적지 `rca|report`, 고정 요청·scope·모델 설정과 하나의 module_dispatches 행을 같은 트랜잭션으로 저장한다.
4. Chatbot의 전달 루프가 `POST RCA /internal/v1/analyses` 또는 `POST Report /internal/v1/reports`를 고정 dispatch_id·멱등 키로 호출한다.
5. 목적지 Agent가 job을 커밋한 뒤에만 job_id가 생긴다. Chatbot은 전달 행과 메시지의 job 참조를 자기 트랜잭션으로 갱신한다.
6. 응답이 유실되면 같은 전달 ID로 재조회/재전송하여 같은 job으로 수렴한다. 새 메시지나 새 job을 만들지 않는다.

메시지당 전문 전달은 한 건이다. 두 전문 업무가 필요하면 별도 사용자 메시지로 구분한다. `message.status`는 대화 응답 상태이고 `dispatch_ref.status`는 전달 상태, `job.status`는 전문 실행 상태다. 전달 의도가 저장됐다는 안내 답변은 completed가 될 수 있어도 전문 분석 완료를 뜻하지 않는다.

```json
{
  "message_id": "e1167c94-3fdc-40ba-9237-b95a721b8801",
  "status": "completed",
  "response": {"text": "RCA 요청을 전달 중입니다."},
  "dispatch_ref": {
    "id": "1270dc18-8e2b-4cb1-b7bf-3ea5f66d9ba5",
    "status": "pending",
    "target_module": "rca"
  },
  "job_id": null
}
```

전달 저장 후 Chatbot이 종료되면 일반 답변 처리의 failed 여부와 별개로 저장된 전달은 복구한다. 사용자가 새 요청을 만들도록 유도하기 전에 기존 dispatch 상태를 조회한다. 패널 닫기는 메시지·전달·job 취소가 아니다.

## 5. 저장·의존성

소유 데이터: conversations, messages, source_module=chatbot 전달 행. 공통 evidence·llm_calls는 공유 저장 코드로 현재 요청 범위에서만 기록한다. 다른 Agent의 jobs/result는 수정하지 않는다. 읽기는 현재 권한을 적용하는 공통 조회 어댑터 또는 목적지 API를 사용한다.

의존성: Backend 진입, PostgreSQL, 공통 조회/Knowledge/LLM 라이브러리, 사내 추론, 전문 전달 시 RCA/보고서 API. RCA 장애 중에도 전문 전달 상태를 표시하고, 영향을 받지 않는 일반 대화는 계속 제공한다. 전달 재시도는 C07의 backoff·최대 시도·원래 deadline을 지키며 사용자에게 처리 중인지 실패했는지 구분해 알린다.

## 6. 완료 조건

T28의 메시지·맥락·멱등·재조회와 T40의 근거/설명을 통과한다. T43에서 전달 저장 직후, Agent 커밋 직후 응답 유실, Chatbot 재시작을 주입해 메시지 1개·전달 1개·job 1개를 확인한다. T46의 권한 철회, T48의 전달 취소 경합도 검증한다. 실제 상태는 NOT RUN이다.

[02 외부 계약](02_백엔드_API_작업명세서.md) · [03 데이터](03_데이터_설계서.md) · [15 공통 호출](15_모듈간_호출과_공통실행_계약.md)
