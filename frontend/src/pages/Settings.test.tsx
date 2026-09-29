import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ModelForm } from './Settings';

vi.mock('../lib/store', () => ({ useApp: () => ({ canManage: true }) }));
vi.mock('../lib/live', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/live')>()),
  useCommand: () => ({ busy: false, error: '서버 연결을 확인해 주세요.' }),
}));

describe('model registration', () => {
  it('starts with only endpoint and model name, and keeps server errors visible', () => {
    const html = renderToStaticMarkup(<ModelForm initial={{}} onClose={() => {}} />);
    const basic = html.split('<details>')[0];
    expect(basic.match(/<input /g)).toHaveLength(2);
    expect(basic.match(/required=""/g)).toHaveLength(2);
    expect(basic).toContain('API 기본 주소');
    expect(basic).toContain('모델 이름');
    expect(basic).toContain('인증');
    expect(basic).toContain('value="env:LLM_API_KEY" selected=""');
    expect(html).toContain('<details><summary>추가 설정 (선택)</summary>');
    expect(html).toContain('value="C07"');
    expect(html).toContain('서버 연결을 확인해 주세요.');
    expect(html).not.toContain('<details open');
  });

  it('keeps existing metadata editable without echoing credentials into the input', () => {
    const html = renderToStaticMarkup(
      <ModelForm
        initial={{
          id: 'model-id',
          name: '사내 모델',
          endpoint_url: 'https://llm.example.com/v1',
          model_name: 'internal-model',
          artifact_revision: 'artifact-7',
          engine_revision: 'engine-3',
          precision: 'bf16',
          secret_ref: 'env:LLM_API_KEY',
          capabilities: { tools: true },
        }}
        onClose={() => {}}
      />,
    );
    for (const value of ['사내 모델', 'artifact-7', 'engine-3', 'bf16']) {
      expect(html).toContain(`value="${value}"`);
    }
    expect(html).toContain('value="env:LLM_API_KEY" selected=""');
    expect(html).toContain('키 원문은 이 화면에 저장하지 않습니다.');
  });
});
