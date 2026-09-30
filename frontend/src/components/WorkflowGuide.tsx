import { useState } from 'react';
import { Link } from 'react-router-dom';
import { obj, str, type Row } from '../lib/live';
import { publicationStep, rcaSteps, reportSteps, workflowValues } from '../lib/workflow';
import { Badge, Notice } from './ui';
import { DataView } from './live';

export function WorkflowGuide({ job, kind = 'rca' }: { job?: Row; kind?: string }) {
  const report = (job?.kind || kind) === 'report';
  const steps = [...(report ? reportSteps : rcaSteps), publicationStep];
  const [selected, setSelected] = useState(0);
  const step = steps[Math.min(selected, steps.length - 1)];
  const values = job ? workflowValues(step, job) : {};
  const present = Object.values(values).filter((v) => v != null).length;
  return (
    <section
      className="workflow-guide"
      aria-label={`${report ? '보고서' : 'RCA'} 워크플로우 검증 가이드`}
    >
      <div className="workflow-heading">
        <div>
          <span className="dev-kicker">{report ? 'REPORT' : 'RCA'} / 검증 가이드</span>
          <h2>이 흐름은 어디에서 확인하나요?</h2>
        </div>
        <span className="guide-disclaimer">설계 흐름 · 실시간 실행 추적이 아님</span>
      </div>
      <div className="workflow-layout">
        <nav aria-label="검증 단계" className="workflow-steps">
          {steps.map((s, i) => (
            <button key={s.title} aria-pressed={selected === i} onClick={() => setSelected(i)}>
              <span>{String(i + 1).padStart(2, '0')}</span>
              <div>
                <b>{s.title}</b>
                <small>{s.owner}</small>
              </div>
            </button>
          ))}
        </nav>
        <div className="workflow-inspector">
          <h3>{step.title}</h3>
          <p>{step.purpose}</p>
          <dl className="guide-fields">
            <dt>확인할 데이터</dt>
            <dd>
              <code>{step.inspect}</code>
            </dd>
            <dt>판단 기준</dt>
            <dd>{step.expected}</dd>
            <dt>조회 한계·다음 확인</dt>
            <dd>{step.missing}</dd>
          </dl>
          {job ? (
            <>
              <div className="head-actions">
                <Badge status={str(job.status) || 'unknown'} />
                <span>
                  서버 단계 <code>{str(job.stage, '미확인')}</code>
                </span>
                <span>
                  선택 단계 관련 필드 {present}/{step.fields.length}개 제공 · 정상 판정 아님
                </span>
              </div>
              <DataView value={values} explain />
              <details>
                <summary>제공된 값 그대로 보기</summary>
                <pre>{JSON.stringify(values, null, 2)}</pre>
              </details>
            </>
          ) : (
            <Notice>작업을 선택하면 이 안내 옆에 해당 작업의 실제 데이터를 표시합니다.</Notice>
          )}
          <div className="head-actions">
            {job?.incident_id != null && (
              <Link className="button" to={`/incidents/${str(job.incident_id)}`}>
                사건 입력 확인
              </Link>
            )}
            <Link className="button" to="/settings/backend">
              서비스·큐 확인
            </Link>
            {report && (
              <Link className="button" to="/schedules">
                정기 발생 이력
              </Link>
            )}
          </div>
        </div>
      </div>
      {job && (
        <div className="dev-contract-line">
          공개 참조: <code>{str(job.result_ref, '미공개')}</code> · 결과 품질:{' '}
          <Badge
            status={
              job.result_ref != null
                ? str(obj(job.result).result_status, str(job.result_status, 'unknown'))
                : 'unpublished'
            }
          />{' '}
          · 실행 성공과 근거 충분성은 별개
        </div>
      )}
    </section>
  );
}
