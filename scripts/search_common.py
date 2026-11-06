"""Shared sitemap and HTML validation; no credentials or network side effects."""
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

BASE = 'https://www.wangsaiyu.com'
NS = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.canonical = []
        self.meta = {}
        self.title = ''
        self.in_title = False
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical.append(attrs.get('href'))
        if tag == 'meta':
            key = attrs.get('name', attrs.get('http-equiv', '')).lower()
            self.meta[key] = attrs.get('content', '')
        if tag == 'title':
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def parse_sitemap(data):
    root = ET.fromstring(data)
    if root.tag != '{%s}urlset' % NS['s']:
        raise ValueError('Expected a URL sitemap, not a sitemap index')
    records, seen = [], set()
    for entry in root.findall('s:url', NS):
        url = entry.findtext('s:loc', namespaces=NS)
        parsed = urlsplit(url or '')
        if (parsed.scheme != 'https' or parsed.netloc != 'www.wangsaiyu.com'
                or parsed.query or parsed.fragment or '..' in unquote(parsed.path).split('/')):
            raise ValueError('Sitemap contains a noncanonical URL')
        if url in seen:
            raise ValueError('Duplicate sitemap URL: ' + url)
        seen.add(url)
        records.append({'url': url, 'lastmod': entry.findtext('s:lastmod', default='', namespaces=NS)})
    if not records:
        raise ValueError('Empty sitemap')
    return records


def page_file(public, url):
    path = unquote(urlsplit(url).path).lstrip('/')
    target = Path(public) / path
    return target / 'index.html' if not path or path.endswith('/') else target


def article_records(public):
    records = parse_sitemap((Path(public) / 'sitemap-articles.xml').read_bytes())
    for record in records:
        record['hash'] = hashlib.sha256(page_file(public, record['url']).read_bytes()).hexdigest()
    return sorted(records, key=lambda r: (r['lastmod'], r['url']), reverse=True)


def save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)
