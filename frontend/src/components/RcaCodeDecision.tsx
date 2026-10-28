import { obj, rows, str, strings, type Row } from '../lib/live';

const rules: Record<string, string> = {
  required_evidence: '필수 근거 누락',
  approved_runbook: '조사 지침 부재',
  incident_mapping: '필수 사건 대상 연결 누락',
  target_identity_conflict: '대상 식별 충돌',
  error_code_unparsed: 'XID/SXID 코드 해석 불가',
  alert_report_not_found: '알람에 대응하는 상태 보고 없음',
  report_reason_changed: '알람과 상태 보고의 사유 불일치',
  event_missing: '대응하는 원본 이벤트 부재',
  preceding_healthy: '첫 오류보다 앞선 정상 보고 존재',
  multiple_devices: '여러 장치의 이벤트',
  pci_mismatch: 'PCI 주소 불일치',
  uuid_unresolved: 'GPU UUID 확인 불가',
  uuid_mismatch: 'GPU UUID 불일치',
  collection_failed: 'D09 수집 실패·사용 불가',
  alert_match_gap: '알람 대조 결과를 누락 사유에 포함',
  observation_degraded: '필수 수집 실패',
  conflicting_evidence: '상태 근거 상충',
  unknown_value: '해석할 수 없는 상태 값',
};

const names: Record<string, string> = {
  'alert_match.status': '알람·로그 대조 결과',
  result_status: '전체 산출 상태',
  missing_inputs: '최종 누락 사유',
  gaps: '수집 판정의 누락 사유',
  gate: '관측 자료 상태',
  analysis_status: 'AI 분석 상태',
  analysis_missing: '분석 후 합친 누락 사유',
  first_unhealthy_at: '선택한 첫 오류 보고',
  last_healthy_at: '그 이전 마지막 정상 보고',
  preceding_healthy_count: '첫 오류 이전 정상 보고 수',
  matched_event_count: '대응하는 원본 이벤트 수',
  reports_count: '대상·컴포넌트의 오류 보고 수',
  same_reason_count: '알람 사유가 일치하는 보고 수',
  termination_reason: '종료 사유',
  optional_failed: '실패한 선택 조회',
  time_basis: '시각 기준',
};

function valueText(value: unknown): string {
  if (value === null) return 'null · 값 없음';
  if (value === undefined) return '미기록';
  if (typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.length ? value.map(valueText).join(', ') : '[] · 빈 목록';
  if (typeof value === 'object')
    return Object.entries(obj(value))
      .map(([k, v]) => `${k}: ${valueText(v)}`)
      .join(' / ');
  return String(value);
}

function Fields({ value }: { value: Row }) {
  return (
    <dl className="rca-decision-fields">
      {Object.entries(value).map(([key, item]) => (
        <div key={key}>
          <dt>
            {names[key] && (
              <span>
                {names[key]}
                <br />
              </span>
            )}
            <code>{key}</code>
          </dt>
          <dd>{valueText(item)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function RcaCodeDecision({
  record,
  onEvidence,
  evidenceLabels = {},
}: {
  record: Row;
  onEvidence: (id: string) => void;
  evidenceLabels?: Record<string, string>;
}) {
  const body = obj(record.snapshot);
  const frozen = record.query_id === 'rca_result_frozen';
  const recorded = body.schema === 'rca-code-decision/1';
  if (!frozen && !recorded) return null;
  const material = obj(body.material);
  const match = obj(obj(material.analysis).alert_match);
  const refs = strings(body.decision_evidence_refs);
  if (frozen)
    return (
      <section className="rca-code-decision" aria-label="저장된 판정 근거">
        <h4>부분 산출·누락 사유 추적</h4>
        <Fields
          value={{
            'alert_match.status': match.status,
            missing_inputs: material.missing_inputs,
          }}
        />
        {refs.length ? (
          refs.map((id, i) => (
            <button key={id} className="text-link" onClick={() => onEvidence(id)}>
              {i === 0 ? '수집 결과 코드 판정 열기' : '최종 산출 상태 판정 열기'}
            </button>
          ))
        ) : (
          <>
            <p className="notice warning">
              이전 기록: 코드 판정의 독립 실행 기록이 없습니다. 위 값은 당시 저장 결과이며, 조건별
              입력·분기와 적용 코드 버전은 미기록입니다.
            </p>
            {match.status === 'event_not_found' && (
              <div>
                <p>
                  <code>event_not_found</code>는 시작 근거 부족을 나타내는 저장 코드입니다. 현재
                  코드의 처리 경로는{' '}
                  <code>match_alert → gaps → missing_inputs → result_status</code>
                  입니다. 당시 어떤 보고를 선택했는지는 이 기록만으로 재판정하지 않습니다.
                </p>
                <details>
                  <summary>현재 코드 기준 참고 · 당시 실행 기록 아님</summary>
                  <p>
                    <code>rcca_agent.fleet_events.match_alert()</code>: 알림과 같은 서버·PCI·오류
                    코드의 이벤트를 먼저 찾습니다. 다른 장치·오류는 참고 자료로 유지합니다. 대응
                    이벤트가 없을 때만 같은 사유의 상태 보고와 그 이전 정상 보고를 검사합니다.
                  </p>
                  <pre className="rca-decision-expression">
                    {
                      'not matched and not healthy → alert_match.status = "event_not_found"\nalert_match.status in MISMATCH_CODES → gaps.append(alert_match.status)\nanalysis_missing.extend(gaps) → assessment.missing_inputs → result_status(assessments)'
                    }
                  </pre>
                  <p>
                    <code>healthy</code>는 같은 대상·컴포넌트에서{' '}
                    <code>observed_at &lt; first</code>인 정상 보고입니다. 첫 오류 이후 전환을 모두
                    찾는 조건이 아닙니다.
                  </p>
                </details>
              </div>
            )}
            {strings(match.evidence_refs).map((id, i) => (
              <button key={id} className="text-link" onClick={() => onEvidence(id)}>
                판정에 연결된 원문 {i + 1}
                {evidenceLabels[id] ? ` · ${evidenceLabels[id]}` : ''}
              </button>
            ))}
          </>
        )}
      </section>
    );
  const outputs = obj(body.outputs);
  const checks = rows(body.checks);
  const assessments = rows(outputs.assessments);
  const summary = Object.fromEntries(
    Object.entries(outputs).filter(([k]) => !['assessments', 'alert_match'].includes(k)),
  );
  if (outputs.alert_match) summary['alert_match.status'] = obj(outputs.alert_match).status;
  return (
    <section className="rca-code-decision" aria-label="코드 판정 과정">
      <p className="rca-decision-flow">수집 입력 → 코드 조건 → 판정값 → 산출 상태</p>
      <h4>판정 결과</h4>
      <Fields value={summary} />
      <p>
        처리 함수: <code>{str(body.source)}</code> · 기록 규격: <code>{str(body.schema)}</code>
      </p>
      <p>
        실행 당시의 입력과 조건식입니다. 조건 성립 여부는 장비 정상·고장 판정과 다릅니다. 실행하지
        않은 후속 분기는 기록하지 않습니다.
      </p>
      {record.query_id === 'collection_assessment' ? (
        <p>
          <code>gaps</code>는 분석 후 누락 사유에 합쳐집니다. 전체 <code>result_status</code>는 뒤의
          ‘최종 산출 상태 판정’에서 결정합니다.
        </p>
      ) : (
        <p>
          각 조사 지침의 누락 사유와 사용 가능한 자료로 상태를 정하고, 그 상태들을 합쳐 전체 산출
          상태를 결정합니다.
        </p>
      )}
      <h4>입력·적용 기준</h4>
      <Fields value={obj(body.inputs)} />
      {checks.map((c, index) => (
        <details
          className="rca-decision-check"
          key={`${str(c.rule)}-${index}`}
          open={c.value === true || c.rule === 'preceding_healthy'}
        >
          <summary>
            {index + 1}. {rules[str(c.rule)] || str(c.rule)} ·{' '}
            {c.value === true
              ? '조건 성립 (true)'
              : c.value === false
                ? '조건 불성립 (false)'
                : '판정값 미기록'}
          </summary>
          <p>
            <code>{str(c.rule)}</code> · <code>{str(c.source, str(body.source))}</code>
          </p>
          <pre className="rca-decision-expression">{str(c.expression, '조건식 미기록')}</pre>
          <Fields value={obj(c.inputs)} />
          {c.rule === 'preceding_healthy' && (
            <p>
              첫 오류 보고보다 이전인 정상 보고만 검사합니다. 첫 오류 이후의 정상→오류 재전환은 이
              조건에 반영하지 않습니다. 시각은 Loki 기록 시각입니다.
            </p>
          )}
        </details>
      ))}
      {!!assessments.length && (
        <div className="table-wrap">
          <table>
            <caption>조사 지침별 산출 판정</caption>
            <thead>
              <tr>
                <th>assessment_id</th>
                <th>status</th>
                <th>missing_inputs</th>
              </tr>
            </thead>
            <tbody>
              {assessments.map((a, i) => (
                <tr key={i}>
                  <td>
                    <code>{str(a.assessment_id)}</code>
                  </td>
                  <td>{str(a.status)}</td>
                  <td>{valueText(a.missing_inputs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p>연결 근거</p>
      {strings(body.evidence_refs).map((id, i) => (
        <button key={id} className="text-link" onClick={() => onEvidence(id)}>
          근거 {i + 1} · {evidenceLabels[id] || id.slice(0, 8)}
        </button>
      ))}
    </section>
  );
}
