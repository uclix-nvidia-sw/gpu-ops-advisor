import { useState, type FormEvent } from 'react';
import { num, obj, str, useCommand, type Row } from '../lib/live';
import { reportRequestTime } from '../lib/reportPeriod';
import { reportTitle } from '../lib/workflow';
import { useApp } from '../lib/store';
import { CommandError } from './live';
import { Field, Modal, Notice } from './ui';

export function ReportDeleteButton({ job }: { job: Row }) {
  if (
    job.kind !== 'report' ||
    job.can_delete !== true ||
    job.deletion != null ||
    !str(job.id) ||
    !Number.isInteger(job.version) ||
    num(job.version) < 1
  )
    return null;
  return <ReportDeleteAction job={job} />;
}

function ReportDeleteAction({ job }: { job: Row }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="button danger" onClick={() => setOpen(true)}>
        보고서 삭제
      </button>
      {open && <ReportDeleteDialog job={job} onClose={() => setOpen(false)} />}
    </>
  );
}

export function ReportDeleteDialog({ job, onClose }: { job: Row; onClose: () => void }) {
  const [reason, setReason] = useState('');
  const cmd = useCommand();
  const app = useApp();
  const close = () => {
    if (!cmd.busy) onClose();
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (cmd.busy || !reason.trim()) return;
    if (
      await cmd.run(
        `/jobs/${encodeURIComponent(str(job.id))}/delete`,
        { reason: reason.trim() },
        { version: num(job.version), idempotent: true },
      )
    ) {
      app.notify('보고서를 삭제했습니다. 파일 정리 상태는 작업 이력에서 확인할 수 있습니다.');
      onClose();
    }
  };
  return (
    <Modal title="보고서를 영구 삭제할까요?" onClose={close}>
      <form className="stack" onSubmit={submit}>
        <strong>{reportTitle(job)}</strong>
        <Notice tone="warning">
          보고서 본문, 이 작업의 모든 시도에서 수집한 전용 근거와 생성 파일을 삭제합니다. 삭제한
          내용은 복구할 수 없습니다.
        </Notice>
        <p>
          작업·시도 이력과 삭제 기록은 남습니다. 원본 RCA 조사와 다른 보고서는 유지하며, 다른 기록이
          이 근거를 사용 중이면 삭제하지 않습니다.
        </p>
        <Field label="삭제 사유" hint="작업 이력에 남길 사유를 입력하세요. 최대 500자입니다.">
          <textarea
            required
            maxLength={500}
            rows={3}
            value={reason}
            disabled={cmd.busy}
            onChange={(e) => setReason(e.target.value)}
          />
        </Field>
        <CommandError error={cmd.error} />
        {cmd.error && (
          <button type="button" className="button" disabled={cmd.busy} onClick={app.refresh}>
            현재 상태 다시 확인
          </button>
        )}
        <div className="form-actions">
          <button className="button" type="button" disabled={cmd.busy} onClick={close}>
            돌아가기
          </button>
          <button className="button danger" disabled={cmd.busy || !reason.trim()}>
            {cmd.busy ? '삭제 처리 중…' : '영구 삭제'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function ReportDeletionNotice({ job }: { job: Row }) {
  const deletion = obj(job.deletion);
  if (job.kind !== 'report' || !deletion.deleted_at) return null;
  const cleanup = str(deletion.artifact_cleanup_state);
  return (
    <section className="stack" aria-label="보고서 삭제 기록">
      <h3>삭제된 보고서입니다.</h3>
      <p>
        보고서 본문과 전용 근거를 삭제했습니다. 작업·시도 이력과 삭제 기록만 확인할 수 있습니다.
      </p>
      <dl className="details">
        <dt>삭제 시각</dt>
        <dd>{reportRequestTime(str(deletion.deleted_at))}</dd>
        <dt>삭제 사유</dt>
        <dd>{str(deletion.reason, '미확인')}</dd>
        <dt>삭제한 전용 근거</dt>
        <dd>
          {typeof deletion.evidence_count === 'number' ? `${deletion.evidence_count}건` : '미확인'}
        </dd>
        <dt>생성 파일 정리</dt>
        <dd role="status">
          {cleanup === 'complete'
            ? '정리 완료'
            : cleanup === 'failed'
              ? '정리 지연 · 자동으로 다시 시도합니다.'
              : cleanup === 'pending'
                ? '정리 대기 · 자동으로 진행합니다.'
                : '정리 상태 미확인'}
        </dd>
      </dl>
      {cleanup === 'failed' && (
        <Notice tone="warning">
          본문과 근거 삭제는 완료됐습니다. 파일 정리가 계속 지연되면 운영 담당자가 Ops Agent 상태를
          확인해야 합니다.
        </Notice>
      )}
    </section>
  );
}
