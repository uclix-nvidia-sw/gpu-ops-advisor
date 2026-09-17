"""Check repository-local Markdown links and HTML/SVG assets with Python 3."""
from pathlib import Path
from urllib.parse import unquote, urlsplit
import html
import re
import sys
import os

ROOT = Path(__file__).resolve().parents[1]
FENCE = re.compile(r'^```[^\n]*\n.*?^```[^\n]*$', re.M | re.S)
MARKDOWN = re.compile(r'!?\[[^\]\n]*\]\((<[^>\n]+>|[^)\n]+)\)')
ATTRIBUTE = re.compile(r'\b(?:src|href)=["\']([^"\']+)["\']')


def check(root):
    errors = []
    checked = 0
    documents = 0
    excluded = {'.git', 'node_modules', '.venv', '.local', 'dist', '__pycache__', '.pytest_cache', '.ruff_cache'}
    sources = []
    for current, directories, filenames in os.walk(root):
        directories[:] = [d for d in directories if d not in excluded]
        sources.extend(Path(current) / name for name in filenames)
    for source in sorted(sources):
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
            web_root = label == 'frontend/index.html' and link.startswith('/') and not link.startswith('//')
            if not web_root and re.match(r'^/?[A-Za-z]:[/\\]|^file:|^/', link):
                errors.append(f'{label}: absolute local path: {link}')
                continue
            path = unquote(urlsplit(link).path)
            if not path:
                continue
            target = (source.parent / path).resolve()
            if web_root:
                # Vite serves source paths from frontend/ and static assets from public/.
                target = (source.parent / path[1:]).resolve()
                if not target.is_relative_to(source.parent):
                    errors.append(f'{label}: outside frontend root: {link}')
                    continue
                if not target.exists():
                    target = (source.parent / 'public' / path[1:]).resolve()
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
    from tempfile import TemporaryDirectory

    assert MARKDOWN.findall('[file](<a%20b.md?plain=1#L3>)') == ['<a%20b.md?plain=1#L3>']
    assert not MARKDOWN.findall(FENCE.sub('', '```text\n[x](missing)\n```'))
    with TemporaryDirectory() as directory:
        sample = Path(directory).resolve()
        frontend = sample / 'frontend'
        (frontend / 'src').mkdir(parents=True)
        (frontend / 'public').mkdir()
        (frontend / 'src/main.tsx').write_text('', encoding='utf-8')
        (frontend / 'public/favicon.svg').write_text('<svg/>', encoding='utf-8')
        entry = frontend / 'index.html'
        entry.write_text('<script src="/src/main.tsx"></script><link href="/favicon.svg">', encoding='utf-8')
        assert check(sample)[1:] == (2, [])
        entry.write_text('<link href="/missing.svg"><link href="/../README.md">', encoding='utf-8')
        assert len(check(sample)[2]) == 2
    documents, checked, errors = check(ROOT)
    for error in errors:
        print(error)
    print(f'{documents} documents; {checked} local links/assets; {len(errors)} errors.')
    sys.exit(bool(errors))
