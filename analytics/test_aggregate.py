import copy
import json
import unittest
from unittest.mock import patch

import aggregate as a

NOW = a.START + 12 * 3600000


def log(visit='11111111-1111-4111-8111-111111111111', aid='browser-one', path='/posts/test/', active=5000, started=None):
    return {'env': 'production', 'ext1': a.MARKER, 'aid': aid, 'from': 'https://www.wangsaiyu.com' + path,
            'msg': json.dumps({'v': 1, 'visit': visit, 'started': NOW - 60000 if started is None else started,
                               'path': path, 'article': path.startswith('/posts/'), 'activeMs': active})}


class AggregationTests(unittest.TestCase):
    def test_heartbeats_and_reimports_are_idempotent(self):
        state = a.empty_state()
        for duration in [0, 5000, 20000, 5000, 20000]:
            self.assertTrue(a.apply_log(state, log(active=duration), NOW))
        result = a.public_snapshot(state, NOW)
        self.assertEqual(result['totals']['pageViews'], 1)
        self.assertEqual(result['totals']['activeSeconds'], 20)

    def test_unique_visitor_unions_across_domains_days_and_articles(self):
        state = a.empty_state()
        a.apply_log(state, log(), NOW)
        second = log(visit='22222222-2222-4222-8222-222222222222', started=NOW+a.DAY_MS-60000)
        second['from'] = second['from'].replace('www.', '')
        a.apply_log(state, second, NOW+a.DAY_MS)
        third = log(visit='33333333-3333-4333-8333-333333333333', path='/posts/other/', started=NOW+a.DAY_MS-60000)
        a.apply_log(state, third, NOW+a.DAY_MS)
        result = a.public_snapshot(state, NOW+a.DAY_MS)
        self.assertEqual(sum(d['uniqueVisitors'] for d in result['daily']), 2)
        self.assertEqual(result['periods']['7']['uniqueVisitors'], 1)
        self.assertEqual(result['periods']['7']['articles']['/posts/test/']['uniqueVisitors'], 1)
        self.assertEqual(result['totals']['pageViews'], 3)

    def test_invalid_logs_and_test_environment_are_rejected(self):
        baseline = log()
        samples = []
        for key, value in [('env','test'), ('ext1','other'), ('from','https://evil.example/posts/test/'), ('msg','bad json'), ('aid','')]:
            item = copy.deepcopy(baseline); item[key] = value; samples.append(item)
        for key, value in [('activeMs',-1), ('activeMs',999999999), ('started',NOW+999999), ('path','//evil.test/'), ('path','/posts/../private/'), ('visit','bad')]:
            item=copy.deepcopy(baseline); metric=json.loads(item['msg']); metric[key]=value; item['msg']=json.dumps(metric); samples.append(item)
        for item in samples:
            self.assertFalse(a.apply_log(a.empty_state(), item, NOW), item)

    def test_chinese_paths_and_beijing_day_boundary(self):
        self.assertEqual(a.safe_path('/posts/%E4%BD%A0%E5%A5%BD/'), '/posts/你好/')
        self.assertEqual(a.day(a.START-1), '2026-10-12')
        self.assertEqual(a.day(a.START), '2026-10-13')

    def test_legacy_archive_articles_are_counted(self):
        state=a.empty_state(); row=log(path='/archives/leveldbwriteop/')
        metric=json.loads(row['msg']); metric['article']=True; row['msg']=json.dumps(metric)
        a.apply_log(state,row,NOW)
        self.assertEqual(a.public_snapshot(state,NOW)['totals']['articleViews'],1)

    def test_archive_preserves_totals_and_removes_visitor_details(self):
        state = a.empty_state()
        a.apply_log(state, log(), NOW)
        before = a.public_snapshot(state, NOW)
        later = NOW + 100 * a.DAY_MS
        a.compact(state, later)
        after = a.public_snapshot(state, later)
        self.assertEqual(before['totals'], after['totals'])
        self.assertEqual(before['articles'], after['articles'])
        self.assertEqual(state['days'], {})
        self.assertEqual(after['periods']['90']['pageViews'], 0)
        self.assertFalse(a.apply_log(state, log(), later))

    def test_public_data_never_contains_private_identifiers(self):
        state = a.empty_state(); a.apply_log(state, log(), NOW)
        snapshot = json.dumps(a.public_snapshot(state, NOW))
        for forbidden in [state['salt'], 'browser-one', '11111111-1111', '"salt"', '"aid"', '"ip"']:
            self.assertNotIn(forbidden, snapshot)

    def test_failed_import_does_not_advance_checkpoint(self):
        state=a.empty_state()
        with patch.object(a, 'tencent', return_value={'Result': '{"oops": []}'}), self.assertRaises(RuntimeError):
            a.import_logs(state, NOW)
        self.assertEqual(state['watermark'], a.START)

    def test_pagination_import_and_empty_final_page(self):
        state=a.empty_state()
        rows=[{**log(), 'timestamp':NOW-60000, 'rowId':n} for n in range(100)]
        with patch.object(a, 'tencent', side_effect=[{'Result':json.dumps({'Result':rows})},{'Result':'{"Result":[]}'}]) as call:
            a.import_logs(state,NOW)
        self.assertEqual(state['watermark'],NOW)
        self.assertEqual(call.call_args[0][3]['LastRowId'],99)
        self.assertEqual(a.public_snapshot(state,NOW)['totals']['pageViews'],1)


if __name__ == '__main__':
    unittest.main()
