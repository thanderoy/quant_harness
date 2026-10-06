#!/usr/bin/env bash
# Copy the strategies' live state from one Docker volume to another, verified.
#
#   services/migrate_state_volume.sh FROM_VOLUME TO_VOLUME
#
# Why this exists (Phase 3 step 6, R12): the drawdown guard reads peak equity
# from a file on the state volume. If the volume changes without the files
# moving, the guard finds no peak, takes current equity as a new high, and
# hands back the whole drawdown budget -- silently. A volume changes in two
# ways here, and both need this copy:
#
#   * the T10 rename of the Compose volume key to quant_harness_state;
#   * the cutover from the WMPS stack to this repository's stack. Neither
#     Compose file sets a project name, so their volumes are already different
#     Docker volumes (prefixed by directory) whatever the key is called.
#
# Find the real names with:  docker volume ls --format '{{.Name}}' | grep state
#
# It refuses rather than guesses: a missing or empty source, a destination that
# already holds state, or any container still mounting the source (a worker
# could write mid-copy) all stop it before anything is written. Afterwards
# every file's sha256 is compared on both sides.
#
# IMAGE (default alpine:3.20) is the throwaway image used to do the copy; any
# image with sh, cp, find and sha256sum works.
set -euo pipefail

IMAGE="${IMAGE:-alpine:3.20}"

die() { echo "migrate_state_volume: $*" >&2; exit 1; }

[ "$#" -eq 2 ] || die "usage: $0 FROM_VOLUME TO_VOLUME"
FROM="$1"; TO="$2"
[ "$FROM" != "$TO" ] || die "FROM and TO are the same volume"

docker volume inspect "$FROM" >/dev/null 2>&1 \
  || die "source volume '$FROM' does not exist -- nothing to migrate from"

users="$(docker ps --filter "volume=$FROM" --format '{{.Names}}')"
[ -z "$users" ] || die "source '$FROM' is mounted by running containers: $users -- stop them first"

count() {
  docker run --rm -v "$1":/v:ro "$IMAGE" sh -c 'find /v -type f | wc -l'
}

n_from="$(count "$FROM")"
[ "$n_from" -gt 0 ] || die "source '$FROM' holds no files -- wrong volume name?"

if docker volume inspect "$TO" >/dev/null 2>&1; then
  n_to="$(count "$TO")"
  [ "$n_to" -eq 0 ] || die "destination '$TO' already holds $n_to file(s); refusing to overwrite live state"
else
  docker volume create "$TO" >/dev/null
fi

docker run --rm -v "$FROM":/from:ro -v "$TO":/to "$IMAGE" sh -c 'cp -a /from/. /to/'

sums() {
  docker run --rm -v "$1":/v:ro "$IMAGE" sh -c 'cd /v && find . -type f -exec sha256sum {} + | sort -k2'
}
a="$(sums "$FROM")"; b="$(sums "$TO")"
[ "$a" = "$b" ] || die "checksums differ after copy:
--- $FROM
$a
--- $TO
$b"

echo "migrated $n_from file(s) from $FROM to $TO, all checksums match:"
echo "$b"
