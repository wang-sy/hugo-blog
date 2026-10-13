"""Explicit infrastructure commands. Uses the current tccli login, never stores credentials."""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import zipfile
from urllib.error import HTTPError

from cloud import cos, tencent

ROOT = Path(__file__).resolve().parent
BUCKET = 'saiyudoc-stats-1301596189'
FUNCTION = 'saiyudoc-analytics'
ROLE = 'SaiyuDocAnalyticsRole'


def login():
    if os.environ.get('TENCENTCLOUD_SECRETID'):
        return
    credential = json.loads((Path.home() / '.tccli/default.credential').read_text())
    for key, env in [('secretId', 'TENCENTCLOUD_SECRETID'), ('secretKey', 'TENCENTCLOUD_SECRETKEY'),
                     ('token', 'TENCENTCLOUD_SESSIONTOKEN')]:
        if credential.get(key):
            os.environ[env] = credential[key]


def api(service, action, params):
    return tencent(service, {'scf': '2018-04-16', 'cam': '2019-01-16', 'rum': '2021-06-22'}[service], action, params)


def bundle():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in ('aggregate.py', 'cloud.py'):
            archive.write(ROOT / file, file)
    return base64.b64encode(output.getvalue()).decode()


def storage():
    try:
        cos('HEAD', BUCKET)
    except HTTPError as error:
        if error.code != 404:
            raise
        cos('PUT', BUCKET, headers={'x-cos-acl': 'private'})
        print('Created private analytics bucket')
    policy = {'version': '2.0', 'statement': [{'effect': 'allow', 'principal': {'qcs': ['*']},
              'action': ['name/cos:GetObject'],
              'resource': ['qcs::cos:ap-guangzhou:uid/1301596189:' + BUCKET + '/public/stats.json']}]}
    cos('PUT', BUCKET, query={'policy': ''}, data=json.dumps(policy).encode(),
        headers={'Content-Type': 'application/json'})
    cors = b'<CORSConfiguration><CORSRule><ID>PublicAggregates</ID><AllowedOrigin>*</AllowedOrigin><AllowedMethod>GET</AllowedMethod><AllowedMethod>HEAD</AllowedMethod><AllowedHeader>*</AllowedHeader><ExposeHeader>ETag</ExposeHeader><MaxAgeSeconds>600</MaxAgeSeconds></CORSRule></CORSConfiguration>'
    cos('PUT', BUCKET, query={'cors': ''}, data=cors, headers={'Content-Type': 'application/xml'})
    print('Only public/stats.json allows anonymous reads; CORS configured')


def role():
    trust = {'version': '2.0', 'statement': [{'effect': 'allow', 'action': 'name/sts:AssumeRole',
             'principal': {'service': ['scf.qcloud.com']}}]}
    try:
        result = api('cam', 'GetRole', {'RoleName': ROLE})
        print('Existing role:', result['RoleInfo']['RoleId'])
    except RuntimeError as error:
        if 'RoleNotExist' not in str(error):
            raise
        print(api('cam', 'CreateRole', {'RoleName': ROLE, 'PolicyDocument': json.dumps(trust),
                  'Description': 'Read blog RUM measurements and publish anonymous aggregate statistics', 'ConsoleLogin': 0}))
    policy = {'version': '2.0', 'statement': [
        {'effect': 'allow', 'action': ['name/rum:DescribeRumLogDetailsV2'],
         # This API explicitly checks resource '*', and does not support instance-level CAM scope.
         'resource': ['*']},
        {'effect': 'allow', 'action': ['name/cos:GetObject', 'name/cos:PutObject'],
         'resource': ['qcs::cos:ap-guangzhou:uid/1301596189:' + BUCKET + '/' + key
                      for key in ('private/state.json.gz', 'public/stats.json')]}]}
    name = 'SaiyuDocAnalyticsAccess'
    existing = api('cam', 'ListPolicies', {'Scope': 'Local', 'Keyword': name, 'Rp': 100})
    matches = [p for p in existing['List'] if p['PolicyName'] == name]
    if matches:
        policy_id = matches[0]['PolicyId']
        api('cam', 'UpdatePolicy', {'PolicyId': policy_id, 'PolicyDocument': json.dumps(policy)})
    else:
        policy_id = api('cam', 'CreatePolicy', {'PolicyName': name, 'PolicyDocument': json.dumps(policy),
                  'Description': 'Only blog RUM logs and two analytics COS objects'})['PolicyId']
    print(api('cam', 'AttachRolePolicy', {'PolicyId': policy_id, 'AttachRoleName': ROLE}))
    print('Policy ID:', policy_id)


def create_function():
    print(api('scf', 'CreateFunction', {'FunctionName': FUNCTION, 'Code': {'ZipFile': bundle()},
         'Handler': 'aggregate.main_handler', 'Runtime': 'Python3.10', 'MemorySize': 256, 'Timeout': 120,
         'Description': 'Import RUM blog measurements and publish public anonymous stats every 10 minutes',
         'Role': ROLE, 'CodeSource': 'ZipFile', 'Type': 'Event',
         'AutoCreateClsTopic': 'FALSE', 'AutoDeployClsTopicIndex': 'FALSE',
         'PublicNetConfig': {'PublicNetStatus': 'ENABLE', 'EipConfig': {'EipStatus': 'DISABLE'}},
         'Environment': {'Variables': [{'Key': 'STATS_BUCKET', 'Value': BUCKET},
                                      {'Key': 'RUM_PROJECT_ID', 'Value': '159725'}]}}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['storage', 'role', 'create', 'update', 'status', 'invoke', 'schedule'])
    args = parser.parse_args()
    login()
    if args.command == 'storage':
        storage()
    elif args.command == 'role':
        role()
    elif args.command == 'create':
        create_function()
    elif args.command == 'update':
        print(api('scf', 'UpdateFunctionCode', {'FunctionName': FUNCTION, 'ZipFile': bundle(),
                                              'Handler': 'aggregate.main_handler'}))
    elif args.command == 'status':
        result = api('scf', 'GetFunction', {'FunctionName': FUNCTION, 'ShowCode': 'FALSE'})
        print(json.dumps({k: result.get(k) for k in ('FunctionName', 'Status', 'Runtime', 'MemorySize', 'Timeout', 'Role', 'StatusDesc')}, ensure_ascii=False))
    elif args.command == 'invoke':
        print(json.dumps(api('scf', 'Invoke', {'FunctionName': FUNCTION, 'InvocationType': 'RequestResponse',
                                              'ClientContext': '{}', 'LogType': 'Tail'}), ensure_ascii=False))
    elif args.command == 'schedule':
        # Memory quota equals one invocation, preventing overlapping state updates. This does not prewarm instances.
        print(api('scf', 'PutReservedConcurrencyConfig', {'FunctionName': FUNCTION, 'ReservedConcurrencyMem': 256}))
        print(api('scf', 'CreateTrigger', {'FunctionName': FUNCTION, 'TriggerName': 'aggregate-every-10-minutes',
              'Type': 'timer', 'TriggerDesc': '0 */10 * * * * *', 'Enable': 'OPEN',
              'Description': 'Refresh public blog statistics every 10 minutes'}))


if __name__ == '__main__':
    main()
