#!/usr/bin/env bash
# Owner-initiated, pinned Daily deployment. Never run this on a public endpoint.
set -Eeuo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo 'Usage: deploy-daily.sh <verified 40-character merge commit SHA>' >&2
  exit 2
fi
if [[ "$(id -u)" -ne 0 ]]; then
  echo 'Run from the existing Hetzner root SSH session.' >&2
  exit 2
fi

SHA="$1"
SHORT="${SHA:0:8}"
SRC="/opt/agency-releases/$SHA"
IMAGE="agency-daily:release-$SHORT"
CONTAINER="agency-daily-daily-1"

echo '[1/5] Identify the existing Daily Compose stack'
FILES="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$CONTAINER")"
if [[ -z "$FILES" || "$FILES" == '<no value>' ]]; then
  echo 'Running container does not expose its Compose configuration.' >&2
  exit 1
fi

IFS=',' read -r -a CONFIG_PATHS <<< "$FILES"
COMPOSE=(docker compose -p agency-daily)
for file in "${CONFIG_PATHS[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Compose configuration missing: $file" >&2
    exit 1
  fi
  COMPOSE+=(-f "$file")
done
"${COMPOSE[@]}" config --quiet

DATA="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$CONTAINER")"
if [[ -z "$DATA" || ! -f "$DATA/daily.sqlite3" ]]; then
  echo 'Could not verify the existing mounted SQLite database.' >&2
  exit 1
fi
PRIVATE="$(dirname "$DATA")"
OLD_ID="$(docker inspect -f '{{.Image}}' "$CONTAINER")"
docker image inspect "$OLD_ID" >/dev/null

echo '[2/5] Build the exact merged revision'
mkdir -p /opt/agency-releases
if [[ ! -e "$SRC" ]]; then
  git clone --no-checkout https://github.com/Stoqnist/chatgpt-library.git "$SRC"
  git -C "$SRC" checkout --detach "$SHA"
fi
test "$(git -C "$SRC" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$SRC" status --porcelain)"
docker build -t "$IMAGE" "$SRC/daily"

echo '[3/5] Verify and back up private state'
DIR="$(mktemp -d "$PRIVATE/release-${SHORT}-XXXXXXXX")"
python3 - "$DATA/daily.sqlite3" "$DIR/daily.sqlite3" <<'PY'
import sqlite3
import sys
from pathlib import Path

path = Path(sys.argv[1])
with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as source:
    for table in ('runs', 'chat_turns'):
        active = source.execute(
            f"SELECT count(*) FROM {table} WHERE status='running'"
        ).fetchone()[0]
        if active:
            raise SystemExit('A Daily request is still running; finish it and retry.')
    with sqlite3.connect(sys.argv[2]) as backup:
        source.backup(backup)
        if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SystemExit('Database backup failed integrity verification.')
PY
chmod 600 "$DIR/daily.sqlite3"

# Preserve the previous immutable image even if its old tag is moved.
ROLLBACK_IMAGE="agency-daily:rollback-before-$SHORT"
docker image tag "$OLD_ID" "$ROLLBACK_IMAGE"
printf 'services:\n  daily:\n    image: %s\n' "$IMAGE" > "$DIR/release.yaml"
printf 'services:\n  daily:\n    image: %s\n' "$ROLLBACK_IMAGE" > "$DIR/rollback.yaml"
{
  printf '#!/usr/bin/env bash\nset -Eeuo pipefail\n'
  printf '%q ' "${COMPOSE[@]}" -f "$DIR/rollback.yaml" \
    up -d --no-build --no-deps --wait --wait-timeout 120 daily
  printf '\n'
} > "$DIR/rollback.sh"
chmod 700 "$DIR/rollback.sh"

"${COMPOSE[@]}" -f "$DIR/release.yaml" config --quiet

rollback() {
  result=$?
  trap - ERR
  echo 'Verification failed. Restoring the previous service image.' >&2
  if ! bash "$DIR/rollback.sh"; then
    echo "Automatic rollback also failed; run: bash $DIR/rollback.sh" >&2
  fi
  echo "Verified backup retained: $DIR/daily.sqlite3" >&2
  exit "$result"
}
trap rollback ERR

echo '[4/5] Recreate only the Daily service'
"${COMPOSE[@]}" -f "$DIR/release.yaml" \
  up -d --no-build --no-deps --wait --wait-timeout 120 daily

echo '[5/5] Check health, proxy and private authentication'
curl -fsS --max-time 15 http://127.0.0.1:18001/health >/dev/null
curl -fsS --max-time 15 http://127.0.0.1:8092/daily/ >/dev/null
for port in 18001 8092; do
  status="$(curl -sS --max-time 15 -o /dev/null \
    -w '%{http_code}' "http://127.0.0.1:$port/daily/api/state")"
  test "$status" = 401
done
test "$(docker inspect -f '{{.Image}}' "$CONTAINER")" = \
  "$(docker image inspect -f '{{.Id}}' "$IMAGE")"

trap - ERR
printf '\nDEPLOYMENT SUCCESSFUL\nRelease: %s\nBackup: %s/daily.sqlite3\nRollback: bash %s/rollback.sh\n' \
  "$SHA" "$DIR" "$DIR"
