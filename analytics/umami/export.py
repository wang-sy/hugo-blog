"""Publish aggregate article counts and deduplicated foreground time from Umami.

Runs once per minute on the analytics host. No public database/API credentials.
SQL is fixed; no browser-controlled query reaches PostgreSQL.
"""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import uuid


def export(website_id, directory):
    website_id = str(uuid.UUID(website_id))
    sql = """
BEGIN READ ONLY;
SET LOCAL statement_timeout = '45s';
WITH views AS (
  SELECT url_path AS path, session_id, created_at
  FROM website_event
  WHERE website_id = '%s' AND event_type = 1 AND hostname = 'www.wangsaiyu.com'
), readings AS (
  SELECT e.url_path AS path, e.session_id, rid.string_value AS read_id,
         min(e.created_at) AS started,
         least(14400000, greatest(0, max(ms.number_value))) / 1000.0 AS seconds
  FROM website_event e
  JOIN event_data rid ON rid.website_event_id = e.event_id AND rid.data_key = 'read_id'
  JOIN event_data ms ON ms.website_event_id = e.event_id AND ms.data_key = 'active_ms'
  WHERE e.website_id = '%s' AND (e.event_name = 'blog_read' OR e.event_type = 1)
    AND e.hostname = 'www.wangsaiyu.com'
    AND rid.string_value ~ '^[0-9a-f-]{36}$'
  GROUP BY e.url_path, e.session_id, rid.string_value
), periods AS (
  SELECT days, (date_trunc('day', now() AT TIME ZONE 'Asia/Shanghai')
    - (days - 1) * interval '1 day') AT TIME ZONE 'Asia/Shanghai' AS since
  FROM (VALUES (7), (30), (90)) n(days)
), totals AS (
  SELECT path, count(*) AS "pageViews" FROM views GROUP BY path
), pv AS (
  SELECT p.days, v.path, count(*) AS pv, count(DISTINCT v.session_id) AS uv
  FROM periods p JOIN views v ON v.created_at >= p.since GROUP BY p.days, v.path
), active AS (
  SELECT p.days, r.path, sum(seconds) AS seconds, count(*) AS samples
  FROM periods p JOIN readings r ON r.started >= p.since GROUP BY p.days, r.path
), items AS (
  SELECT pv.days, pv.path, json_build_object('pageViews',pv.pv,'uniqueVisitors',pv.uv,
    'activeSeconds',round(coalesce(a.seconds,0)),
    'averageSeconds',round(coalesce(a.seconds,0)/pv.pv),
    'timedVisits',coalesce(a.samples,0)) AS metrics
  FROM pv LEFT JOIN active a ON a.days=pv.days AND a.path=pv.path
)
SELECT json_build_object('articles', coalesce((SELECT json_object_agg(path,
  json_build_object('pageViews',"pageViews")) FROM totals),'{}'::json),
  'periods', (SELECT json_object_agg(days, paths) FROM (
    SELECT p.days, coalesce(json_object_agg(i.path,i.metrics)
      FILTER (WHERE i.path IS NOT NULL),'{}'::json) AS paths
    FROM periods p LEFT JOIN items i USING(days) GROUP BY p.days) q));
COMMIT;
""" % (website_id, website_id)
    result = subprocess.run(
        ['docker', 'compose', 'exec', '-T', 'db', 'psql', '-X', '-qAt',
         '-v', 'ON_ERROR_STOP=1', '-U', 'umami', '-d', 'umami'],
        input=sql, text=True, capture_output=True, check=True, timeout=55)
    data = json.loads(result.stdout)
    data.update(version=2, generatedAt=dt.datetime.now(dt.timezone.utc).isoformat(),
                timezone='Asia/Shanghai', source='Umami')
    target = Path(directory) / 'articles.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    temporary.chmod(0o644)
    os.replace(temporary, target)


if __name__ == '__main__':
    config = json.loads(Path('/opt/saiyudoc-umami/site.json').read_text())
    os.chdir('/opt/saiyudoc-umami')
    export(config['websiteId'], '/var/www/umami-public')
