"""Build and validate the portable RCA animation review page (standard library only)."""
import hashlib
import html
import json
from pathlib import Path

root = Path(__file__).resolve().parent
repo = root.parents[1]
# The product report serves the same files; this review page reads them in place.
ASSETS = 'frontend/public/inspection-figures'
manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
items = manifest['items']
assert [item['id'] for item in items] == [f'{family}{i}' for i in range(1, 8) for family in ['S', 'P']]
cards = []
for item in items:
 ident, title, caption = item['id'], item['title'], item['caption']
 for ext, asset in item['assets'].items():
  assert asset['path'] == f'{ASSETS}/{ident}.{ext}'
  assert hashlib.sha256((repo / asset['path']).read_bytes()).hexdigest() == asset['sha256'], ident
 mapping = item

 rows=[]
 for label,key in [('XID','xid'),('SXID','sxid')]:
  value=html.escape(mapping[key]) if mapping[key] else '직접 매핑 없음'
  if ident=='S2' and key=='sxid':
   value=f'<details><summary>92개 코드 보기</summary><p>{value}</p></details>'
  rows.append(f'<dt>{label}</dt><dd>{value}</dd>')
 runbooks=''.join(f'<li>{html.escape(name)}</li>' for name in mapping['runbooks'])
 conditions=''.join(f'<li>{html.escape(condition)}</li>' for condition in mapping['conditions'])
 mapping_html=f'<section class="mapping" aria-label="{ident} 적용 매핑"><h3>적용 매핑 · 조건부 후보</h3><dl>{"".join(rows)}<dt>컴포넌트<br>runbook</dt><dd><ul class="runbooks">{runbooks}</ul></dd></dl><h4>적용 조건</h4><ul class="conditions">{conditions}</ul></section>'

 cards.append(f'''<article><div class="caption"><b>{ident}</b><h2>{html.escape(title)}</h2><p>{html.escape(caption)}</p></div><button class="picture" data-id="{ident}" aria-label="{ident} {html.escape(title)} 크게 보기"><img src="../../{ASSETS}/{ident}.png" alt="{html.escape(caption)}" width="750" height="500"></button><footer><a href="../../{ASSETS}/{ident}.webp" download>WebP 다운로드</a><a href="../../{ASSETS}/{ident}.png" download>정지 이미지</a></footer>{mapping_html}</article>''')
template = (root / 'review-template.html').read_text(encoding='utf-8')
assert template.count('CARDS') == 1
(root / 'index.html').write_text(template.replace('CARDS', ''.join(cards)), encoding='utf-8', newline='\r\n')
print('14 mappings and 28 asset hashes verified; index.html generated.')
