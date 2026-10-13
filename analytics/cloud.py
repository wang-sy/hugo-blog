"""Small, dependency-free Tencent API client. Credentials never enter public files."""
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


def credentials():
    return (os.environ['TENCENTCLOUD_SECRETID'],
            os.environ['TENCENTCLOUD_SECRETKEY'],
            os.environ.get('TENCENTCLOUD_SESSIONTOKEN', ''))


def digest(key, value, algorithm='sha256'):
    return hmac.new(key, value.encode(), algorithm).digest()


def request(method, url, data=None, headers=None):
    for attempt in range(3):
        try:
            with urlopen(Request(url, data=data, headers=headers or {}, method=method), timeout=15) as response:
                return response.read(), dict(response.headers)
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            time.sleep(0.3 * (2 ** attempt))


def tencent(service, version, action, params, region='ap-guangzhou'):
    secret_id, secret_key, token = credentials()
    timestamp = int(time.time())
    date = datetime.fromtimestamp(timestamp, timezone.utc).strftime('%Y-%m-%d')
    host = service + '.tencentcloudapi.com'
    payload = json.dumps(params, separators=(',', ':')).encode()
    canonical = 'POST\n/\n\ncontent-type:application/json\nhost:' + host + '\n\ncontent-type;host\n' + hashlib.sha256(payload).hexdigest()
    scope = date + '/' + service + '/tc3_request'
    message = 'TC3-HMAC-SHA256\n' + str(timestamp) + '\n' + scope + '\n' + hashlib.sha256(canonical.encode()).hexdigest()
    signing_key = digest(digest(digest(('TC3' + secret_key).encode(), date), service), 'tc3_request')
    signature = digest(signing_key, message).hex()
    headers = {'Content-Type': 'application/json', 'Host': host,
               'X-TC-Action': action, 'X-TC-Version': version,
               'X-TC-Region': region, 'X-TC-Timestamp': str(timestamp),
               'Authorization': 'TC3-HMAC-SHA256 Credential=' + secret_id + '/' + scope + ', SignedHeaders=content-type;host, Signature=' + signature}
    if token:
        headers['X-TC-Token'] = token
    raw, _ = request('POST', 'https://' + host, payload, headers)
    result = json.loads(raw)['Response']
    if 'Error' in result:
        raise RuntimeError(action + ': ' + result['Error']['Code'] + ': ' + result['Error']['Message'])
    return result


def cos(method, bucket, key='', data=None, query=None, headers=None, region='ap-guangzhou'):
    secret_id, secret_key, token = credentials()
    host = bucket + '.cos.' + region + '.myqcloud.com'
    path = '/' + quote(key, safe='/-_.~')
    query = query or {}
    signed = {'host': host, **{k.lower(): str(v) for k, v in (headers or {}).items()}}
    if data is not None:
        signed['content-md5'] = base64.b64encode(hashlib.md5(data).digest()).decode()
    if token:
        signed['x-cos-security-token'] = token
    encode = lambda value: quote(str(value), safe='-_.~')
    canonical_query = '&'.join(encode(k.lower()) + '=' + encode(v) for k, v in sorted(query.items()))
    canonical_headers = '&'.join(encode(k) + '=' + encode(v) for k, v in sorted(signed.items()))
    key_time = str(int(time.time()) - 60) + ';' + str(int(time.time()) + 900)
    canonical = method.lower() + '\n' + path + '\n' + canonical_query + '\n' + canonical_headers + '\n'
    message = 'sha1\n' + key_time + '\n' + hashlib.sha1(canonical.encode()).hexdigest() + '\n'
    signing_key = digest(secret_key.encode(), key_time, 'sha1').hex().encode()
    signature = digest(signing_key, message, 'sha1').hex()
    signed['authorization'] = ('q-sign-algorithm=sha1&q-ak=' + secret_id + '&q-sign-time=' + key_time +
        '&q-key-time=' + key_time + '&q-header-list=' + ';'.join(sorted(signed)) +
        '&q-url-param-list=' + ';'.join(sorted(query)) + '&q-signature=' + signature)
    url = 'https://' + host + path + ('?' + urlencode(query) if query else '')
    return request(method, url, data, signed)
