"""Upload an encrypted pg_dump using the dedicated write-only backup identity."""
import json
import os
from pathlib import Path
import sys
from cloud import cos

config = json.loads(Path('/opt/saiyudoc-umami/backup-credentials.json').read_text())
os.environ['TENCENTCLOUD_SECRETID'] = config['SecretId']
os.environ['TENCENTCLOUD_SECRETKEY'] = config['SecretKey']
source = Path(sys.argv[1])
cos('PUT', 'saiyudoc-stats-1301596189', 'private/umami-backups/' + source.name,
    source.read_bytes(), headers={'Content-Type': 'application/octet-stream'})
print('Offsite backup uploaded:', source.name)
