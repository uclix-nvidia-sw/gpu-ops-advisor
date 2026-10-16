export function readerHTML(root: HTMLElement, title: string): string {
  const copy = root.cloneNode(true) as HTMLElement;
  copy
    .querySelectorAll('button,input,select,textarea,script,iframe,form,.form-error')
    .forEach((node) => node.remove());
  copy.querySelectorAll('details').forEach((node) => node.setAttribute('open', ''));
  copy.querySelectorAll('a').forEach((node) => node.replaceWith(...node.childNodes));
  const heading = document.createElement('h1');
  heading.textContent = title;
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GPU 운영 보고서</title><style>body{font:16px/1.8 system-ui,sans-serif;max-width:1200px;margin:40px auto;padding:0 24px;color:#243c37}table{width:100%;border-collapse:collapse}th,td{padding:12px;text-align:left;border-bottom:1px solid #dce6e1}section{margin:24px 0}p{white-space:pre-wrap}svg{max-width:100%}details{margin:16px 0}h1,h2,h3{color:#173b39}</style></head><body>${heading.outerHTML}<p>현재 화면에 표시된 공개 결과입니다. 화면의 선택 범위와 펼쳐진 분석을 저장합니다. 한국 시간 기준.</p>${copy.innerHTML}</body></html>`;
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
