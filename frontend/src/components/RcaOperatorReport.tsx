import { num, obj, rows, str, strings, type Row } from '../lib/live';
import { aiFailure, operatorView, sentences, valueText } from '../lib/rcaOperatorView';
import { gapMeaning } from '../lib/rcaGuidance';
import { rcaReasons } from '../lib/rcaLabels';
import { formatRcaTime } from '../lib/rcaTime';
import { Ids, RcaPoints, ToneBadge } from './RcaReportParts';
import { RcaTriageObservations } from './RcaTriageObservations';
import { RcaHostHistory } from './RcaHostHistory';

const TRIAGE_URL = 'https://docs.nvidia.com/deploy/gpu-debug-guidelines/gpu-node-triage.html';
const FM_URL = 'https://docs.nvidia.com/datacenter/tesla/fabric-manager-user-guide/index.html';

// Fixed report template: 1 summary, 2 response order, 3 logs/metrics, 4 analysis,
// 5 history, 6 references. Every section is filled from stored result fields.
export function RcaOperatorReport({
  result,
  decisionSummary = false,
  onEvidence,
  alarm,
}: {
  result: Row;
  decisionSummary?: boolean;
  onEvidence?: (id: string) => void;
  /** The incident as it is now; the report itself is a snapshot from its query window. */
  alarm?: Row;
}) {
  const quality = obj(result.quality);
  const v = operatorView(result);
  // Judgment-step labels for the reason this alert reported (component Runbooks).
  const branches = [
    ...new Set((v?.currentReasons || []).flatMap((r) => (r.branch ? [r.branch] : []))),
  ];
  const narrative = rows(result.narrative).map((section) =>
    section.id === 'limits'
      ? {
          ...section,
          text: str(section.text)
            .split('\n')
            .filter(
              (line) =>
                !/^(분석 품질 검토:|조사 종료 이유:|분석 처리 상태: 독립 품질 검토|LLM 검토는 정답을|증거 의미 해석을 완료하지 못해 해석 결과는 미검토)/.test(
                  line.trim(),
                ),
            )
            .join('\n'),
        }
      : section,
  );
  const sources = rows(obj(quality.report).source_items);
  const guidance = rows(quality.runbook_guidance).filter(
    (r) => r.report_applicability !== 'reference_only',
  );
  const paragraphs = (id: string) =>
    narrative
      .filter((s) => s.id === id)
      .flatMap((s) => str(s.text).split(/\n\s*\n/))
      .filter(Boolean);
  // Fixed code sentences repeat Q1-Q5; only model-written analysis is shown here.
  const notes = sources.filter(
    (r) =>
      r.section === 'cause' &&
      r.fixed !== true &&
      !str(r.text).startsWith('발행 Runbook의 오류 설명:'),
  );
  // Older results without source items keep their stored cause prose.
  const noteTexts = sources.length ? notes.map((r) => str(r.text)) : paragraphs('cause');
  const refs = guidance.flatMap((g) => rows(g.sources));
  const links = (value: unknown) =>
    [...new Set(strings(value))].map((id, i, all) =>
      onEvidence ? (
        <button className="text-link" key={id} onClick={() => onEvidence(id)}>
          {all.length > 1 ? `근거 원문 ${i + 1}` : '근거 원문'}
        </button>
      ) : null,
    );
  const missing = strings(result.missing_inputs);
  const ai = aiFailure(result);
  const [identity, timing, telemetry, repeat] = v?.findings || [];
  const facts = paragraphs('problem').length
    ? paragraphs('problem')
    : rows(result.facts).length
      ? rows(result.facts)
          .map((f) => str(f.text))
          .filter(Boolean)
      : v
        ? [identity.verdict, timing.verdict, telemetry.verdict, repeat.verdict]
        : [];
  const gaps = [
    ...new Set([
      ...missing.map(
        (code) => gapMeaning(code, result) || rcaReasons[code] || `미확인 조건: ${code}`,
      ),
      ...paragraphs('limits'),
      ...strings(result.limitations),
    ]),
  ];
  const savedChecks = [...paragraphs('action'), ...paragraphs('next')];
  const nextChecks = savedChecks.length
    ? savedChecks
    : (v?.actionChecks || []).map((c) => `${str(c.title)} — ${str(c.text)}`);
  const first = v?.actionChecks[0];
  const maxCount = Math.max(1, ...(v?.devices || []).map((d) => d.count));
  // Sections 1 and 3 need the triage observations; say why they are empty.
  const books = rows(result.runbook_revisions).filter(
    (b) => !str(b.knowledge_key).includes('GENERAL'),
  );
  const used = books.length
    ? ` (사용 Runbook: ${books.map((b) => `${str(b.knowledge_key)} rev ${num(b.revision)}`).join(', ')})`
    : '';
  // The 30-minute comparison exists only for XID/SXID plans; component alerts never get one.
  const noSummary = books.some((b) => /^RB-S?XID-/.test(str(b.knowledge_key)))
    ? `이 결과에는 1·3장을 채우는 요약 자료가 저장되지 않았습니다${used}. 대개 지표 조회 계획이 없는 이전 Runbook revision으로 실행된 경우이며, 최신 revision으로 다시 분석하면 채워집니다.`
    : `1·3장의 요약과 30분 로그·지표 비교는 XID/SXID 오류에만 만듭니다${used}. 2·4·5·6장을 확인하세요.`;
  const podText = (w: { name: string; gpus: string; gpuCount: number }) =>
    `${w.name} (${w.gpus}${w.gpuCount > 1 ? ` · ${w.gpuCount}개 함께 사용` : ''})`;
  return (
    <section
      id="final-report"
      className="rca-narrative rca-operator-report"
      aria-label="RCA 최종 보고서"
    >
      <header className="rca-narrative-header">
        <h3>RCA 장애 보고서{v ? ` · ${v.node} · ${v.codes.join(', ')}` : ''}</h3>
        {v?.family === 'component' && (
          <p>
            {v.codes[0]} 컴포넌트 · 노드 {v.node} · {v.targetShort}
          </p>
        )}
        {v && v.family !== 'component' && (
          <p>
            {v.family === 'nvswitch' ? 'NVSwitch' : `GPU${v.gpuIndex ? ` ${v.gpuIndex}` : ''}`} PCI{' '}
            <code className="rca-id">{v.alertPci || '—'}</code>
            {v.alertUuid && (
              <>
                {' '}
                · <code className="rca-id">{v.alertUuid}</code>
              </>
            )}
            {[v.gpuModel, v.driver && `드라이버 ${v.driver}`].filter(Boolean).map((x) => ` · ${x}`)}
          </p>
        )}
        <div className="rca-chips">
          {alarm?.alarm_status === 'firing' && <ToneBadge tone="alert" label="지금 알림 발생 중" />}
          {alarm?.alarm_status === 'resolved' && (
            <ToneBadge
              tone="ok"
              label={`알림 해제됨${str(alarm.alarm_resolved_at) ? ` · ${formatRcaTime(str(alarm.alarm_resolved_at))}` : ''}`}
            />
          )}
          {v?.ongoing && <ToneBadge tone="alert" label="조회 종료 시점에도 보고 중" />}
          {v && v.sameDeviceCount > 1 && (
            <ToneBadge
              tone="alert"
              label={`같은 ${{ nvswitch: '스위치', gpu: 'GPU', component: '노드·사유' }[v.family]} ${v.sameDeviceCount}번째 발생`}
            />
          )}
          {missing.some((c) => c !== 'synthesis_failed' && c !== 'event_not_found') && (
            <ToneBadge tone="warn" label="일부 자료로 작성" />
          )}
          {missing.includes('synthesis_failed') && (
            <ToneBadge
              tone="unknown"
              label={`AI 해석 실패${ai.status ? ` · HTTP ${ai.status}` : ''}`}
            />
          )}
          {missing.includes('event_not_found') && !v?.onsetText && (
            <ToneBadge tone="unknown" label="시작 시각 미확인" />
          )}
        </div>
        {missing.includes('synthesis_failed') && (
          <p className="rca-muted">
            {`AI가 쓰는 해석 문장만 빠졌습니다${ai.reason ? ` — ${ai.reason}` : ''}. 아래 표와 판정은 수집한 로그·지표를 코드로 계산한 결과입니다.`}
          </p>
        )}
      </header>

      {decisionSummary && (
        <section className="rca-decision-summary" aria-label="사건 판단 요약">
          <h4>사건 판단</h4>
          <div className="rca-decision-grid">
            <article>
              <h5>확인한 사실</h5>
              <RcaPoints
                items={
                  facts.length ? facts.slice(0, 2) : ['저장된 관측 사실을 확인할 수 없습니다.']
                }
              />
              {facts.length > 2 && (
                <details>
                  <summary>나머지 관측 사실 {facts.length - 2}건</summary>
                  <RcaPoints items={facts.slice(2)} />
                </details>
              )}
              <a href="#rca-observation-detail">로그·지표 확인</a>
            </article>
            <article>
              <h5>원인 후보</h5>
              <p className="rca-muted">후보는 확정 원인이 아닙니다.</p>
              <RcaPoints
                items={
                  noteTexts.length
                    ? noteTexts.slice(0, 2)
                    : [
                        v?.causeNote
                          ? `발행 Runbook의 일반 조사 방향: ${v.causeNote}`
                          : '저장된 원인 후보가 없습니다.',
                      ]
                }
              />
              <a href="#rca-analysis-detail">분석과 근거 확인</a>
            </article>
            <article>
              <h5>확인하지 못한 사항</h5>
              <RcaPoints
                items={
                  gaps.length
                    ? gaps.slice(0, 3)
                    : [
                        '저장된 제한 사항이 없습니다. 원인 확정이나 현재 정상 상태를 뜻하지 않습니다.',
                      ]
                }
              />
              {gaps.length > 3 && (
                <details>
                  <summary>나머지 제한 {gaps.length - 3}건</summary>
                  <RcaPoints items={gaps.slice(3)} />
                </details>
              )}
            </article>
            <article>
              <h5>다음 확인</h5>
              <RcaPoints
                items={
                  nextChecks.length
                    ? nextChecks.slice(0, 2)
                    : ['저장된 확인 제안이 없습니다. 수집된 근거와 미확인 사항부터 검토하세요.']
                }
              />
              {nextChecks.length > 2 && (
                <details>
                  <summary>나머지 확인 제안 {nextChecks.length - 2}건</summary>
                  <RcaPoints items={nextChecks.slice(2)} />
                </details>
              )}
              <a href="#rca-response-reference">전체 확인 순서·공통 절차</a>
            </article>
          </div>
        </section>
      )}

      {v && (
        <section className="rca-glance" aria-label="사건 핵심 요약">
          <h4>
            1. 한눈에 보기 · {v.node} · {v.codes.join(', ') || '장애 알림'}
          </h4>
          <RcaPoints
            items={[
              `무엇: ${v.codes.join(', ')} — ${sentences(v.meaning)[0] || v.message}${v.family === 'component' && !v.currentReasons.length ? ` · Fleet 보고 사유: ${v.message}` : ''}`,
              ...(v.currentReasons.length
                ? [
                    `이번 사유: ${v.currentReasons.map((r) => r.label).join(' · ')} (Fleet 원문: ${v.message})`,
                  ]
                : []),
              ...(v.reasons.length > 1
                ? [
                    `가능한 사유 ${v.reasons.length}가지: ${v.reasons.map((r) => (v.currentReasons.includes(r) ? `${r.label}(이번)` : r.label)).join(' · ')}`,
                  ]
                : []),
              v.family === 'component'
                ? `대상: ${v.cluster ? `${v.cluster} · ` : ''}${v.node} · ${v.target}`
                : `대상: ${v.cluster ? `${v.cluster} · ` : ''}${v.node} · ${v.family === 'nvswitch' ? 'NVSwitch' : 'GPU'} PCI ${v.alertPci || '—'}${v.alertUuid ? ` · ${v.alertUuid}` : ''}`,
              `언제: ${v.eventTime ? `${formatRcaTime(v.eventTime)} ${v.eventLabel}` : v.onsetText || '시작 시각 미확인'} — ${timing.verdict}`,
              ...v.otherNotes.map((note) => `같은 노드 다른 오류: ${note}`),
              ...(v.workloads.some((w) => w.atIncident)
                ? [
                    `누구에게 영향: ${v.workloads
                      .filter((w) => w.atIncident)
                      .map(podText)
                      .join(
                        ', ',
                      )}${v.family === 'nvswitch' ? ' — NVSwitch가 연결하는 노드 GPU의 작업' : ''} (DCGM 지표 라벨 기준)`,
                  ]
                : v.family === 'component'
                  ? [
                      `누구에게 영향: 수집한 자료에 파드 정보가 없습니다 — kubectl get pods -A -o wide --field-selector spec.nodeName=${v.node}로 이 노드의 작업을 확인하세요`,
                    ]
                  : v.metrics.length
                    ? [
                        v.podsKnown
                          ? `누구에게 영향: 사건 시각에 ${v.family === 'nvswitch' ? '노드 GPU' : '이 GPU'}를 쓰던 파드가 DCGM 지표 라벨에 없습니다 (작업 영향 미관측)`
                          : '누구에게 영향: 수집한 지표에 파드 정보가 없어 확인하지 못했습니다 — kubectl get pods -A -o wide로 노드의 작업을 확인하세요',
                      ]
                    : []),
              ...(v.neighbours.length
                ? [
                    `같은 노드 다른 GPU 작업: ${v.neighbours.map((w) => `${w.name} (${w.gpus})`).join(', ')}`,
                  ]
                : []),
              `처음인가: ${repeat.verdict}`,
              ...(first
                ? [`우선 대응: ${str(first.title)} — ${sentences(str(first.text))[0]}`]
                : []),
            ]}
          />
        </section>
      )}
      {!v && (
        <section className="rca-glance" aria-label="사건 핵심 요약">
          <h4>1. 한눈에 보기</h4>
          <p className="rca-muted">{noSummary}</p>
        </section>
      )}

      <section id="rca-response-reference" className="rca-narrative-section">
        <h4>2. 대응 순서</h4>
        <p className="rca-muted">
          <a href={TRIAGE_URL} target="_blank" rel="noreferrer">
            NVIDIA GPU Node Triage
          </a>{' '}
          순서: 대상 확정 → 진단 자료 보존 → 작업 배출·복구 → 조치 후 확인 → 공급사 전달. 실제
          조치는 운영자가 수행하며, 직전에 노드와 장치 PCI 주소를 다시 대조하세요.
        </p>
        {v && guidance.length ? (
          <>
            {v.message && (
              <p>
                이번 로그 원문: <Ids text={v.message} />
                {branches.length > 0 &&
                  ` — '${v.currentReasons.map((r) => r.label).join(' · ')}'에 해당합니다. 아래 판단 단계에서 ▶로 표시한 항목을 따르세요.`}
              </p>
            )}
            <ol className="rca-steps">
              <li>
                <div className="rca-step-head">
                  <strong>대상 장치 확정</strong>{' '}
                  <ToneBadge tone={identity.tone} label={identity.label} />
                </div>
                <p>{identity.verdict}</p>
                <RcaPoints items={sentences(str(v.targetCheck?.text))} />
              </li>
              {v.actionChecks.map((c, i) => (
                <li key={i}>
                  <div className="rca-step-head">
                    <strong>{str(c.title)}</strong>
                  </div>
                  <RcaPoints
                    items={sentences(str(c.text)).map((line) =>
                      branches.some((b) => line.startsWith(`${b}:`)) ? `▶ ${line}` : line,
                    )}
                  />
                </li>
              ))}
              {/* Generic triage close-out unless the published Runbook already covers it. */}
              {v.family !== 'component' &&
                !v.actionChecks.some((c) => str(c.text).includes('dcgmi diag')) && (
                  <li>
                    <div className="rca-step-head">
                      <strong>조치 후 확인·에스컬레이션</strong>
                    </div>
                    <RcaPoints
                      items={[
                        '재인식 확인: 같은 장치가 다시 인식·접근되는지와 같은 오류의 재발 여부를 확인합니다.',
                        '정밀 진단: 하드웨어 문제가 의심되거나 재발하면 dcgmi diag -r 3(약 30분)으로 진단합니다.',
                        '공급사 전달: 해결되지 않으면 아래 전달 자료를 갖춰 시스템 공급사에 티켓을 제출합니다.',
                      ]}
                    />
                  </li>
                )}
            </ol>
            {guidance.map((g, i) => (
              <span key={i}>{links([g.evidence_id])}</span>
            ))}
            {v.family !== 'component' && (
              <div className="rca-history-table">
                <table>
                  <caption>
                    공급사 전달 자료 체크리스트 (NVIDIA GPU Node Triage) · ✅ 이 보고서에 있음 · ⬜
                    미수집(운영자가 확보) · ✍ 운영자가 작성
                  </caption>
                  <thead>
                    <tr>
                      <th>전달 자료</th>
                      <th>이 보고서</th>
                      <th>운영자가 할 일</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>이슈 요약·핵심 로그</td>
                      <td>✅ 1·3장</td>
                      <td>원문 링크와 함께 첨부</td>
                    </tr>
                    <tr>
                      <td>장치 식별(PCI·UUID)</td>
                      <td>{identity.tone === 'ok' ? '✅ 알림·로그 일치' : '⚠️ 대조 필요'}</td>
                      <td>조치 직전 재확인</td>
                    </tr>
                    <tr>
                      <td>관련 지표·이전 사건</td>
                      <td>✅ 3·5장</td>
                      <td>—</td>
                    </tr>
                    <tr>
                      <td>수행한 조치 단계</td>
                      <td>
                        ✍ 운영자 작성
                        <br />
                        <small>이 보고서는 조치를 수행하지 않습니다</small>
                      </td>
                      <td>수행한 조치·시각·결과를 티켓에 기록</td>
                    </tr>
                    <tr>
                      <td>OS·드라이버 버전</td>
                      <td>
                        {v.driver ? (
                          <>
                            {`✅ 드라이버 ${v.driver} (DCGM 라벨)`}
                            <br />⬜ OS 미수집
                          </>
                        ) : (
                          '⬜ 미수집'
                        )}
                      </td>
                      <td>
                        {v.driver
                          ? 'OS는 /etc/os-release·uname -r로 확인'
                          : 'nvidia-smi와 /etc/os-release로 확인'}
                      </td>
                    </tr>
                    <tr>
                      <td>nvidia-bug-report.sh</td>
                      <td>⬜ 미수집</td>
                      <td>재시작·리셋 전에 확보</td>
                    </tr>
                    {v.family === 'nvswitch' && (
                      <tr>
                        <td>Fabric Manager 로그</td>
                        <td>⬜ 미수집</td>
                        <td>HGX 시스템 필수 · 재부팅 전에 확보</td>
                      </tr>
                    )}
                    <tr>
                      <td>DCGM 진단 로그</td>
                      <td>⬜ 미수집</td>
                      <td>dcgmi diag 실행 후 첨부</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
            {v.family !== 'component' && (
              <details>
                <summary>GPU·NVSwitch 리셋 방식 선택 (NVIDIA GPU Node Triage 표 2)</summary>
                <div className="rca-history-table">
                  <table>
                    <thead>
                      <tr>
                        <th>구성</th>
                        <th>리셋 방식</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>Ampere+ NVSwitch · bare metal · FM 실행 중</td>
                        <td>GPU 개별 리셋 가능, FM이 해당 NVSwitch 링크를 함께 리셋</td>
                      </tr>
                      <tr>
                        <td>Ampere+ NVSwitch · bare metal · FM 미실행</td>
                        <td>개별 리셋 불가, NVLink로 연결된 GPU·NVSwitch 전체 리셋</td>
                      </tr>
                      <tr>
                        <td>Hopper+ NVSwitch · bare metal</td>
                        <td>개별 리셋 지원, -i 없이 nvidia-smi 리셋 시 전체 리셋</td>
                      </tr>
                      <tr>
                        <td>가상화(VM 안의 GPU)</td>
                        <td>
                          GPU 리셋 미지원 → VM 재시작 (Hopper+는 하이퍼바이저 권한에 따라 다름)
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p className="rca-muted">
                  리셋은 대상 GPU를 쓰는 프로세스가 없어야 하며 root 권한이 필요합니다. 작업 배출 후
                  수행합니다.
                </p>
              </details>
            )}
          </>
        ) : (
          paragraphs('action').map((text, i) => <p key={i}>{text}</p>)
        )}
      </section>

      <section id="rca-observation-detail">
        {v ? (
          <RcaTriageObservations result={result} onEvidence={onEvidence} />
        ) : (
          <section className="rca-host-history" aria-label="사건 로그와 관련 지표">
            <h4>3. 관련 로그·메트릭</h4>
            <p className="rca-muted">{noSummary}</p>
          </section>
        )}
      </section>

      <section id="rca-analysis-detail" className="rca-narrative-section">
        <h4>4. 분석 및 해석</h4>
        {v ? (
          <>
            <p className="rca-muted">
              수집한 로그·지표·사건 이력으로 운영자가 먼저 알아야 할 다섯 질문에 답합니다. ‘추정’
              표시는 확정이 아닌 점검 방향입니다.
            </p>
            {v.findings.map((f, i) => (
              <article key={f.key} className={`rca-finding tone-${f.tone}`}>
                <header>
                  <span className="rca-q">Q{i + 1}</span>
                  <h5>{f.question}</h5>
                  <ToneBadge tone={f.tone} label={f.label} />
                </header>
                <p className="rca-verdict">{f.verdict}</p>
                <RcaPoints items={f.points} />
                {f.key === 'telemetry' && !v.multiGpu && v.metrics.length > 0 && (
                  <div className="rca-history-table">
                    <table>
                      <thead>
                        <tr>
                          <th style={{ width: '38%' }}>지표</th>
                          <th>사건 전 (직전)</th>
                          <th>사건 후</th>
                          <th style={{ width: '20%' }}>판정</th>
                        </tr>
                      </thead>
                      <tbody>
                        {v.metrics.map((m, j) => (
                          <tr key={j}>
                            <td>{m.name}</td>
                            <td>
                              {m.whole
                                ? `조회 구간 ${m.wholeText}`
                                : m.before
                                  ? `${valueText(m.before.last, m.unit)}${m.before.min !== m.before.max ? ` (${m.beforeText})` : ''}`
                                  : '표본 없음'}
                            </td>
                            <td>{m.whole ? '—' : m.afterText || '수집 전'}</td>
                            <td>
                              <ToneBadge tone={m.tone} label={m.tag} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {links(f.refs)}
              </article>
            ))}
            {noteTexts.length > 0 && (
              <article className="rca-finding tone-unknown">
                <header>
                  <h5>AI 해석</h5>
                </header>
                <RcaPoints items={noteTexts} />
                {links(notes.flatMap((r) => strings(r.evidence_refs)))}
              </article>
            )}
          </>
        ) : (
          paragraphs('cause').map((text, i) => <p key={i}>{text}</p>)
        )}
        <details>
          <summary>저장된 비교 원문</summary>
          {paragraphs('comparison')
            .filter(
              (text) => !sources.some((r) => r.detail_only === true && str(r.text) === text.trim()),
            )
            .map((text, i) => (
              <p key={i}>{text}</p>
            ))}
        </details>
      </section>

      <section className="rca-narrative-section">
        <h4>5. 이전 사건 이력</h4>
        {v && v.devices.length > 0 && (
          <figure className="rca-bars" aria-label="장치별 같은 오류 사건 수">
            <figcaption>
              같은 오류({v.codes.join(', ')})의 장치별 사건 수 ·{' '}
              <span className="rca-legend-current">■</span> 이번 장치
            </figcaption>
            {v.devices.map((d) => (
              <div key={d.label} className={d.current ? 'rca-bar current' : 'rca-bar'}>
                <span>{d.label}</span>
                <span className="rca-bar-track">
                  <span style={{ width: `${(d.count / maxCount) * 100}%` }} />
                </span>
                <strong>{d.count}건</strong>
              </div>
            ))}
          </figure>
        )}
        <RcaHostHistory result={result} embedded />
      </section>

      <section className="rca-narrative-section">
        <h4>6. 참고 자료</h4>
        <ul>
          {[
            ...new Map(
              [
                ...refs,
                { url: TRIAGE_URL, section: 'NVIDIA GPU Node Triage' },
                ...(v?.family === 'nvswitch'
                  ? [{ url: FM_URL, section: 'NVIDIA Fabric Manager User Guide' }]
                  : []),
              ].map((r) => [str(r.url), r]),
            ).values(),
          ]
            .filter((r) => /^https:\/\//.test(str(r.url)))
            .map((r) => (
              <li key={str(r.url)}>
                <a href={str(r.url)} target="_blank" rel="noreferrer">
                  {str(r.section) || str(r.url)}
                </a>
              </li>
            ))}
        </ul>
        {guidance.map((g, i) => (
          <dl key={i} className="rca-reference-guide">
            {str(obj(g.guidance).meaning) && (
              <div>
                <dt>오류 의미</dt>
                <dd>{str(obj(g.guidance).meaning)}</dd>
              </div>
            )}
            {rows(obj(g.guidance).references).map((r, j) => (
              <div key={j}>
                <dt>{str(r.title)}</dt>
                <dd>
                  <RcaPoints items={sentences(str(r.text))} />
                </dd>
              </div>
            ))}
          </dl>
        ))}
        <details>
          <summary>수집 원문·처리 상세</summary>
          {sources
            .filter((r) => r.detail_only === true)
            .map((r, i) => (
              <p key={i}>{str(r.text)}</p>
            ))}
          {narrative
            .filter((s) => !['cause', 'action', 'comparison'].includes(str(s.id)))
            .map((s, i) => (
              <section key={i}>
                <h5>{str(s.title)}</h5>
                <p style={{ whiteSpace: 'pre-wrap' }}>{str(s.text)}</p>
              </section>
            ))}
        </details>
      </section>
    </section>
  );
}
