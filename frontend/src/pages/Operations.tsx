import { ArrowRight, ClipboardList, FileChartColumn, Radar, Telescope } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { useApp } from '../lib/store';
import {
  obj,
  queryPath,
  str,
  strings,
  topicId,
  topics,
  useList,
  useResource,
  type Row,
} from '../lib/live';
import { formatDate, labels } from '../lib/domain';
import { reportTitle } from '../lib/workflow';
import { AlarmIdentity, JobRows, More, QueryState } from '../components/live';
import { Badge, Field } from '../components/ui';
import { IncidentStates } from '../components/RcaDebug';

function SectionLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link className="ops-link" to={to}>
      {children}
      <ArrowRight size={16} />
    </Link>
  );
}
export function OperationCaseList({ items }: { items: Row[] }) {
  return (
    <div className="ops-case-list">
      {items.map((i) => (
        <Link className="ops-case" key={str(i.id)} to={`/incidents/${str(i.id)}`}>
          <span className={`ops-signal ${i.alarm_status === 'firing' ? 'attention' : ''}`} />
          <div>
            <AlarmIdentity record={i} />
            <IncidentStates incident={i} />
          </div>
          <div className="ops-case-time">
            <time>{formatDate(str(i.occurred_at, str(i.created_at)))}</time>
            <span>
              사건 확인 <ArrowRight size={15} />
            </span>
          </div>
        </Link>
      ))}
    </div>
  );
}
export function OperationsHome() {
  const app = useApp();
  const dashboard = useResource(
    app.canOperate
      ? queryPath('/dashboard', {
          scope: app.scope,
          time_range: app.timeRange,
          timezone: 'Asia/Seoul',
        })
      : null,
  );
  const incidents = useList(
    app.canOperate
      ? queryPath('/incidents', {
          scope: app.scope,
          from: app.timeRange.start,
          to: app.timeRange.end,
          limit: 8,
        })
      : null,
    true,
  );
  const reports = useList(
    app.canOperate ? queryPath('/reports', { scope: app.scope, limit: 4 }) : null,
    true,
  );
  const d = dashboard.data || {};
  const counts = [
    ['기간 내 사건', d.incident_count],
    ['대기 작업', obj(d.jobs).queued],
    ['실행 중', obj(d.jobs).running],
  ];
  return (
    <div className="ops-page">
      <header className="ops-intro">
        <div>
          <span className="ops-overline">GPU Ops Advisor / 운영</span>
          <h1 tabIndex={-1}>지금, 확인할 일부터.</h1>
          <p>사건을 확인하고, 운영 분석을 읽고, 다음 판단을 기록하세요.</p>
        </div>
        <Link className="button primary" to="/reports/new">
          <FileChartColumn size={17} />
          운영 분석 요청
        </Link>
      </header>
      <QueryState query={dashboard}>
        <section className="ops-pulse" aria-label="선택 기간 현황">
          {counts.map(([name, value]) => (
            <div key={String(name)}>
              <span>{String(name)}</span>
              <strong>{typeof value === 'number' ? value : '—'}</strong>
            </div>
          ))}
          <div className="ops-quality">
            <Radar size={24} />
            <div>
              <b>관측 신뢰도</b>
              <p>
                {str(obj(d.quality).reason)
                  ? '전체 상태를 확정할 근거가 부족합니다.'
                  : '범위별 관측 품질을 확인하세요.'}
              </p>
              <SectionLink to="/fleet/quality">부족한 관측 확인</SectionLink>
            </div>
          </div>
        </section>
      </QueryState>
      <div className="ops-home-grid">
        <section className="ops-section">
          <header>
            <div>
              <span className="ops-overline">사건 확인</span>
              <h2>최근 들어온 신호</h2>
            </div>
            <SectionLink to="/cases">전체 사건</SectionLink>
          </header>
          <p className="ops-caption">
            선택 기간의 최근 사건입니다. 발생 순서이며 위험 점수 순위가 아닙니다.
          </p>
          <QueryState query={incidents} empty={!incidents.items.length}>
            <OperationCaseList items={incidents.items} />
          </QueryState>
        </section>
        <aside className="ops-reading">
          <div className="ops-reading-title">
            <FileChartColumn size={24} />
            <h2>운영을 이해하는 보고서</h2>
          </div>
          <p>저장된 수치와 해석 한계를 함께 읽습니다.</p>
          <QueryState query={reports} empty={!reports.items.length}>
            {reports.items.map((r) => (
              <Link className="ops-report-teaser" key={str(r.id)} to={`/reports/${str(r.id)}`}>
                <Badge status={str(r.result_status, 'unpublished')} />
                <h3>{reportTitle(r)}</h3>
                <p>
                  {strings(r.topic_ids)
                    .map((t) => topics[Number(t.slice(1)) - 1] || t)
                    .join(' / ')}
                </p>
                <small>{formatDate(str(r.created_at))}</small>
                <ArrowRight size={18} />
              </Link>
            ))}
          </QueryState>
          <SectionLink to="/reports">보고서 서재</SectionLink>
        </aside>
      </div>
      <section className="ops-next">
        <Link to="/fleet/assets">
          <Telescope />
          <div>
            <b>어떤 자산이 관측되었나요?</b>
            <span>GPU·Node·Pod와 저장된 관계 확인</span>
          </div>
          <ArrowRight />
        </Link>
        <Link to="/schedules">
          <ClipboardList />
          <div>
            <b>반복 분석은 일정으로</b>
            <span>정기 보고서와 예정·발생 이력 관리</span>
          </div>
          <ArrowRight />
        </Link>
        <Link to="/jobs">
          <Radar />
          <div>
            <b>요청한 분석은 어디까지?</b>
            <span>대기 사유·진행·실패 이력 확인</span>
          </div>
          <ArrowRight />
        </Link>
      </section>
    </div>
  );
}
export function OperationsCases() {
  const app = useApp(),
    [params, setParams] = useSearchParams();
  const status = params.get('status') || '';
  const tab = ['analyses', 'reports'].includes(params.get('tab') || '')
    ? params.get('tab')!
    : 'incidents';
  const q = useList(
    app.canOperate
      ? queryPath('/' + (tab === 'reports' ? 'analyses' : tab), {
          scope: app.scope,
          status: tab === 'reports' ? 'succeeded' : status,
          limit: 30,
        })
      : null,
    true,
  );
  return (
    <div className="ops-page">
      <header className="ops-intro">
        <div>
          <span className="ops-overline">사건 대응</span>
          <h1 tabIndex={-1}>어떤 사건을 확인할까요?</h1>
          <p>알람 발생, 사건 처리, 사람의 검토를 구분해 확인합니다.</p>
        </div>
        <Link className="button primary" to="/cases?tab=reports">
          최종 보고서
        </Link>
      </header>
      <div className="tabs">
        {[
          ['incidents', '사건'],
          ['analyses', '조사 이력'],
          ['reports', '최종 보고서'],
        ].map(([value, label]) => (
          <button
            key={value}
            className={tab === value ? 'active' : ''}
            onClick={() => {
              const next = new URLSearchParams(params);
              next.set('tab', value);
              next.delete('status');
              setParams(next);
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {tab !== 'reports' && (
        <div
          className="ops-filter-pills"
          aria-label={tab === 'incidents' ? '사건 처리 상태' : '실행 상태'}
        >
          {(tab === 'incidents'
            ? [
                ['', '전체 사건'],
                ['open', '열린 사건'],
                ['acknowledged', '확인한 사건'],
                ['closed', '종결한 사건'],
              ]
            : ['', 'queued', 'running', 'succeeded', 'failed', 'cancelled'].map((value) => [
                value,
                labels[value] || '전체',
              ])
          ).map(([value, label]) => (
            <button
              key={value}
              aria-pressed={status === value}
              onClick={() => {
                const next = new URLSearchParams(params);
                next.set('status', value);
                setParams(next);
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      <section className="ops-section">
        <QueryState query={q} empty={!q.items.length}>
          {tab !== 'incidents' ? (
            <JobRows items={q.items} />
          ) : (
            <OperationCaseList items={q.items} />
          )}
        </QueryState>
        <More query={q} />
      </section>
      <p className="ops-caption">
        사건은 알람을 통해 접수됩니다. 알람 해제는 원인 확인이나 실제 복구 완료를 의미하지 않습니다.
      </p>
    </div>
  );
}
export function OperationsReports() {
  const app = useApp(),
    [params, setParams] = useSearchParams();
  const topic = params.get('topic') || '';
  const finalOnly = params.get('tab') === 'final';
  const q = useList(
    app.canOperate
      ? queryPath('/reports', {
          scope: app.scope,
          topic_id: topic,
          status: finalOnly ? 'succeeded' : '',
          limit: 30,
        })
      : null,
    true,
  );
  return (
    <div className="ops-page">
      <header className="ops-intro">
        <div>
          <span className="ops-overline">분석 서재</span>
          <h1 tabIndex={-1}>수치에서 운영 판단으로.</h1>
          <p>무엇이 관측되었는지, 무엇을 아직 판단할 수 없는지 함께 확인하세요.</p>
        </div>
        <div className="head-actions">
          <Link className="button primary" to="/reports?tab=final">
            최종 보고서 <ArrowRight size={16} />
          </Link>
          <Link className="button" to="/reports/new">
            새 운영 분석 요청 <ArrowRight size={16} />
          </Link>
        </div>
      </header>
      <div className="tabs" aria-label="보고서 보기">
        {[
          [false, '전체 이력'],
          [true, '최종 보고서'],
        ].map(([final, label]) => (
          <button
            key={String(label)}
            className={finalOnly === final ? 'active' : ''}
            aria-pressed={finalOnly === final}
            onClick={() => {
              const next = new URLSearchParams(params);
              if (final) next.set('tab', 'final');
              else next.delete('tab');
              setParams(next);
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {finalOnly && (
        <section className="ops-section">
          <h2>공개된 Ops 최종 보고서</h2>
          <p>
            완료된 보고서를 바로 읽을 수 있습니다. 자료 부족·부분 분석 여부는 결과 품질에서
            확인하세요.
          </p>
        </section>
      )}
      <div className="ops-report-tools">
        <Field label="궁금한 분석 주제">
          <select
            value={topic}
            onChange={(e) => {
              const next = new URLSearchParams(params);
              next.set('topic', e.target.value);
              setParams(next);
            }}
          >
            <option value="">모든 주제</option>
            {topics.map((t, i) => (
              <option key={t} value={topicId(i)}>
                {t}
              </option>
            ))}
          </select>
        </Field>
        <SectionLink to="/schedules">정기 보고서 관리</SectionLink>
      </div>
      <QueryState query={q} empty={!q.items.length}>
        <div className="ops-library">
          {q.items.map((r, i) => (
            <Link
              className="ops-report-book"
              key={str(r.id)}
              to={`/reports/${str(r.id)}${r.result_ref != null ? '#final-report' : ''}`}
            >
              <div className="ops-book-spine">
                <FileChartColumn size={32} />
                <span>{String(i + 1).padStart(2, '0')}</span>
              </div>
              <div>
                <div className="head-actions">
                  <Badge status={str(r.status) || null} />
                  <Badge status={str(r.result_status, 'unpublished')} />
                </div>
                <h2>{reportTitle(r)}</h2>
                <p>
                  {strings(r.topic_ids)
                    .map((t) => topics[Number(t.slice(1)) - 1] || t)
                    .join(' / ')}
                </p>
                <dl>
                  <dt>분석 기간</dt>
                  <dd>
                    {formatDate(str(obj(r.time_range).start))} —{' '}
                    {formatDate(str(obj(r.time_range).end))}
                  </dd>
                  <dt>생성 시각</dt>
                  <dd>{formatDate(str(r.created_at))}</dd>
                </dl>
                <span className="ops-link">
                  {r.result_ref != null ? '최종 보고서 보기' : '진행 확인'} <ArrowRight size={16} />
                </span>
              </div>
            </Link>
          ))}
        </div>
      </QueryState>
      <More query={q} />
    </div>
  );
}
