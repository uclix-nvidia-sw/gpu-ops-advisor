import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RcaStepPoints } from './RcaReportParts';

it('moves the reported branch first and marks commands, actions and prohibitions', () => {
  const html = renderToStaticMarkup(
    <RcaStepPoints
      branches={['GPU requires reset']}
      items={[
        'GPU lost: 작업 배출과 유지보수 승인 뒤 호스트를 재시작합니다.',
        'GPU requires reset: 작업 배출 뒤 해당 GPU를 리셋합니다.',
        '커널 로그에 없으면 재시작하지 않고 nvidia-smi -q로 확인합니다.',
      ]}
    />,
  );
  const items = html.split('<li').slice(1);
  expect(items[0]).toContain('rca-branch-hit');
  expect(items[0]).toContain('▶ ');
  expect(items[0]).toContain('GPU requires reset');
  expect(items[1]).toContain('GPU lost');
  expect(html).toContain('<code class="rca-mark-command rca-nowrap">nvidia-smi -q</code>');
  expect(html).toContain('<mark class="rca-mark-action">호스트를 재시작합니다</mark>');
  expect(html).toContain('<mark class="rca-mark-caution">재시작하지 않고</mark>');
});
