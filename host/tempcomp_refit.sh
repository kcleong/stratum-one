#!/bin/sh
# Refit chrony-tempcomp.points from the last 30 days and apply it after confirmation.
# Run from the repo root: host/tempcomp_refit.sh [extra tempcomp_fit.py args, e.g. --since ...]
# Applying restarts chronyd (~4 NTP pool points), so it asks first.
set -eu

points=chrony-tempcomp.points
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

docker compose exec -T chrony cat /var/lib/chrony/tempcomp.log > "$tmp/tempcomp.log"
cp "$points" "$tmp/new.points"
python3 host/tempcomp_fit.py --minutes 43200 --comp-log "$tmp/tempcomp.log" -o "$tmp/new.points" "$@"

if diff -u "$points" "$tmp/new.points"; then
    echo "No change."
    exit 0
fi
printf 'Apply and restart chrony? [y/N] '
read -r answer
[ "$answer" = y ] || exit 0
cp "$tmp/new.points" "$points"
docker compose up -d --force-recreate chrony
echo "Applied. Commit $points when chronyd shows PPS again (chronyc sources)."
