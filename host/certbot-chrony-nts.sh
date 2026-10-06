#!/bin/sh
# certbot deploy hook for the NTS server cert: copy it where the chrony container (gid 101) can
# read it, then restart chrony (it loads NTS server certificates only at start).
# Registered per certificate (see README), so certbot runs it only for that one.
set -e
repo=$(cd "$(dirname "$0")/.." && pwd)
install -d -m 750 -o root -g 101 "$repo/nts"
install -m 640 -o root -g 101 "$RENEWED_LINEAGE/fullchain.pem" "$RENEWED_LINEAGE/privkey.pem" "$repo/nts/"
cd "$repo" && docker compose restart chrony
