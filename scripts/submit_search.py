"""Submit new/changed articles; API receipt is not a promise of indexing."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from search_common import BASE, article_records, save_state


def request(url, data, content_type):
    # Never log request URLs: Baidu authenticates via a query parameter.
    req = Request(url, data=data, headers={'Content-Type': content_type,
                                         'User-Agent': 'SaiyuDoc-SearchSubmit/1.0'})
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()
    except (URLError, TimeoutError):
        raise RuntimeError('Search submission network error (credentials omitted)') from None


def baidu(records, state, path, send=request):
    token = os.environ.get('BAIDU_TOKEN')
    if not token:
        raise RuntimeError('BAIDU_TOKEN is not configured')
    endpoint = 'https://data.zz.baidu.com/urls?' + urlencode({'site': BASE, 'token': token})
    accepted = 0
    # Probe with one article; never send a full sitemap against an unknown quota.
    for record in records[:20]:
        status, raw = send(endpoint, record['url'].encode(), 'text/plain; charset=utf-8')
        try:
            result = json.loads(raw)
        except ValueError:
            raise RuntimeError('Baidu returned a non-JSON response, HTTP ' + str(status)) from None
        if result.get('message') == 'over quota':
            print('::warning::Baidu quota unavailable; pending articles retained. Check the verified site quota.')
            return accepted, 'quota'
        if status != 200 or result.get('error') or result.get('success') != 1 or result.get('not_valid') or result.get('not_same_site'):
            raise RuntimeError('Baidu rejected submission (HTTP %s, code %s)' % (status, result.get('error')))
        state[record['url']] = record['hash']
        save_state(path, state)
        accepted += 1
        if result.get('remain') == 0:
            return accepted, 'quota' if len(records) > accepted else 'accepted'
    return accepted, 'pending' if len(records) > accepted else 'accepted'


def indexnow(records, state, path, public, send=request):
    key = (Path(public) / 'indexnow-key.txt').read_text().strip()
    payload = {'host': 'www.wangsaiyu.com', 'key': key,
               'keyLocation': BASE + '/indexnow-key.txt',
               'urlList': [r['url'] for r in records[:10000]]}
    status, _ = send('https://api.indexnow.org/indexnow', json.dumps(payload).encode(), 'application/json; charset=utf-8')
    if status not in (200, 202):
        raise RuntimeError('IndexNow rejected submission, HTTP ' + str(status))
    for record in records[:10000]:
        state[record['url']] = record['hash']
    save_state(path, state)
    return min(len(records), 10000), 'verification_pending' if status == 202 else 'accepted'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', choices=['baidu', 'indexnow'], required=True)
    parser.add_argument('--public', default='public')
    parser.add_argument('--state-dir', default='.search-state')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    path = Path(args.state_dir) / (args.engine + '.json')
    state = json.loads(path.read_text()) if path.exists() else {}
    records = [r for r in article_records(args.public) if state.get(r['url']) != r['hash']]
    report = {'engine': args.engine, 'pending_before': len(records), 'accepted': 0, 'status': 'unchanged'}
    try:
        if args.dry_run:
            report['status'] = 'dry_run'
        elif records:
            if args.engine == 'baidu':
                report['accepted'], report['status'] = baidu(records, state, path)
            else:
                report['accepted'], report['status'] = indexnow(records, state, path, args.public)
        report['pending_after'] = sum(state.get(r['url']) != r['hash'] for r in records)
        print(json.dumps(report))
        return 2 if report['status'] == 'quota' else 0
    except Exception:
        report['status'] = 'failed'
        raise
    finally:
        report['pending_after'] = sum(state.get(r['url']) != r['hash'] for r in records)
        report['accepted'] = len(records) - report['pending_after']
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
                summary.write('\n### Search submission\n\n```json\n' + json.dumps(report) + '\n```\nAPI receipt does not guarantee indexing or ranking.\n')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, OSError) as error:
        print('::error::' + str(error), file=sys.stderr)
        sys.exit(1)
