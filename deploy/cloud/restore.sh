#!/usr/bin/env bash
# Installed as /usr/local/sbin/clucktalk-restore. Restores the pilot's state from a backup file.
#   sudo clucktalk-restore /var/backups/clucktalk-pilot/pilot_state_YYYYMMDD-HHMMSS.sqlite3
# 1) restore_test.py checks the backup (integrity, schema, opens in the app) without touching live data;
# 2) the app is stopped; 3) the current state is kept next to it as *.before-restore-*; 4) the backup is put in place;
# 5) the app is started again. Nothing is deleted.
set -euo pipefail
BACKUP_DIR=/var/backups/clucktalk-pilot
STATE=/var/lib/clucktalk-pilot/state/pilot_state.sqlite3
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 2; }
[ $# -eq 1 ] || { echo "usage: clucktalk-restore BACKUP_FILE" >&2; exit 2; }
SRC=$(realpath -e "$1")
case "$SRC" in "$BACKUP_DIR"/pilot_state_*.sqlite3) ;; *) echo "restore: the file must be one of $BACKUP_DIR/pilot_state_*.sqlite3" >&2; exit 2 ;; esac
sudo -u clucktalk-pilot env PYTHONDONTWRITEBYTECODE=1 /opt/clucktalk/.venv/bin/python /opt/clucktalk/deploy/restore_test.py --backup "$SRC"
systemctl stop clucktalk-pilot.service
stamp=$(date -u +%Y%m%d-%H%M%S)
if [ -f "$STATE" ]; then mv "$STATE" "${STATE%.sqlite3}.before-restore-$stamp.sqlite3.old"; fi
rm -f "$STATE-wal" "$STATE-shm"
install -o clucktalk-pilot -g clucktalk-pilot -m 600 "$SRC" "$STATE"
systemctl start clucktalk-pilot.service
echo "restore: done. The previous state is kept as ${STATE%.sqlite3}.before-restore-$stamp.sqlite3.old"
