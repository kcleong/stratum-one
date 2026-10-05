#!/bin/sh
# certbot deploy hook: copy the renewed ntp.example.org cert where the chrony container (gid 101)
# can read it, then restart chrony (it loads NTS server certificates only at start).
set -e
case "$RENEWED_LINEAGE" in */ntp.example.org) ;; *) exit 0 ;; esac
d=/home/leong/stratum_one/nts
install -d -m 750 -o root -g 101 "$d"
install -m 640 -o root -g 101 "$RENEWED_LINEAGE/fullchain.pem" "$RENEWED_LINEAGE/privkey.pem" "$d/"
cd /home/leong/stratum_one && docker compose restart chrony
