import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from search_common import parse_sitemap
from submit_search import baidu, indexnow
from verify_search import validate_page


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state_path = self.root / 'state.json'
        self.records = [{'url': 'https://www.wangsaiyu.com/posts/a/', 'hash': 'aaa'},
                        {'url': 'https://www.wangsaiyu.com/posts/b/', 'hash': 'bbb'}]

    def tearDown(self):
        self.tmp.cleanup()

    @patch.dict(os.environ, {'BAIDU_TOKEN': 'test-token'})
    def test_quota_keeps_unsubmitted_urls_pending(self):
        state, calls = {}, []
        def send(url, body, content_type):
            calls.append(body)
            return 400, b'{"error":400,"message":"over quota"}'
        self.assertEqual(baidu(self.records, state, self.state_path, send), (0, 'quota'))
        self.assertEqual(state, {})
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.state_path.exists())

    @patch.dict(os.environ, {'BAIDU_TOKEN': 'test-token'})
    def test_quota_after_success_preserves_only_acknowledged_url(self):
        state = {}
        result = baidu(self.records, state, self.state_path,
                       lambda *args: (200, b'{"success":1,"remain":0}'))
        self.assertEqual(result, (1, 'quota'))
        self.assertEqual(json.loads(self.state_path.read_text()), {self.records[0]['url']: 'aaa'})

    @patch.dict(os.environ, {'BAIDU_TOKEN': 'test-token'})
    def test_api_error_with_http_200_is_not_success(self):
        with self.assertRaises(RuntimeError):
            baidu(self.records, {}, self.state_path,
                  lambda *args: (200, b'{"error":401,"message":"invalid token"}'))
        self.assertFalse(self.state_path.exists())

    def test_indexnow_202_is_pending_verification_not_indexed(self):
        (self.root / 'indexnow-key.txt').write_text('a' * 32)
        result = indexnow(self.records, {}, self.state_path, self.root,
                          lambda *args: (202, b''))
        self.assertEqual(result, (2, 'verification_pending'))

    def test_indexnow_failure_does_not_acknowledge_urls(self):
        (self.root / 'indexnow-key.txt').write_text('a' * 32)
        with self.assertRaises(RuntimeError):
            indexnow(self.records, {}, self.state_path, self.root,
                     lambda *args: (403, b''))
        self.assertFalse(self.state_path.exists())

    def test_sitemap_rejects_external_duplicate_and_query_urls(self):
        template = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{}</urlset>'
        for url in ['https://example.com/', 'http://www.wangsaiyu.com/',
                    'https://www.wangsaiyu.com/?secret=x']:
            with self.assertRaises(ValueError):
                parse_sitemap(template.format('<url><loc>' + url + '</loc></url>'))
        row = '<url><loc>https://www.wangsaiyu.com/</loc></url>'
        with self.assertRaises(ValueError):
            parse_sitemap(template.format(row + row))

    def test_noindex_and_redirects_fail_release_validation(self):
        html = '<title>Article</title><link rel="canonical" href="https://www.wangsaiyu.com/"><meta name="description" content="Description">'
        for extra in ['<meta name="robots" content="noindex">', '<meta http-equiv="refresh" content="0;url=/">']:
            with self.assertRaises(AssertionError):
                validate_page(html + extra, 'https://www.wangsaiyu.com/')


if __name__ == '__main__':
    unittest.main()
