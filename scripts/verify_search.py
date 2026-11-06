"""Validate published search inputs and TLS without generating visitor events."""
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import socket
import ssl
from urllib.request import Request, urlopen
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from search_common import BASE, Page, parse_sitemap, page_file


def validate_page(text, url):
    page = Page(text)
    assert page.canonical == [url], 'Canonical mismatch: ' + url
    assert page.title.strip(), 'Missing title: ' + url
    assert page.meta.get('description', '').strip(), 'Missing description: ' + url
    assert 'This is my cool site' not in page.meta['description'], 'Theme placeholder: ' + url
    assert 'noindex' not in page.meta.get('robots', '').lower(), 'Noindex: ' + url
    assert 'refresh' not in page.meta, 'Redirect in sitemap: ' + url


def fetch(url):
    request_url = quote(url, safe=':/%?=&')
    with urlopen(Request(request_url, headers={'User-Agent': 'SaiyuDoc-SearchHealth/1.0'}), timeout=30) as response:
        assert response.status == 200, 'HTTP status: ' + url
        assert response.url == request_url, 'Unexpected redirect: ' + url
        assert 'noindex' not in response.headers.get('X-Robots-Tag', '').lower()
        return response.read()


def reachable_articles(public, articles):
    """Follow static HTML links, including archive pagination, without JavaScript."""
    visited, pending = set(), [BASE + '/']
    while pending:
        url = pending.pop()
        if url in visited:
            continue
        visited.add(url)
        file = page_file(public, url)
        if not file.is_file() or file.suffix != '.html':
            continue
        for href in Page(file.read_text()).links:
            target = urlsplit(urljoin(url, href))
            if target.scheme in ('http', 'https') and target.netloc in ('wangsaiyu.com', 'www.wangsaiyu.com'):
                path = unquote(target.path)
                if '..' not in path.split('/'):
                    pending.append(BASE + (path or '/'))
    missing = {unquote(record['url']) for record in articles} - visited
    assert not missing, 'Articles unreachable through static links: ' + ', '.join(sorted(missing))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--public', default='public')
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    public = Path(args.public)
    all_urls = parse_sitemap((public / 'sitemap.xml').read_bytes())
    articles = parse_sitemap((public / 'sitemap-articles.xml').read_bytes())
    assert {r['url'] for r in articles} <= {r['url'] for r in all_urls}
    for record in all_urls:
        validate_page(page_file(public, record['url']).read_text(), record['url'])
        if record['lastmod']:
            assert datetime.fromisoformat(record['lastmod']) <= datetime.now(timezone.utc) + timedelta(minutes=5)
    robots = (public / 'robots.txt').read_text()
    for name in ['sitemap.xml', 'sitemap-articles.xml']:
        assert 'Sitemap: ' + BASE + '/' + name in robots
    parser = RobotFileParser()
    parser.parse(robots.splitlines())
    for bot in ['Googlebot', 'bingbot', 'Baiduspider']:
        assert all(parser.can_fetch(bot, record['url']) for record in articles), 'Robots blocks ' + bot
    reachable_articles(public, articles)
    print('Local validation:', len(all_urls), 'URLs;', len(articles), 'articles')
    if args.live:
        for host in ['www.wangsaiyu.com', 'wangsaiyu.com']:
            with socket.create_connection((host, 443), timeout=15) as sock:
                with ssl.create_default_context().wrap_socket(sock, server_hostname=host) as secure:
                    expiry = datetime.fromtimestamp(ssl.cert_time_to_seconds(secure.getpeercert()['notAfter']), timezone.utc)
                    days = (expiry - datetime.now(timezone.utc)).days
                    print('TLS:', host, 'valid for', days, 'days')
                    assert days >= 21, 'Certificate renewal required: ' + host
        for name in ['sitemap.xml', 'sitemap-articles.xml']:
            assert parse_sitemap(fetch(BASE + '/' + name)) == parse_sitemap((public / name).read_bytes()), 'Deployment mismatch: ' + name
        assert fetch(BASE + '/robots.txt').decode().strip() == robots.strip()
        assert fetch(BASE + '/indexnow-key.txt').strip() == (public / 'indexnow-key.txt').read_bytes().strip()
        for record in [{'url': BASE + '/'}] + articles[:3]:
            validate_page(fetch(record['url']).decode(), record['url'])
        print('Live TLS, sitemaps, robots, ownership file and sample pages verified')


if __name__ == '__main__':
    main()
