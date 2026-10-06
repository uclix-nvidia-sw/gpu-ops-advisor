import { useSyncExternalStore } from 'react';
import { useLocation } from 'react-router-dom';
import { apiTraceSnapshot, clearApiTrace, subscribeApiTrace } from '../lib/api';

export function DeveloperContext() {
  const { pathname } = useLocation();
  const guide = pathname.startsWith('/schedules')
    ? [
        '정기 발생 검증',
        '일정 revision·effective_at·next_run_at을 확인한 뒤 발생 이력의 scheduled_for·period_start/end·job_id를 대조하세요. pending은 Backend 전달 대기, accepted는 JC 접수이며 분석 성공이 아닙니다. 일시중지는 기존 작업을 취소하지 않습니다.',
      ]
    : pathname.startsWith('/fleet')
      ? [
          '관측 신원·시간 검증',
          'scope·대상 신원·valid_from/to와 관측 시각을 대조하세요. 저장된 GPU–Pod 관계는 독점 할당을 보장하지 않습니다. 기대 대상 분모가 없는 관측률은 미확인입니다.',
        ]
      : pathname.startsWith('/knowledge')
        ? [
            'Runbook revision 검증',
            'knowledge_id·revision·content_hash·reviewed_content_hash와 발행 상태를 확인하세요. 발행본은 불변이며 변경에는 새 revision이 필요합니다. 형식 승인만으로 실제 조사 쿼리가 검증되지는 않습니다.',
          ]
        : pathname.startsWith('/settings')
          ? [
              '연결·모델 구성 검증',
              '연결 검사 transport와 schema를 구분하고 rca/report 라우팅의 model_id·model_revision을 확인하세요. 새 지정은 새 작업부터 반영됩니다. 서비스 readiness·모델 응답 성공은 분석 품질의 증명이 아닙니다.',
            ]
          : pathname === '/reports/new'
            ? [
                '보고서 접수 검증',
                'scope·기간·topic_ids·group_by를 확인하세요. 202 응답의 job_id로 작업을 조회합니다. 응답 유실 시 같은 본문·멱등 키를 재사용합니다. 기간·Namespace 활동률과 독점 할당량은 구분합니다.',
              ]
            : pathname === '/reports'
              ? [
                  '보고서 결과 추적',
                  '발행된 보고서 제목은 분석 본문을 엽니다. 입력 → 관측 → 계산 → 공개 기록은 별도 작업 상태·시도 이력에서 확인하세요. 실행 status와 result_status·narrative_status는 별개입니다.',
                ]
              : pathname === '/cases'
                ? [
                    'RCA 입력 추적',
                    '사건의 target·evidence_version을 확인하고 연결된 RCA 작업을 선택하세요. 알람·사건·검토 상태를 구분하며, 조사 이력에서 job_id와 공개 결과를 추적할 수 있습니다.',
                  ]
                : null;
  return guide ? (
    <aside className="dev-context">
      <b>{guide[0]}</b>
      <p>{guide[1]}</p>
    </aside>
  ) : null;
}

export function ApiInspector() {
  const traces = useSyncExternalStore(subscribeApiTrace, apiTraceSnapshot, apiTraceSnapshot);
  return (
    <details className="api-inspector">
      <summary>Backend 요청 관찰 · 최근 {traces.length}건</summary>
      <p>
        현재 탭의 공통 API 클라이언트가 관찰한 HTTP 메타데이터입니다. 쿼리 값·본문·비밀은 기록하지
        않습니다. 다운로드·내부 Worker 호출은 포함하지 않습니다. 페이지 새로고침 시 초기화됩니다.
      </p>
      <button className="button" onClick={clearApiTrace}>
        기록 지우기
      </button>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>시각</th>
              <th>요청</th>
              <th>HTTP</th>
              <th>소요</th>
              <th>요청 ID</th>
            </tr>
          </thead>
          <tbody>
            {traces.map((t) => (
              <tr key={t.id}>
                <td>{t.at.slice(11, 23)} UTC</td>
                <td>
                  <code>
                    {t.method} /api/v1{t.path}
                  </code>
                </td>
                <td>{t.status || '네트워크 실패'}</td>
                <td>{t.duration} ms</td>
                <td>
                  <code>{t.requestId || '미제공'}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
