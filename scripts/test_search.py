import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from search_common import parse_sitemap
from submit_search import baidu, indexnow, request
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

    @patch.dict(os.environ, {'BAIDU_TOKEN': 'test&token'})
    def test_baidu_site_is_literal_and_token_is_encoded(self):
        def send(url, *args):
            self.assertEqual(url, 'http://data.zz.baidu.com/urls?site=https://www.wangsaiyu.com&token=test%26token')
            return 400, b'{"error":400,"message":"site init fail"}'
        with self.assertRaisesRegex(RuntimeError, 'site init fail'):
            baidu(self.records, {}, self.state_path, send)
        self.assertFalse(self.state_path.exists())

    @patch.dict(os.environ, {'BAIDU_TOKEN': 'test-token'})
    def test_unknown_baidu_message_cannot_echo_credentials(self):
        with self.assertRaises(RuntimeError) as raised:
            baidu(self.records, {}, self.state_path,
                  lambda *args: (400, b'{"error":400,"message":"token=test-token"}'))
        self.assertNotIn('test-token', str(raised.exception))

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

    @patch('submit_search.urlopen')
    def test_network_failure_does_not_expose_credential_url(self, open_url):
        secret_url = 'http://data.zz.baidu.com/urls?token=private-test-token'
        open_url.side_effect = URLError(OSError(secret_url))
        with self.assertRaises(RuntimeError) as raised:
            request(secret_url, b'https://www.wangsaiyu.com/', 'text/plain')
        self.assertIn('OSError', str(raised.exception))
        self.assertNotIn('private-test-token', str(raised.exception))

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
