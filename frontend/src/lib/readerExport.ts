import adviceColors from './advice-colors.css?inline';
import console2Charts from '../components/console2-charts.css?inline';

export function readerHTML(root: HTMLElement, title: string): string {
  const copy = root.cloneNode(true) as HTMLElement;
  copy
    .querySelectorAll('button,input,select,textarea,script,iframe,form,.form-error')
    .forEach((node) => node.remove());
  copy
    .querySelectorAll('details:not(.aggregate-advice-evidence)')
    .forEach((node) => node.setAttribute('open', ''));
  copy.querySelectorAll('a').forEach((node) => node.replaceWith(...node.childNodes));
  const heading = document.createElement('h1');
  heading.textContent = title;
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${heading.innerHTML}</title><style>body{font:16px/1.8 system-ui,sans-serif;max-width:1200px;margin:40px auto;padding:0 24px;color:#243c37}table{width:100%;border-collapse:collapse}th,td{padding:12px;text-align:left;border-bottom:1px solid #dce6e1}section{margin:24px 0}p{white-space:pre-wrap}svg{max-width:100%}details{margin:16px 0}h1,h2,h3,h4,h5,h6{color:#173b39}.aggregate-advice-cluster{margin:20px 0;padding:16px 18px;border:1px solid #dce6e1;border-left:5px solid #156e57;border-radius:8px;background:#fff}.aggregate-advice-cluster .aggregate-advice-card-title{font-size:16px;margin:0 0 4px;color:#156e57}.aggregate-advice-cluster .aggregate-advice-cluster-target{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 8px;margin:0 0 8px;font-size:13px;font-weight:400;color:#596762}.aggregate-advice-cluster-target>code{display:inline-block;max-width:100%;padding:1px 6px;border:1px solid #cfe1d7;border-radius:4px;background:#edf7f1;color:inherit;font-family:ui-monospace,monospace;font-size:.95em;line-height:1.5;overflow-wrap:anywhere}.aggregate-advice-namespace{margin:0 0 0 8px}.aggregate-advice-namespace+.aggregate-advice-namespace{margin-top:20px;padding-top:16px;border-top:1px solid #dce6e1}.aggregate-advice-namespace .aggregate-advice-identity{display:grid;grid-template-columns:6.3em .65em minmax(0,1fr);column-gap:6px;align-items:baseline;margin:0 0 8px;font-size:14px;font-weight:400;line-height:1.6;color:#596762}.aggregate-advice-identity>code{min-width:0;font-size:.95em;font-weight:500;color:#243c37;overflow-wrap:anywhere}.aggregate-namespace-summary>li{margin:0;overflow-wrap:anywhere}.aggregate-namespace-summary>li+li{margin-top:20px}.aggregate-advice-heading{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline;margin:0 0 4px}.aggregate-advice-heading h5{font-size:14px;font-weight:600;line-height:1.6;margin:0}.aggregate-advice-history{font-size:12px;color:#596762}.aggregate-namespace-summary>li>p{margin:0 0 10px;font-size:14px;font-weight:400;line-height:1.75;white-space:normal}.aggregate-advice-namespace dl{display:grid;gap:4px;margin:0;font-size:13px}.aggregate-advice-namespace dl>div{display:grid;grid-template-columns:6rem minmax(0,1fr);gap:4px 10px;align-items:baseline;margin:0}.aggregate-advice-namespace dt{font-size:12px;color:#596762}.aggregate-advice-namespace dd{margin:0;line-height:1.65;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.aggregate-namespace-summary>li>.aggregate-advice-model,.aggregate-namespace-summary>li>.aggregate-advice-scope{margin:6px 0 0;font-size:12px;font-weight:400;line-height:1.65;color:#596762}.aggregate-advice-namespace details{margin:6px 0 0;padding:0;border:0;font-size:13px}.aggregate-advice-namespace details>summary{cursor:pointer;width:fit-content;padding:4px 0;color:#596762;font-weight:400}.aggregate-advice-namespace details>summary:focus-visible{outline:2px solid #156e57;outline-offset:3px}.aggregate-advice-namespace details>p{margin:8px 0;font-size:13px;line-height:1.75}.aggregate-advice-basis{color:#596762}.aggregate-advice-time-note{font-size:12px;color:#596762;margin:0 0 16px}@media(max-width:640px){.aggregate-advice-cluster{padding:14px 12px}.aggregate-advice-namespace{margin-left:0}.aggregate-advice-namespace dl>div{grid-template-columns:minmax(0,1fr);gap:0}} .aggregate-namespace-summary{list-style:none;padding:0;margin:0}.aggregate-advice-cluster .aggregate-advice-card-title{margin-bottom:4px}.aggregate-advice-namespace details>summary:hover{color:#156e57;text-decoration:underline;text-underline-offset:3px}.aggregate-advice-namespace details[open]>summary{margin-bottom:8px}.aggregate-advice-namespace details>p{color:#596762;font-weight:400}.aggregate-advice-namespace details>p>strong{color:#243c37;font-weight:500}.aggregate-advice-evidence .sr-only{display:none}${adviceColors}${copy.querySelector('.c2-report-visual') ? console2Charts : ''}</style></head><body>${heading.outerHTML}<p>현재 화면에 표시된 공개 결과입니다. 화면의 선택 범위와 펼쳐진 분석을 저장합니다. 한국 시간 기준.</p>${copy.innerHTML}</body></html>`;
}
export function downloadReader(root: HTMLElement, title: string) {
  const url = URL.createObjectURL(
    new Blob([readerHTML(root, title)], { type: 'text/html;charset=utf-8' }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = 'gpu-operations-report.html';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
