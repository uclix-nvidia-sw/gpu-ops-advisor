import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { WorkloadContext } from './WorkloadContext';

it('preserves old reports and identifies unavailable context without zero substitution', () => {
  expect(renderToStaticMarkup(<WorkloadContext value={{}} />)).toBe('');
  const html = renderToStaticMarkup(
    <WorkloadContext value={{ version: 'pod-workload-context-v1', records: [] }} />,
  );
  expect(html).toContain('연결할 작업 자료가 없습니다');
  expect(html).toContain('실제 할당량이 아니며');
});

it('keeps declared tests, unknown purpose, request ranges and completion separate', () => {
  const base = {
    cluster_id: 'cpc-2',
    namespace: 'test-project',
    regular_gpu_request: 1,
    phase: 'Pending',
    node: null,
    period: {},
    uid: 'a',
    pod: 'hidden-detail-pod',
    workload_type: '배치 부하 모의 테스트',
    profile: 'batch-wave',
    execution: 'batch',
    queue_design: 'pod-antiaffinity',
  };
  const html = renderToStaticMarkup(
    <WorkloadContext
      value={{
        version: 'pod-workload-context-v1',
        records: [
          base,
          {
            ...base,
            uid: 'b',
            regular_gpu_request: 2,
            phase: 'Running',
            node: 'node-b',
            workload_type: '작업 유형 미확인',
            profile: null,
            execution: null,
            queue_design: null,
          },
        ],
        completed_jobs: [
          {
            cluster_id: 'cpc-2',
            namespace: 'test-project',
            job_name: '<unsafe-job>',
            workload_type: '배치 부하 모의 테스트',
          },
        ],
      }}
    />,
  );
  expect(html).toContain('gpu-report-test-profile=batch-wave');
  expect(html).toContain('gpu-report-test-execution=batch');
  expect(html).toContain('gpu-report-test-queue-design=pod-antiaffinity');
  expect(html).toContain('연결된 라벨 자료 없음');
  expect(html.indexOf('연결된 라벨')).toBeLessThan(html.indexOf('작업 라벨의 의미'));
  expect(html).toContain('배치 부하 모의 테스트');
  expect(html).toContain('작업 유형 미확인');
  expect(html).toContain('노드 배정 안 됨');
  expect(html).toContain('노드 배정됨');
  expect(html).toContain('동시 요청 총량이 아닙니다');
  expect(html).toContain('&lt;unsafe-job&gt;');
  expect(html).not.toContain('hidden-detail-pod');
  expect(html).not.toContain('<unsafe-job>');
});
