"""Check repository-local Markdown links and HTML/SVG assets with Python 3."""
from pathlib import Path
from urllib.parse import unquote, urlsplit
import html
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FENCE = re.compile(r'^```[^\n]*\n.*?^```[^\n]*$', re.M | re.S)
MARKDOWN = re.compile(r'!?\[[^\]\n]*\]\((<[^>\n]+>|[^)\n]+)\)')
ATTRIBUTE = re.compile(r'\b(?:src|href)=["\']([^"\']+)["\']')


def check(root):
    errors = []
    checked = 0
    documents = 0
    for source in sorted(root.rglob('*')):
        if not source.is_file() or source.suffix.lower() not in ('.md', '.html', '.svg'):
            continue
        if {'.git', 'node_modules', '.venv'} & set(source.relative_to(root).parts):
            continue
        documents += 1
        text = source.read_text(encoding='utf-8-sig')
        text = FENCE.sub('', text) if source.suffix.lower() == '.md' else text
        links = MARKDOWN.findall(text) if source.suffix.lower() == '.md' else ATTRIBUTE.findall(text)
        for raw in links:
            link = html.unescape(raw.strip('<>'))
            if link.startswith(('http:', 'https:', 'data:', 'mailto:', '#', 'javascript:')):
                continue
            label = source.relative_to(root).as_posix()
            if re.match(r'^/?[A-Za-z]:[/\\]|^file:|^/', link):
                errors.append(f'{label}: absolute local path: {link}')
                continue
            path = unquote(urlsplit(link).path)
            if not path:
                continue
            target = (source.parent / path).resolve()
            checked += 1
            if not target.is_relative_to(root) or not target.exists():
                errors.append(f'{label}: missing or outside repository: {link}')
                continue
            # Windows also checks exact casing for a later Linux/GitHub checkout.
            current = root
            for segment in target.relative_to(root).parts:
                if segment not in {p.name for p in current.iterdir()}:
                    errors.append(f'{label}: wrong case: {link}')
                    break
                current = current / segment
    return documents, checked, errors


if __name__ == '__main__':
    assert MARKDOWN.findall('[file](<a%20b.md?plain=1#L3>)') == ['<a%20b.md?plain=1#L3>']
    assert not MARKDOWN.findall(FENCE.sub('', '```text\n[x](missing)\n```'))
    documents, checked, errors = check(ROOT)
    for error in errors:
        print(error)
    print(f'{documents} documents; {checked} local links/assets; {len(errors)} errors.')
    sys.exit(bool(errors))
