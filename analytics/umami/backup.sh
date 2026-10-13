#!/bin/sh
set -eu
umask 077
cd /opt/saiyudoc-umami
mkdir -p /var/backups/saiyudoc-umami
backup="/var/backups/saiyudoc-umami/umami-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T db pg_dump -U umami -d umami -Fc > "$backup.tmp"
test -s "$backup.tmp"
mv "$backup.tmp" "$backup"
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
  -pass file:/opt/saiyudoc-umami/backup.key -in "$backup" -out "$backup.enc"
python3 /opt/saiyudoc-umami/backup_upload.py "$backup.enc"
# Local dumps: 7 days. COS automatically expires encrypted copies after 30 days.
find /var/backups/saiyudoc-umami -name '*.dump' -mtime +7 -delete
find /var/backups/saiyudoc-umami -name '*.enc' -mtime +7 -delete
