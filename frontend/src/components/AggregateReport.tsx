import { adviceGroups, advicePresentation, adviceTime } from '../lib/namespaceAdvice';
import { useState } from 'react';
import { obj, rows, str, strings, type Row } from '../lib/live';
import { ReportPeriod } from './ReportMeta';
import { Notice, TextLink } from './ui';
import { reportRequestTime } from '../lib/reportPeriod';
import './aggregate-report.css';
import '../lib/advice-colors.css';
import { memoryPercent, NamespaceCharts, type NamespaceFocus } from './NamespaceCharts';
import { WorkloadCharts } from './WorkloadCharts';
import { WorkloadContext } from './WorkloadContext';
import { ReportVisualSummary } from './Console2Charts';

export const aggregateReasons: Record<string, string> = {
  unobserved_hour: '이 시간대 관측 없음',
  identity_labels_missing: 'GPU·Namespace·Pod 식별 정보 부족',
  identity_labels_conflict: 'GPU·노드 식별 정보 불일치',
  duplicate_or_changed_gpu_identity: 'GPU 연결 변경 또는 중복 관측',
  invalid_activity_aggregate: '활동률 집계 검증 실패',
  pod_identity_unverified: 'Pod 신원 확인 불가',
  incomplete_hour_or_sampling_interval: '시간대 관측 부족 또는 수집 주기 불일치',
  node_sharing_configuration_unverified: 'GPU 공유 설정 이력 미확인',
  shared_or_mig_attribution_unverified: '공유 GPU·MIG 귀속 미확인',
  report_query_failed: '집계 조회 실패',
  report_datasource_unavailable: '자료 조회 경로 미확인',
  namespace_observations_missing: 'Namespace 관측 자료 없음',
  incident_limit_exceeded: '사건 조회 상한 초과',
  query_unavailable: '집계 조회 불가',
  report_response_limit_exceeded: '조회 자료 크기 상한 초과',
  report_point_limit_exceeded: '조회 표본 수 상한 초과',
  report_query_limit_exceeded: '조회 횟수 상한 초과',
  invalid_prometheus_matrix: '집계 응답 형식 오류',
  partial_or_invalid_prometheus_response: '불완전한 집계 응답',
};
const pct = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)}%` : '산출 불가';
const difference = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value)
    ? `${value > 0 ? '+' : ''}${value.toFixed(2)}%p`
    : '비교 보류';
const keyOf = (row: Row) => [row.cluster_id, row.namespace, row.gpu_model].join('/');
const namespaceKey = (row: Row) => JSON.stringify([row.cluster_id, row.namespace]);
export function namespaceGroups(comparisons: Row[]) {
  const groups = new Map<
    string,
    { key: string; cluster: string; namespace: string; models: Row[] }
  >();
  for (const row of comparisons) {
    if (!str(row.namespace)) continue;
    const key = namespaceKey(row);
    const group = groups.get(key) || {
      key,
      cluster: str(row.cluster_id),
      namespace: str(row.namespace),
      models: [],
    };
    group.models.push(row);
    groups.set(key, group);
  }
  return [...groups.values()];
}
function comparisonReason(row: Row) {
  if (row.comparison_status === 'comparable') return '동일 모델·완료 기간 비교';
  if (row.comparison_status === 'previous_not_observed') return '이전 기간 관측 없음';
  if (row.comparison_status === 'current_not_observed') return '현재 기간 관측 없음';
  if (row.previous_valid_hours != null)
    return `현재 ${row.valid_hours}/${row.expected_hours}시간 · 이전 ${row.previous_valid_hours}/${row.previous_expected_hours}시간 확인`;
  return '현재 또는 이전 기간 자료 부족';
}
function observedCount(models: Row[]) {
  const observed = models.filter((r) => r.observed_gpu_count != null);
  if (!observed.length) return '미확인';
  if (
    observed.some(
      (r) =>
        !rows(r.hours)
          .filter((h) => h.activity_percent != null)
          .flatMap((h) => strings(h.gpu_ids)).length,
    )
  )
    return '모델별 확인';
  const count = new Set(
    observed.flatMap((r) =>
      rows(r.hours)
        .filter((h) => h.activity_percent != null)
        .flatMap((h) => strings(h.gpu_ids)),
    ),
  ).size;
  return `${count}개${observed.length < models.length ? ' · 일부 확인' : ''}`;
}

export function namespaceActivity(models: Row[]) {
  const values = models
    .map((r) => r.activity_percent)
    .filter((v): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 100);
  if (!values.length) return '산출 불가';
  const min = Math.min(...values),
    max = Math.max(...values);
  return min === max ? pct(min) : `${pct(min)}–${pct(max)}`;
}

function memoryRange(models: Row[], field: string, percent = false) {
  const values = models
    .map((r) => {
      const memory = obj(r.gpu_memory);
      if (memoryPercent(memory) == null) return null;
      return percent
        ? memoryPercent(memory, field)
        : field === 'total'
          ? Number(memory.used_gib_per_gpu) + Number(memory.free_gib_per_gpu)
          : memory[field];
    })
    .filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  if (!values.length) return '확인 불가';
  const min = Math.min(...values),
    max = Math.max(...values);
  return `${min.toFixed(percent ? 1 : 2)}${min === max ? '' : `–${max.toFixed(percent ? 1 : 2)}`}${percent ? '%' : ' GiB'}`;
}

export function incidentShortTitle(value: string) {
  const title = value.replace(/\s+/g, ' ').trim();
  if (!title) return '장애 설명 미저장 · 사건 상세 확인';
  if (/\bXID\s*79\b/i.test(title) && /fallen off.*bus/i.test(title))
    return 'XID 79 · GPU 연결 끊김 알림';
  if (/\bSXID\s*11001\b/i.test(title) && /ingress invalid command/i.test(title))
    return 'SXID 11001 · 스위치 수신 명령 오류 알림';
  const characters = Array.from(title);
  return characters.length > 60 ? `${characters.slice(0, 60).join('')}…` : title;
}

function InterpretationText({ text }: { text: string }) {
  // Keep each saved date/time together without rewriting the model's text.
  return text.split(/(\b\d{1,2}\/\d{1,2}[ \t]+\d{2}:\d{2}(?::\d{2})?)/g).map((part, i) =>
    i % 2 ? (
      <span className="aggregate-timestamp" key={i}>
        {part}
      </span>
    ) : (
      part
    ),
  );
}

function AdviceSummary({
  item,
  onEvidence,
  onFocus,
}: {
  item: Row;
  onEvidence?: (id: string) => void;
  onFocus?: (item: Row) => void;
}) {
  const parts = obj(item.summary_parts);
  const decision = str(parts.decision);
  const evidence = str(parts.evidence);
  // Only display exact stored slices; old or inconsistent records keep their full prose.
  const separated =
    !!decision &&
    !!evidence &&
    (`${decision} ${evidence}` === str(item.summary) ||
      `${decision}${evidence}` === str(item.summary));
  const target = obj(item.target);
  const { title, basis, trial, windows, models } = advicePresentation(item);
  return (
    <li
      data-advice-id={str(item.fact_id)}
      id={onFocus ? `c2-advice-${encodeURIComponent(str(item.fact_id))}` : undefined}
    >
      <div className="aggregate-advice-heading">
        <h5 className="advice-kind" data-kind={str(item.kind)}>
          {title}
        </h5>
        {trial && <span className="aggregate-advice-history">과거 관측</span>}
      </div>
      {str(item.summary) ? (
        <p className="aggregate-advice-decision">
          <InterpretationText text={separated ? decision : str(item.summary)} />
        </p>
      ) : (
        <>
          <p>
            <InterpretationText text={str(item.observation)} />
          </p>
          <p>
            <strong>운영 제안</strong> {str(item.meaning)}
          </p>
          <p>
            <strong>다음 확인</strong> {str(item.next_check)}
          </p>
        </>
      )}
      <dl className="aggregate-advice-target aggregate-advice-windows">
        {windows.map(({ label, period }) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              <span className="aggregate-advice-window-time">({adviceTime(period)})</span>
            </dd>
          </div>
        ))}
      </dl>
      {models.length > 0 && (
        <p className="aggregate-advice-model">GPU 모델 · {models.join(' · ')}</p>
      )}
      {trial && (
        <p className="aggregate-advice-scope">
          과거 관측입니다. 향후 시간대 변경은 반복성과 실행 조건을 확인한 뒤 판단하세요.
        </p>
      )}
      {onFocus && (
        <div className="c2-advice-facts">
          <p>
            <strong>관측 근거</strong>
            <InterpretationText
              text={separated ? evidence : str(item.observation) || '저장된 관측 문장이 없습니다.'}
            />
          </p>
          {str(item.conditions) && (
            <p>
              <strong>적용 조건</strong>
              {str(item.conditions)}
            </p>
          )}
          {str(target.cluster_id) && str(target.namespace) && (
            <button className="button" onClick={() => onFocus(item)}>
              이 대상·구간을 그래프에서 확인 →
            </button>
          )}
        </div>
      )}
      <details className="aggregate-advice-evidence">
        <summary>
          판단 근거와 적용 조건
          <span className="sr-only">
            {' '}
            · {str(target.cluster_id)} / {str(target.namespace)}
          </span>
        </summary>
        {basis && (
          <p className="aggregate-advice-basis">
            <strong>해석 기준</strong> {basis}
          </p>
        )}
        <p>
          <strong>관측 근거</strong>{' '}
          <InterpretationText text={separated ? evidence : str(item.observation)} />
        </p>
        {str(item.conditions) && (
          <p className="aggregate-static-note">
            <strong>적용 조건</strong> {str(item.conditions)}
          </p>
        )}
        {trial && (
          <p className="aggregate-static-note">
            이미 지난 구간입니다. 이후 같은 시간대에도 활동률이 낮은지와 사용 가능한 GPU를 확인한
            뒤, 시작 시간을 바꿀 수 있는 작업 일부만 시험할지 판단하세요.
          </p>
        )}
        {onEvidence ? (
          <div className="aggregate-evidence-links">
            {strings(item.evidence_refs).map((id, i) => (
              <button type="button" className="text-link" key={id} onClick={() => onEvidence(id)}>
                원본 근거 {i + 1}
              </button>
            ))}
          </div>
        ) : null}
      </details>
    </li>
  );
}

function IncidentInterpretation({
  topic,
  section,
  facts,
  onEvidence,
}: {
  topic: Row;
  section: Row;
  facts: Row[];
  onEvidence?: (id: string) => void;
}) {
  const check = str(section.check_target);
  // Match the saved selection exactly; do not select a new target in the reader.
  const selected = facts.find((fact) => {
    const target = obj(fact.target);
    return (
      target.node &&
      check.startsWith([target.cluster_id, target.node, target.alert_type].join(' / ') + ' · ')
    );
  });
  const target = obj(selected?.target);
  const clusters = [
    ...new Set(facts.map((fact) => str(obj(fact.target).cluster_id)).filter(Boolean)),
  ];
  const count = rows(topic.metrics).find(
    (metric) =>
      strings(selected?.value_refs).includes(str(metric.id)) &&
      str(metric.id).startsWith('incident_summary.node_alert_count.'),
  );
  return (
    <section
      className="aggregate-interpretation aggregate-interpretation-grouped"
      aria-label="incident_summary AI 운영 해석"
    >
      <div className="aggregate-advice-groups">
        <section className="aggregate-advice-cluster">
          <h3 className="aggregate-advice-card-title">AI 운영 해석</h3>
          {clusters.length > 0 && (
            <p className="aggregate-advice-cluster-target">
              <span>대상 클러스터 :</span> <code>{clusters.join(' · ')}</code>
            </p>
          )}
          {count && (
            <p className="aggregate-advice-time-note">
              분석 기간 · {adviceTime(obj(count.period))}
            </p>
          )}
          <div className="aggregate-advice-namespace">
            <h4 className="aggregate-advice-identity">
              <span>확인 대상</span>
              <span aria-hidden="true">:</span>
              {selected ? (
                <code>
                  {[
                    ...(clusters.length > 1 ? [str(target.cluster_id)] : []),
                    str(target.node),
                    str(target.alert_type),
                  ].join(' / ')}
                </code>
              ) : (
                <span>
                  {check
                    ? '저장된 확인 대상은 아래 근거에서 확인하세요.'
                    : '노드가 확인된 사건이 없어 선정하지 않았습니다.'}
                </span>
              )}
            </h4>
            <ul className="aggregate-namespace-summary">
              <li>
                <div className="aggregate-advice-heading">
                  <h5>알림 해석과 확인 제안</h5>
                </div>
                <p className="aggregate-advice-decision">
                  <InterpretationText text={str(section.meaning)} />{' '}
                  <InterpretationText text={str(section.next_check)} />
                </p>
                <details className="aggregate-advice-evidence">
                  <summary>판단 근거와 확인 범위</summary>
                  <p>
                    <strong>관측 근거 · 자동 집계</strong>{' '}
                    <InterpretationText text={str(section.observation)} />
                  </p>
                  <p>
                    <strong>확인 대상 · 자동 선정</strong>{' '}
                    <InterpretationText
                      text={check || '노드가 확인된 사건이 없어 선정하지 않았습니다.'}
                    />
                  </p>
                  <p className="aggregate-advice-basis">
                    <strong>해석 기준</strong> 같은 종류의 여러 노드 발생, 같은 노드의 다른 종류,
                    이전 비교기간 기록 등을 사용한 작성 당시의 선정 결과입니다. 과거 보고서의
                    선정에는 당시 알림 상태가 사용됐을 수 있으며 현재 장애·복구 상태를 뜻하지
                    않습니다. 선정된 내역으로 전체 분포나 원인을 단정하지 않습니다.
                  </p>
                  <p>
                    <strong>해석 범위</strong> {str(section.interpretation_limit)}
                  </p>
                  {onEvidence && (
                    <div className="aggregate-evidence-links">
                      {strings(section.evidence_refs).map((id, i) => (
                        <button
                          type="button"
                          className="text-link"
                          key={id}
                          onClick={() => onEvidence(id)}
                        >
                          근거 {i + 1} 확인
                        </button>
                      ))}
                    </div>
                  )}
                </details>
              </li>
            </ul>
          </div>
        </section>
      </div>
      <p className="aggregate-summary-source aggregate-static-note">
        본문은 AI 작성 · 관측 근거와 확인 대상은 자동 집계·선정
      </p>
      <p className="aggregate-interpretation-limit">
        저장된 사건 자료를 기준으로 합니다. 확인 제안은 실제 조치나 장애 원인 판정이 아닙니다.
      </p>
    </section>
  );
}

function TopicInterpretation({
  topic,
  narrative,
  onEvidence,
  onFocus,
}: {
  topic: Row;
  narrative: Row[];
  onEvidence?: (id: string) => void;
  onFocus?: (item: Row) => void;
}) {
  const section = narrative.find((item) => item.topic_id === topic.topic_id);
  if (section?.interpretation_source === 'deterministic_fallback') {
    return (
      <section className="aggregate-summary" aria-label={`${str(topic.topic_id)} 계산 결과 요약`}>
        <h3>계산 결과 요약</h3>
        <p className="aggregate-static-note">
          이 주제의 AI 해석을 작성하지 못해 저장된 계산 결과를 표시합니다.
        </p>
        <p style={{ whiteSpace: 'pre-line' }}>{str(section.text)}</p>
      </section>
    );
  }
  if (!section || !['observation', 'meaning', 'next_check'].every((key) => str(section[key])))
    return null;
  const facts = rows(topic.findings).filter((fact) =>
    strings(section.source_fact_ids).includes(str(fact.id)),
  );
  if (topic.topic_id === 'incident_summary' && 'check_target' in section) {
    return (
      <IncidentInterpretation
        topic={topic}
        section={section}
        facts={facts}
        onEvidence={onEvidence}
      />
    );
  }
  const advice = rows(section.advice);
  const hasSummary = advice.length > 0 && advice.every((item) => str(item.summary));
  const selection = obj(section.selection);
  const criteria = obj(selection.criteria);
  return (
    <section
      className={`aggregate-interpretation${advice.length ? ' aggregate-interpretation-grouped' : ''}`}
      aria-label={`${str(topic.topic_id)} AI 운영 해석`}
    >
      {advice.length === 0 && <h3>AI 운영 해석</h3>}
      {advice.length > 0 && (
        <div className="aggregate-advice-groups">
          {adviceGroups(advice).map((cluster) => (
            <section
              className="aggregate-advice-cluster"
              key={cluster.key}
              aria-label={`${cluster.cluster || '미확인'} 클러스터 AI 운영 해석`}
            >
              <h3 className="aggregate-advice-card-title">AI 운영 해석</h3>
              <p className="aggregate-advice-cluster-target">
                <span>대상 클러스터 :</span> <code>{cluster.cluster || '미확인'}</code>
              </p>
              <p className="aggregate-advice-time-note">
                구간 시각은 KST 기준이며 끝 시각은 포함하지 않습니다.
              </p>
              {cluster.namespaces.map((ns) => (
                <section className="aggregate-advice-namespace" key={ns.key}>
                  <h4 className="aggregate-advice-identity">
                    <span>네임스페이스</span>
                    <span aria-hidden="true">:</span>
                    <code>{ns.namespace || '미확인'}</code>
                  </h4>
                  <ul className="aggregate-namespace-summary">
                    {ns.items.map((item, i) => (
                      <AdviceSummary
                        key={str(item.fact_id, String(i))}
                        item={item}
                        onEvidence={onEvidence}
                        onFocus={onFocus}
                      />
                    ))}
                  </ul>
                </section>
              ))}
            </section>
          ))}
        </div>
      )}
      <p className="aggregate-summary-source aggregate-static-note">
        <strong>작성 방식</strong>
        {hasSummary
          ? 'AI가 작성한 요약입니다. 관측한 구간의 조건부 제안이며 실제 할당·대기 원인은 별도 확인이 필요합니다.'
          : section.observation_source === 'calculated'
            ? '관측 수치·대상·시간은 코드가 확인한 사실이며, 의미와 확인할 점은 AI가 작성했습니다.'
            : '저장된 계산 결과를 바탕으로 AI가 작성했습니다.'}{' '}
        {hasSummary ? null : '확인할 점은 제안이며, 실제 조치나 장애 원인 판정이 아닙니다.'}
      </p>
      {advice.length > 0 ? null : (
        <dl>
          {[
            [
              'observation',
              section.observation_source === 'calculated'
                ? '계산으로 확인한 관측'
                : '눈에 띄는 변화',
            ],
            ['meaning', '의미와 한계'],
            ['next_check', '확인할 점'],
          ].map(([key, label]) => (
            <div key={key}>
              <dt>{label}</dt>
              <dd>
                <InterpretationText text={str(section[key])} />
              </dd>
            </div>
          ))}
        </dl>
      )}
      {hasSummary ? null : (
        <p className="aggregate-interpretation-limit">{str(section.interpretation_limit)}</p>
      )}
      <details>
        <summary>해석 근거와 계산 결과</summary>
        {hasSummary ? (
          <p className="aggregate-static-note">
            {str(section.interpretation_limit)} 작업 시간대 제안은 예약·대기와 사용 가능한 GPU를
            확인한 뒤 검토하세요. 실제 조치나 장애 원인 판정이 아닙니다.
          </p>
        ) : null}
        {hasSummary && criteria.version ? (
          <p className="aggregate-static-note">
            선별 기준: 활동률 {String(criteria.high_activity_percent)}% 이상과 대기가 함께 관측된
            연속 {String(criteria.minimum_pattern_hours)}시간, 활동률{' '}
            {String(criteria.low_activity_percent)}% 미만인 연속 구간, 같은 구간의 메모리 점유, 대기
            변화와 완료 Job 표본을 확인합니다. 운영정책에 따른 할당 기준은 아닙니다. 근거 후보{' '}
            {String(selection.eligible_count)}개 중 {String(selection.offered_count)}개를 AI에
            전달하고 {advice.length}개를 요약했습니다. 클러스터와 분석 종류를 먼저 보존한 뒤 자료
            충족 여부와 관측 규모로 선별합니다.
          </p>
        ) : null}
        {facts.map((fact) => (
          <p key={str(fact.id)}>{str(fact.text)}</p>
        ))}
        {rows(topic.metrics)
          .filter(
            (metric) =>
              str(metric.id).startsWith('namespace_usage.hourly_activity.') &&
              strings(section.value_refs).includes(str(metric.id)),
          )
          .map((metric) => (
            <p key={str(metric.id)}>
              {str(obj(metric.target).cluster_id)} / {str(obj(metric.target).namespace)} ·{' '}
              {str(obj(metric.target).model)}: {reportRequestTime(str(obj(metric.period).start))} ~{' '}
              {reportRequestTime(str(obj(metric.period).end))} · {pct(metric.value)}
            </p>
          ))}
        <div className="aggregate-evidence-links">
          {onEvidence &&
            strings(section.evidence_refs).map((id, i) => (
              <button type="button" className="text-link" key={id} onClick={() => onEvidence(id)}>
                근거 {i + 1} 확인
              </button>
            ))}
        </div>
      </details>
    </section>
  );
}

export function AggregateReport({
  value,
  onEvidence,
  reader = false,
}: {
  value: Row;
  onEvidence?: (id: string) => void;
  reader?: boolean;
}) {
  const topics = rows(value.topics);
  const usage = topics.find((t) => t.topic_id === 'namespace_usage');
  const incident = topics.find((t) => t.topic_id === 'incident_summary');
  const comparisons = rows(usage?.rows);
  const groups = namespaceGroups(comparisons);
  const hasMemory = comparisons.some((r) => r.gpu_memory != null);
  const selectedNodes = (models: Row[]) =>
    [...new Set(models.flatMap((r) => strings(r.nodes)))].sort();
  const unattributed = comparisons.filter((r) => !str(r.namespace));
  const observationDiagnostics = obj(obj(usage?.quality).observation_diagnostics);
  const diagnosticMessages = strings(observationDiagnostics.messages);
  const [selection, setSelection] = useState('');
  const [modelSelection, setModelSelection] = useState('');
  const [incidentLimit, setIncidentLimit] = useState(50);
  const selected = groups.find((g) => g.key === selection) || groups[0];
  const models = selected?.models || [];
  const active =
    models.find((r) => keyOf(r) === modelSelection) ||
    models.find((r) => rows(r.hours).length) ||
    models[0];
  const hours = rows(active?.hours);
  const [hiddenNamespaces, setHiddenNamespaces] = useState<Set<string>>(() => new Set());
  const [graphFocus, setGraphFocus] = useState<NamespaceFocus | null>(null);
  const focusAdvice = (item: Row) => {
    const target = obj(item.target);
    const key = JSON.stringify([str(target.cluster_id), str(target.namespace)]);
    setSelection(key);
    setHiddenNamespaces((previous) => {
      const next = new Set(previous);
      for (const metric of ['activity', 'memory', 'both'])
        next.delete(JSON.stringify([metric, key]));
      return next;
    });
    setGraphFocus({
      cluster: str(target.cluster_id),
      namespace: str(target.namespace),
      windows: advicePresentation(item).windows.map((w) => w.period),
      origin: `c2-advice-${encodeURIComponent(str(item.fact_id))}`,
    });
    requestAnimationFrame(() => {
      const chart = document.getElementById('c2-namespace-charts');
      chart?.focus({ preventScroll: true });
      chart?.scrollIntoView({ block: 'start' });
    });
  };
  const toggleNamespace = (key: string) =>
    setHiddenNamespaces((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const summary = obj(incident?.summary);
  const summaryMethod = str(obj(obj(value.quality).report).method);
  const partialInterpretation =
    value.narrative_status === 'failed' && summaryMethod === 'partial_interpretation';
  const aiInterpreted =
    (value.narrative_status === 'complete' && summaryMethod === 'llm_interpreted') ||
    partialInterpretation;
  const incidentNumber = usage ? 2 : 1;
  const aiSelected = value.narrative_status === 'complete' && summaryMethod === 'llm_prioritized';
  const calculatedSummary = summaryMethod === 'deterministic_fallback';
  const summaryTitle = aiSelected
    ? 'AI가 고른 주요 변화'
    : calculatedSummary
      ? '계산 결과 요약'
      : '저장된 주요 변화';
  const namespaceCharts = (
    <NamespaceCharts
      headingNumber={reader ? '1.1' : '1.2'}
      reader={reader}
      focus={graphFocus}
      onClearFocus={() => setGraphFocus(null)}
      groups={groups}
      hidden={hiddenNamespaces}
      onToggle={toggleNamespace}
      onSetCluster={(keys, visible) =>
        setHiddenNamespaces((previous) => {
          const next = new Set(previous);
          keys.forEach((key) => {
            if (visible) next.delete(key);
            else next.add(key);
          });
          return next;
        })
      }
    />
  );
  return (
    <section
      id="final-report"
      className="aggregate-report rca-narrative"
      aria-label="운영 분석 보고서"
    >
      {/* Same card frame as the RCA report: a fixed heading above the stored sections. */}
      {!reader && (
        <header className="rca-narrative-header">
          <h3>운영 분석 보고서</h3>
          <ReportPeriod value={value.time_range} />
          <p>직전 같은 길이의 기간과 비교합니다. 모든 시각은 한국 시간 기준입니다.</p>
        </header>
      )}
      {!reader && (
        <nav className="rca-narrative-nav" aria-label="보고서 목차">
          {usage && <a href="#namespace-summary-title">1. Namespace별 GPU 활동 현황</a>}
          {incident && (
            <a href="#incident-summary-title">{incidentNumber}. 기간 내 장애 알림 현황</a>
          )}
          <a href="#report-evidence">집계 기준과 근거</a>
        </nav>
      )}
      {reader && <ReportVisualSummary value={value} />}
      {partialInterpretation && (
        <Notice>
          일부 주제의 AI 해석을 작성하지 못했습니다. 검증을 통과한 주제의 AI 해석은 유지하고,
          나머지는 계산 결과 요약으로 표시합니다.
        </Notice>
      )}
      {!aiInterpreted && rows(value.narrative).length > 0 && (
        <section
          className={`aggregate-summary${aiSelected ? ' aggregate-summary-ai' : ''}`}
          aria-labelledby="report-summary-title"
        >
          <h3 id="report-summary-title">{summaryTitle}</h3>
          <p className="aggregate-summary-source">
            {aiSelected
              ? '계산된 관측 결과 중 AI가 선택한 항목입니다. 문장과 수치는 계산 결과이며, AI가 원인이나 운영 조치를 판단한 내용은 아닙니다.'
              : calculatedSummary
                ? 'AI 응답을 사용하지 않은 기본 요약입니다. 계산된 관측 결과를 표시합니다.'
                : '요약의 AI 선택 여부가 기록되지 않았습니다. 저장된 문장을 그대로 표시합니다.'}
          </p>
          <ul className="rca-points aggregate-summary-findings">
            {rows(value.narrative)
              .slice(0, 3)
              .map((finding) => (
                <li key={str(finding.id)}>{str(finding.summary_text, str(finding.text))}</li>
              ))}
          </ul>
        </section>
      )}
      <p className="aggregate-static-note">
        <strong>해석 기준</strong>
        활동률은 연결 GPU의 관측 표본 평균입니다. 부서의 독점 사용량·할당 효율이나 GPU 회수 가능량을
        뜻하지 않습니다.
      </p>
      {usage && (
        <section className="aggregate-major-topic" aria-labelledby="namespace-summary-title">
          <h2 id="namespace-summary-title">1. Namespace별 GPU 활동 현황</h2>
          {reader && groups.length > 0 && namespaceCharts}
          {diagnosticMessages.length > 0 && (
            <section aria-label="부분 산출 원인">
              <h3>활동률 산출·기간 비교의 제한</h3>
              <p>
                일부 관측을 활동률 계산이나 기간 비교에 사용할 수 없었습니다. 검증 미실행은 신원
                충돌이 확인됐다는 뜻이 아닙니다.
              </p>
              <ul>
                {strings(observationDiagnostics.summary).map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
              <details>
                <summary>대상·기간별 제외 사유 보기</summary>
                <ul>
                  {diagnosticMessages.map((message) => (
                    <li key={message}>{message}</li>
                  ))}
                </ul>
              </details>
            </section>
          )}
          {aiInterpreted && (
            <TopicInterpretation
              topic={usage}
              narrative={rows(value.narrative)}
              onEvidence={onEvidence}
              onFocus={reader ? focusAdvice : undefined}
            />
          )}
          <h3 className="aggregate-subheading">{reader ? '1.2' : '1.1'}. Namespace별 비교</h3>
          <p>
            표는 전체 Namespace의 관측 구성을 보여줍니다. 그래프에서만 비교 대상을 선택할 수
            있습니다. 관측 GPU 수는 기간 내 확인된 고유 GPU 개수이며 서버 수나 동시 할당량이
            아닙니다.
          </p>
          {!groups.length ? (
            <Notice>
              선택한 기간에는 Namespace에 연결해 비교할 수 있는 자료가 없습니다. 새 작업을 오늘
              시작했다면 어제 보고서에는 포함되지 않습니다.
            </Notice>
          ) : (
            <>
              <div className="aggregate-table-scroll">
                <table
                  className={`aggregate-namespace-table${hasMemory ? ' aggregate-namespace-memory' : ''}`}
                >
                  <caption className="sr-only">클러스터·Namespace별 관측 구성</caption>
                  <thead>
                    <tr>
                      <th>클러스터 / Namespace</th>
                      <th>관측 노드</th>
                      <th>관측 GPU 수</th>
                      <th>평균 GPU 활동률</th>
                      {hasMemory && <th>GPU 메모리 사용 비율</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {groups.map((group) => {
                      return (
                        <tr key={group.key}>
                          <th scope="row">
                            <span>{group.cluster}</span>
                            {group.namespace}
                          </th>
                          <td>{selectedNodes(group.models).join(', ') || '미확인'}</td>
                          <td className="aggregate-number">{observedCount(group.models)}</td>
                          <td className="aggregate-number">
                            {namespaceActivity(group.models)}
                            {group.models.length > 1 && <small>모델별 평균 범위</small>}
                            {group.models.some((r) => r.quality_status !== 'ready') && (
                              <small>일부 자료 기준</small>
                            )}
                          </td>
                          {hasMemory && (
                            <td className="aggregate-number">
                              <span className="aggregate-memory-percent">
                                {memoryRange(group.models, 'used_gib_per_gpu', true)}
                              </span>
                              <small>
                                사용 {memoryRange(group.models, 'used_gib_per_gpu')} / 전체{' '}
                                {memoryRange(group.models, 'total')}
                              </small>
                              {group.models.some((r) =>
                                rows(obj(r.gpu_memory).hours).some(
                                  (h) => h.used_gib_per_gpu == null,
                                ),
                              ) && <small>일부 자료 기준</small>}
                            </td>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="aggregate-table-note aggregate-static-note">
                활동률은 확인된 자료의 평균입니다. 여러 GPU 모델을 사용하면 모델별 평균의 최소–최대
                범위를 표시합니다. 자료가 일부뿐이면 전체 기간의 사용 패턴으로 단정하지 않습니다.
              </p>
              {hasMemory && (
                <p className="aggregate-table-note aggregate-static-note">
                  메모리 사용 비율은 사용량 ÷ (사용량 + 여유량) × 100입니다. 보조 수치는 GPU당 평균
                  사용량 / 전체 용량(GiB)입니다. 전체 용량은 관측된 사용량과 여유량의 합입니다. 연결
                  GPU의 관측값이며 Namespace의 전용 사용량이나 할당량이 아닙니다. 활동률과 메모리는
                  각각 확인된 구간의 평균이므로 반영 구간이 다를 수 있습니다. 시간대별 비교는{' '}
                  {reader ? '위' : '아래'}
                  그래프에서 확인하세요. 여러 모델은 모델별 평균 범위를 표시합니다.
                </p>
              )}
              {!reader && namespaceCharts}
              <h3 className="aggregate-subheading">1.3. 세부 수치와 사용 패턴</h3>
              <details className="aggregate-model-detail">
                <summary>세부 수치와 자료 상태</summary>
                <label className="aggregate-detail-selector">
                  확인할 Namespace
                  <select
                    value={selected?.key || ''}
                    onChange={(event) => {
                      setSelection(event.target.value);
                      setModelSelection('');
                    }}
                  >
                    {groups.map((group) => (
                      <option key={group.key} value={group.key}>
                        {group.cluster} / {group.namespace}
                      </option>
                    ))}
                  </select>
                </label>
                <p>
                  현재 자료가 충분해도 이전 기간에 공백이 있으면 증감 비교는 보류합니다. 다른 GPU
                  모델의 활동률을 하나의 평균으로 합치지 않습니다.
                </p>
                <div className="aggregate-table-scroll">
                  <table className="aggregate-model-table">
                    <thead>
                      <tr>
                        <th>GPU 모델 / 상세 선택</th>
                        <th>관측 GPU 수</th>
                        <th>현재 활동률</th>
                        <th>이전 활동률</th>
                        <th>변화</th>
                        <th>유효 시간대</th>
                      </tr>
                    </thead>
                    <tbody>
                      {models.map((row) => (
                        <tr key={keyOf(row)} className={row === active ? 'selected' : ''}>
                          <th scope="row">
                            <button
                              type="button"
                              aria-pressed={row === active}
                              onClick={() => setModelSelection(keyOf(row))}
                            >
                              {str(row.gpu_model) || '모델 미확인'}
                            </button>
                          </th>
                          <td className="aggregate-number">
                            {row.observed_gpu_count == null
                              ? '미확인'
                              : `${row.observed_gpu_count}개`}
                          </td>
                          <td className="aggregate-number">
                            {pct(row.activity_percent)}
                            {row.quality_status !== 'ready' && <small>확인된 시간대만</small>}
                          </td>
                          <td className="aggregate-number">{pct(row.previous_activity_percent)}</td>
                          <td>
                            {difference(row.change_percentage_points)}
                            <small>{comparisonReason(row)}</small>
                          </td>
                          <td className="aggregate-number">
                            {String(row.valid_hours)} / {String(row.expected_hours)}시간
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="aggregate-hour-detail">
                  <h4>선택한 모델의 시간대별 수치</h4>
                  <p>
                    {str(active?.cluster_id)} / {str(active?.namespace)} / {str(active?.gpu_model)}
                  </p>
                  <p>
                    {active?.low_activity_hours == null
                      ? '자료가 부족해 낮은 활동 시간대 수는 판단을 보류합니다.'
                      : `평균 활동률 5% 미만: ${active.low_activity_hours}개 시간대. 이 기준은 보고서 분류 기준이며 운영정책이 아닙니다.`}
                  </p>
                  <details>
                    <summary>시간대별 수치와 자료 부족 사유</summary>
                    <div className="aggregate-table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>시간대 시작</th>
                            <th>평균 활동률</th>
                            {active?.gpu_memory != null && <th>메모리 사용 비율</th>}
                            <th>자료 상태</th>
                          </tr>
                        </thead>
                        <tbody>
                          {hours.map((h) => (
                            <tr key={str(h.end)}>
                              <td>{reportRequestTime(str(h.start))}</td>
                              <td>{pct(h.activity_percent)}</td>
                              {active?.gpu_memory != null && (
                                <td>
                                  {(() => {
                                    const memory = rows(obj(active?.gpu_memory).hours).find(
                                      (m) => m.end === h.end,
                                    );
                                    const percent = memory ? memoryPercent(memory) : null;
                                    return percent == null || !memory ? (
                                      '확인 불가'
                                    ) : (
                                      <>
                                        <span className="aggregate-memory-percent">
                                          {percent.toFixed(1)}%
                                        </span>
                                        <small>
                                          사용 {Number(memory.used_gib_per_gpu).toFixed(2)} GiB ·
                                          여유 {Number(memory.free_gib_per_gpu).toFixed(2)} GiB
                                        </small>
                                      </>
                                    );
                                  })()}
                                </td>
                              )}
                              <td>
                                {strings(h.reasons)
                                  .map((r) => aggregateReasons[r] || r)
                                  .join(' · ') || '관측 조건 확인'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                </div>
                {active && (
                  <div className="aggregate-patterns">
                    <h4>사용 패턴 요약</h4>
                    {rows(usage.findings)
                      .filter(
                        (f) =>
                          str(obj(f.target).cluster_id) === str(active.cluster_id) &&
                          str(obj(f.target).namespace) === str(active.namespace) &&
                          str(obj(f.target).model) === str(active.gpu_model),
                      )
                      .map((f) => (
                        <p key={str(f.id)}>{str(f.text)}</p>
                      ))}
                  </div>
                )}
              </details>
            </>
          )}
          <h3 id={reader ? 'c2-workloads' : undefined} className="aggregate-subheading">
            1.4. GPU 작업 대기·완료 (보조 관측)
          </h3>
          <WorkloadContext value={obj(usage.workload_context)} onEvidence={onEvidence} />
          {str(usage.workload_unavailable_reason) && (
            <Notice>작업 관측의 조회 범위를 초과해 대기·완료 집계를 표시하지 않습니다.</Notice>
          )}
          {rows(usage.workloads).length > 0 && (
            <section aria-label="GPU 작업 보조 관측">
              <h4>GPU 작업 대기·완료 관측</h4>
              <p className="aggregate-static-note">
                GPU를 요청한 일반 컨테이너가 있는 Pod 기준입니다. 대기는 GPU 부족을 뜻하지 않습니다.
                완료·경과시간은 성공 완료가 확인된 Job 표본이며, 전체 작업 수나 GPU 연산 시간이
                아닙니다. Job 경과시간에는 대기·준비가 포함됩니다. 최대값은 확인된 시점만 반영하며
                수집 공백은 포함하지 않습니다. 미수집은 0이 아닙니다. 각 최대값의 발생 시각은 서로
                다를 수 있습니다.
              </p>
              <div className="aggregate-table-scroll">
                <table>
                  <caption className="sr-only">Namespace별 GPU 작업 보조 관측</caption>
                  <thead>
                    <tr>
                      <th>클러스터 / Namespace</th>
                      <th>관측 최대 대기 Pod</th>
                      <th>관측 최대 미배치 Pod</th>
                      <th>관측 최대 실행 Pod</th>
                      <th>확인된 완료 Job</th>
                      <th>평균 Job 경과시간</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows(usage.workloads).map((w) => (
                      <tr key={`${w.cluster_id}/${w.namespace}`}>
                        <th>
                          {str(w.cluster_id)}
                          <br />
                          {str(w.namespace)}
                        </th>
                        {[
                          w.pending_peak,
                          w.unscheduled_peak,
                          w.running_peak,
                          w.completed_observed,
                        ].map((v, i) => (
                          <td key={i}>{typeof v === 'number' ? v : '자료 없음'}</td>
                        ))}
                        <td>
                          {typeof w.mean_elapsed_seconds === 'number'
                            ? `${(w.mean_elapsed_seconds / 60).toFixed(1)}분`
                            : '자료 없음'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <WorkloadCharts workloads={rows(usage.workloads)} />
            </section>
          )}

          {unattributed.length > 0 && (
            <details className="aggregate-unattributed">
              <summary>Namespace에 연결하지 못한 관측 · {unattributed.length}개 모델 묶음</summary>
              <p>
                {obj(usage.quality).namespace_status_basis ===
                'attributed_rows_with_current_cluster_coverage_v1'
                  ? '이 자료는 Namespace 활동 판정에 포함하지 않습니다. 미할당 여부와 전체 GPU 귀속의 완전성은 확인하지 않았습니다.'
                  : '이 자료는 Namespace별 사용량 비교에서 제외했습니다. 미사용 GPU라고 판단한 것은 아닙니다.'}
              </p>
              <ul>
                {unattributed.map((row) => (
                  <li key={keyOf(row)}>
                    {str(row.cluster_id)} · {str(row.gpu_model)}:{' '}
                    {Array.from(new Set(rows(row.hours).flatMap((h) => strings(h.reasons))))
                      .map((r) => aggregateReasons[r] || r)
                      .join(' · ') || 'Namespace 식별 정보 부족'}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      )}
      {incident && (
        <section className="aggregate-major-topic" aria-labelledby="incident-summary-title">
          <h2 id="incident-summary-title">{incidentNumber}. 기간 내 장애 알림 현황</h2>
          {aiInterpreted && (
            <TopicInterpretation
              topic={incident}
              narrative={rows(value.narrative)}
              onEvidence={onEvidence}
            />
          )}
          <h3 className="aggregate-subheading">{incidentNumber}.1. 장애 종류별 발생 현황</h3>
          {rows(incident.findings)
            .filter((f) => !str(f.id).startsWith('incident-node-'))
            .map((f) => (
              <p key={str(f.id)}>{str(f.text)}</p>
            ))}
          {rows(summary.categories).length > 0 && (
            <div className="aggregate-table-scroll">
              <table className="aggregate-incident-types">
                <caption className="sr-only">
                  장애 종류별 발생 현황 · 동일 원인을 의미하지 않습니다
                </caption>
                <thead>
                  <tr>
                    <th>클러스터 / 장애 종류</th>
                    <th>발생 노드</th>
                    <th>이번 기간</th>
                    <th>이전 기간</th>
                  </tr>
                </thead>
                <tbody>
                  {rows(summary.categories).map((category) => (
                    <tr key={`${category.cluster_id}/${category.name}`}>
                      <th scope="row">
                        <span>{str(category.cluster_id)}</span>
                        {str(category.name)}
                      </th>
                      <td>
                        {category.count === 0
                          ? '이번 기간 발생 없음'
                          : strings(category.nodes).join(', ') || '노드 미확인'}
                      </td>
                      <td className="aggregate-number">
                        {String(category.count)}건
                        {Number(category.test_count) > 0 && (
                          <small>시험 표시 {String(category.test_count)}건 포함</small>
                        )}
                      </td>
                      <td className="aggregate-number">{String(category.previous_count)}건</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {Number(summary.unclassified_count) > 0 && (
            <p className="aggregate-data-note">
              장비·증상 식별이 부족한 {String(summary.unclassified_count)}건은 같은 GPU의 반복
              장애인지 확인할 수 없습니다. 미확인 사건은 반복 그룹 수에 포함되지 않습니다.
            </p>
          )}
          {rows(summary.incidents).some((row) => !str(row.symptom)) && (
            <Notice>
              이 보고서에 장애 설명이 저장되지 않은 사건이 있습니다. 사건 상세에서 원문을
              확인하세요. 이 화면에서는 누락된 내용을 추가로 조회하거나 추정하지 않습니다.
            </Notice>
          )}

          <h3 className="aggregate-subheading">{incidentNumber}.2. 사건별 알림 내용</h3>
          {summary.count === 0 ? (
            <Notice>
              선택한 범위·기간에 저장된 사건이 없습니다. 장비 전체의 무장애를 뜻하지 않습니다.
            </Notice>
          ) : (
            rows(summary.incidents).length > 0 && (
              <div>
                <p className="aggregate-data-note aggregate-static-note">
                  <strong>자료 기준 시각</strong>
                  보고서 작성 중 조회한 저장 자료입니다. 현재 장비 상태를 나타내지 않습니다.
                  <br />
                  기준 시각:{' '}
                  {str(summary.status_as_of)
                    ? `${reportRequestTime(str(summary.status_as_of))} KST`
                    : '미저장'}
                </p>
                <div className="aggregate-table-scroll">
                  <table className="aggregate-incident-table">
                    <caption className="sr-only">사건별 알림 내용</caption>
                    <thead>
                      <tr>
                        <th>발생 시각</th>
                        <th>클러스터</th>
                        <th>노드</th>
                        <th>알림 내용</th>

                        <th>상세 보기</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows(summary.incidents)
                        .slice(0, incidentLimit)
                        .map((row) => (
                          <tr key={str(row.id)}>
                            <td className="aggregate-date">
                              <time dateTime={str(row.occurred_at)}>
                                {reportRequestTime(str(row.occurred_at))
                                  .split(/ (?=\d{2}:\d{2}:\d{2}$)/)
                                  .map((part, index) => (
                                    <span key={index}>{part}</span>
                                  ))}
                              </time>
                            </td>
                            <td>{str(row.cluster_id) || '미확인'}</td>
                            <td>{str(obj(row.target).node) || '미확인'}</td>
                            <td>
                              <span className="aggregate-alert-title">
                                {incidentShortTitle(str(row.symptom))}
                              </span>
                              {obj(row.target).test_alarm === true && (
                                <small>시험 알림으로 표시됨</small>
                              )}
                            </td>

                            <td>
                              <TextLink to={`/incidents/${encodeURIComponent(str(row.id))}`}>
                                {row.result_id ? 'RCA 보기' : '사건 보기'}
                              </TextLink>
                              {!row.result_id && <small>RCA 미발행</small>}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                {rows(summary.incidents).length > incidentLimit && (
                  <button
                    type="button"
                    className="button"
                    onClick={() => setIncidentLimit((n) => n + 50)}
                  >
                    사건 50건 더 보기 · 전체 {String(summary.count)}건
                  </button>
                )}
              </div>
            )
          )}
          {rows(summary.groups).length > 0 && (
            <details>
              <summary>같은 GPU·동일 증상의 반복 비교</summary>
              <table>
                <thead>
                  <tr>
                    <th>클러스터 / 장비 / 증상</th>
                    <th>이번 기간</th>
                    <th>이전 기간</th>
                  </tr>
                </thead>
                <tbody>
                  {rows(summary.groups).map((g, i) => (
                    <tr key={i}>
                      <td>
                        {str(g.cluster_id)} · {str(g.gpu_uuid)} · {str(g.symptom)}
                      </td>
                      <td>{String(g.count)}건</td>
                      <td>{String(g.previous_count)}건</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </section>
      )}
      <details className="aggregate-evidence" id="report-evidence">
        <summary>집계 기준과 근거</summary>
        <p>
          일평균끼리 평균내지 않고 활동률 합계와 표본 수를 합산합니다. 이전 보고서의 시간가중 평균과
          계산 방식이 다릅니다.
        </p>
        {strings(value.limitations)
          .filter((text) => !diagnosticMessages.includes(text))
          .map((text) => (
            <p key={text}>{text}</p>
          ))}
        <div className="aggregate-evidence-buttons">
          {onEvidence &&
            strings(value.evidence_refs).map((id, i) => (
              <button key={id} className="text-link" onClick={() => onEvidence(id)}>
                집계 근거 {i + 1}
              </button>
            ))}
        </div>
      </details>
    </section>
  );
}
