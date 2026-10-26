import { describe, expect, it } from 'vitest';
import {
  category,
  categorySummary,
  dailyCounts,
  deviceRepeats,
  incidentLabel,
  incidentView,
  incidentViews,
  nodeStats,
  windowDays,
} from './incidentOverview';

const now = new Date('2026-10-26T07:10:00Z');
const incident = (over: Record<string, unknown>) => ({
  id: 'i',
  occurred_at: '2026-10-26T06:54:10Z',
  alarm_status: 'resolved',
  alarm_resolved_at: '2026-10-26T07:00:00Z',
  target: {
    alertname: 'GPUAlert',
    cluster_id: 'cpc-1',
    k8s_node_name: 'dgx01',
    component: 'accelerator-nvidia-error-xid',
    title:
      'XID 79 ROBUST_CHANNEL_GPU_HAS_FALLEN_OFF_THE_BUS GPU has fallen off the bus detected on GPU PCI:0000:90:00 UUID:GPU-339d635d',
  },
  rca_summary: { latest_published: { job_id: 'job-1', result_status: 'ready' } },
  ...over,
});

describe('incident overview', () => {
  it('names the error, device and NVIDIA action from the Runbook labels', () => {
    const v = incidentView(incident({}), now);
    expect(v.code).toBe('xid:79');
    expect(v.codeText).toBe('XID 79');
    expect(v.label?.action).toBe('호스트 재시작 (RESTART_BM)');
    expect(v.label?.steps.length).toBeGreaterThan(3);
    expect([v.node, v.device, v.kind]).toEqual(['dgx01', '0000:90:00', 'gpu']);
    expect([v.rca, v.jobId]).toEqual(['ready', 'job-1']);
  });

  it('treats SXID devices as switches and components as host with the Fleet reason', () => {
    const sxid = incidentView(
      incident({
        target: {
          k8s_node_name: 'dgx02',
          title: 'SXID 11001(ingress invalid command) detected on PCI:0000:c8:00.0',
        },
      }),
      now,
    );
    expect([sxid.code, sxid.kind, sxid.device]).toEqual(['sxid:11001', 'switch', '0000:c8:00.0']);
    const disk = incidentView(
      incident({
        target: {
          k8s_node_name: 'dgx02',
          component: 'disk',
          title: 'filesystem remounted as read-only due to errors',
        },
      }),
      now,
    );
    expect([disk.code, disk.kind, disk.reason]).toEqual([
      'component:disk',
      'host',
      '읽기 전용 재마운트',
    ]);
    expect(disk.label?.name).toBeTruthy();
  });

  it('separates stale firing alerts, notices and RCA skipped by an early resolve', () => {
    const fresh = incidentView(incident({ alarm_status: 'firing', alarm_resolved_at: null }), now);
    expect([fresh.firing, fresh.stale]).toEqual([true, false]);
    const stale = incidentView(
      incident({ alarm_status: 'firing', occurred_at: '2026-10-23T08:48:10Z' }),
      now,
    );
    expect(stale.stale).toBe(true);
    const notice = incidentView(
      incident({
        rca_summary: {},
        rca_eligibility_reason: 'analysis_policy_unconfigured',
        target: {
          alertname: 'GPUErrorNotice',
          title: '[Warning] XID 13 Graphics Engine Exception',
        },
      }),
      now,
    );
    expect(notice.rca).toBe('notice');
    expect(incidentView(incident({ rca_summary: {} }), now).rca).toBe('none');
    expect(
      incidentView(
        incident({ rca_summary: { latest_job: { job_id: 'j', status: 'running' } } }),
        now,
      ).rca,
    ).toBe('running');
  });

  it('counts repeats per device, per day and per node', () => {
    const views = incidentViews(
      [
        incident({ id: 'a', occurred_at: '2026-10-24T01:00:00Z' }),
        incident({ id: 'b', occurred_at: '2026-10-25T01:00:00Z' }),
        incident({ id: 'c' }),
        incident({
          id: 'd',
          alarm_status: 'firing',
          target: {
            k8s_node_name: 'dgx02',
            component: 'disk',
            title: 'filesystem remounted as read-only due to errors',
          },
        }),
      ],
      now,
    );
    expect(views.map((v) => [v.id, v.nth])).toEqual([
      ['d', 1],
      ['c', 3],
      ['b', 2],
      ['a', 1],
    ]);
    const days = windowDays(now, 3);
    expect(days).toEqual(['2026-10-24', '2026-10-25', '2026-10-26']);
    const [top] = deviceRepeats(views, days);
    expect([top.count, top.perDay, top.kind]).toEqual([3, [1, 1, 1], 'gpu']);
    expect(dailyCounts(views, days)[2]).toEqual({
      day: '2026-10-26',
      counts: { gpu: 1, link: 0, net: 0, server: 1 },
    });
    expect(nodeStats(views).map((n) => [n.node, n.total, n.devices, n.firing])).toEqual([
      ['dgx01', 3, 1, 0],
      ['dgx02', 1, 0, 1],
    ]);
    expect(categorySummary(views)).toBe('GPU 자체 3 · 서버 1');
  });

  it('groups errors by what an operator, researcher or manager recognises', () => {
    const of = (code: string) => category({ code, label: incidentLabel(code) });
    expect(of('xid:79')).toBe('gpu');
    expect(of('xid:74')).toBe('link');
    expect(of('sxid:11001')).toBe('link');
    expect(of('component:accelerator-nvidia-dcgm-nvswitch')).toBe('link');
    expect(of('component:accelerator-nvidia-infiniband')).toBe('net');
    expect(of('component:network-ethernet')).toBe('net');
    expect(of('component:accelerator-nvidia-dcgm-thermal')).toBe('gpu');
    expect(of('component:disk')).toBe('server');
    expect(of('')).toBe('server');
  });
});
