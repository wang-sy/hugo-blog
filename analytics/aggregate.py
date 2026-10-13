"""Import cumulative browser measurements from RUM; publish only aggregate counts."""
import gzip
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit

from cloud import cos, tencent

TZ = timezone(timedelta(hours=8))
MARKER = 'saiyudoc_metric_v1'
DAY_MS = 86400000
MAX_ACTIVE_MS = 4 * 60 * 60 * 1000
BUCKET = os.environ.get('STATS_BUCKET', 'saiyudoc-stats-1301596189')
PROJECT = int(os.environ.get('RUM_PROJECT_ID', '159725'))
START = int(datetime(2026, 10, 13, tzinfo=TZ).timestamp() * 1000)
STATE_KEY = 'private/state.json.gz'
PUBLIC_KEY = 'public/stats.json'


def iso(timestamp):
    return datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat().replace('+00:00', 'Z')


def day(timestamp):
    return datetime.fromtimestamp(timestamp / 1000, TZ).strftime('%Y-%m-%d')


def empty_state():
    return {'version': 1, 'startedAt': iso(START), 'watermark': START,
            'salt': secrets.token_hex(32), 'days': {}, 'history': [], 'archivedArticles': {}}


def safe_path(value):
    if not isinstance(value, str) or not value.startswith('/') or value.startswith('//') or len(value) > 1024:
        return None
    if any(c in value for c in ('?', '#', '\\', '\x00')):
        return None
    path = unquote(value)
    if any(ord(c) < 32 for c in path) or any(part in ('.', '..') for part in path.split('/')):
        return None
    return path


def apply_log(state, row, now):
    if row.get('env') != 'production' or row.get('ext1') != MARKER:
        return False
    try:
        metric = json.loads(row.get('msg', ''))
        visit = metric['visit']
        started = metric['started']
        active = metric['activeMs']
        path = safe_path(metric['path'])
        if (metric.get('v') != 1 or not path or not isinstance(visit, str) or
                not re.fullmatch(r'[a-f0-9-]{36}', visit) or type(started) is not int or
                type(active) is not int or not START <= started <= now + 60000 or
                day(started) < day(now - 89 * DAY_MS) or not 0 <= active <= MAX_ACTIVE_MS or
                active > max(0, now - started) + 60000):
            return False
        source = urlsplit(row.get('from', ''))
        if source.hostname not in ('wangsaiyu.com', 'www.wangsaiyu.com') or safe_path(source.path) != path:
            return False
        aid = row.get('aid', '')
        if not isinstance(aid, str) or not aid or len(aid) > 128:
            return False
    except (KeyError, ValueError, TypeError):
        return False
    visitor = hmac.new(bytes.fromhex(state['salt']), aid.encode(), hashlib.sha256).hexdigest()[:24]
    date = day(started)
    visits = state['days'].setdefault(date, {})
    previous = visits.get(visit)
    if previous and (previous['p'] != path or previous['u'] != visitor):
        return False
    # Every heartbeat contains the cumulative foreground time: retries and overlapping imports are idempotent.
    visits[visit] = {'p': path, 'u': visitor, 'a': max(active, previous['a'] if previous else 0),
                     'article': path.startswith(('/posts/', '/archives/')) and metric.get('article') is True}
    return True


def summarize(visits):
    values = list(visits)
    articles = [v for v in values if v['article']]
    return {'pageViews': len(values), 'uniqueVisitors': len({v['u'] for v in values}),
            'pageActiveSeconds': round(sum(v['a'] for v in values) / 1000, 1),
            'articleViews': len(articles), 'activeSeconds': round(sum(v['a'] for v in articles) / 1000, 1),
            'measuredReads': len(articles)}


def article_counts(visits):
    output = {}
    for visit in visits:
        if not visit['article']:
            continue
        item = output.setdefault(visit['p'], {'pageViews': 0, 'activeSeconds': 0, 'visitors': set()})
        item['pageViews'] += 1
        item['activeSeconds'] += visit['a'] / 1000
        item['visitors'].add(visit['u'])
    return {path: {'pageViews': value['pageViews'], 'activeSeconds': round(value['activeSeconds'], 1),
                   'uniqueVisitors': len(value['visitors'])} for path, value in output.items()}


def compact(state, now):
    cutoff = day(now - 89 * DAY_MS)
    for date in sorted(list(state['days'])):
        if date >= cutoff:
            continue
        values = list(state['days'].pop(date).values())
        state['history'].append({'date': date, **summarize(values)})
        for path, item in article_counts(values).items():
            archived = state['archivedArticles'].setdefault(path, {'pageViews': 0, 'activeSeconds': 0})
            archived['pageViews'] += item['pageViews']
            archived['activeSeconds'] += item['activeSeconds']


def public_snapshot(state, now):
    daily = list(state['history']) + [{'date': date, **summarize(visits.values())}
                                    for date, visits in sorted(state['days'].items())]
    # The public document is constructed from an allowlist, never a redacted copy of private state.
    totals = {key: round(sum(d[key] for d in daily), 1) for key in
              ('pageViews', 'articleViews', 'pageActiveSeconds', 'activeSeconds', 'measuredReads')}
    cumulative = {path: dict(item) for path, item in state['archivedArticles'].items()}
    current = article_counts(v for values in state['days'].values() for v in values.values())
    for path, item in current.items():
        result = cumulative.setdefault(path, {'pageViews': 0, 'activeSeconds': 0})
        result['pageViews'] += item['pageViews']
        result['activeSeconds'] = round(result['activeSeconds'] + item['activeSeconds'], 1)
    periods = {}
    for length in (7, 30, 90):
        since = day(now - (length - 1) * DAY_MS)
        values = [v for date, visits in state['days'].items() if date >= since for v in visits.values()]
        periods[str(length)] = {**summarize(values), 'articles': article_counts(values)}
    return {'version': 1, 'startedAt': state['startedAt'], 'generatedAt': iso(now),
            'dataThrough': iso(state['watermark']), 'timeZone': 'Asia/Shanghai',
            'totals': totals, 'daily': sorted(daily, key=lambda d: d['date']),
            'periods': periods, 'articles': cumulative}


def import_logs(state, end):
    start = max(START, state['watermark'] - 15 * 60 * 1000)
    params = {'OrderBy': 'asc', 'StartTime': start, 'EndTime': end, 'Limit': 100, 'ID': PROJECT,
              'Filter': json.dumps([{'Key': 'ext1', 'Operator': 'eq', 'Value': MARKER},
                                    {'Key': 'env', 'Operator': 'eq', 'Value': 'production'}])}
    count = 0
    cursors = set()
    for _ in range(40):
        result = tencent('rum', '2021-06-22', 'DescribeRumLogDetailsV2', params)
        data = json.loads(result['Result'])
        rows = data.get('Result')
        if not isinstance(rows, list):
            raise RuntimeError('Unexpected RUM response; retaining the previous checkpoint')
        for row in rows:
            if apply_log(state, row, end + 120000):
                count += 1
        if len(rows) < 100:
            state['watermark'] = end
            return count
        last = rows[-1]
        timestamp, row_id = last.get('timestamp'), last.get('rowId')
        if timestamp is None or row_id is None:
            raise RuntimeError('RUM pagination cursor missing; retaining the previous checkpoint')
        cursor = (int(timestamp), int(row_id))
        if cursor in cursors:
            raise RuntimeError('RUM cursor did not advance')
        cursors.add(cursor)
        params.update(LastTime=cursor[0], LastRowId=cursor[1])
        time.sleep(0.06)
    raise RuntimeError('Import batch limit reached; retaining the previous checkpoint')


def main_handler(event, context):
    now = int(time.time() * 1000)
    try:
        raw, _ = cos('GET', BUCKET, STATE_KEY)
        state = json.loads(gzip.decompress(raw))
    except HTTPError as error:
        if error.code != 404:
            raise
        state = empty_state()
    accepted = import_logs(state, now - 120000)
    compact(state, now)
    snapshot = public_snapshot(state, now)
    cos('PUT', BUCKET, STATE_KEY, gzip.compress(json.dumps(state, separators=(',', ':')).encode()),
        headers={'Content-Type': 'application/gzip', 'Cache-Control': 'no-store'})
    cos('PUT', BUCKET, PUBLIC_KEY, json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')).encode(),
        headers={'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'public, max-age=60'})
    result = {'acceptedRecords': accepted, 'pageViews': snapshot['totals']['pageViews'], 'dataThrough': snapshot['dataThrough']}
    print(json.dumps(result))
    return result
