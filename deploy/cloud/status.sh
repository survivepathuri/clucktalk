#!/usr/bin/env bash
# Installed as /usr/local/sbin/clucktalk-status. One screen: is it up, is HTTPS configured, is the last backup good.
# Prints no token and no farmer data.
set -uo pipefail
echo "== services"
for u in clucktalk-pilot.service caddy.service clucktalk-backup.timer; do
  printf '%-28s %s\n' "$u" "$(systemctl is-active "$u" 2>&1)"
done
echo "== health (local)"
curl -sS --max-time 5 http://127.0.0.1:8766/healthz || echo "no answer on 127.0.0.1:8766"
echo
echo "== public origin"
grep -m1 '^CLUCKTALK_PUBLIC_ORIGIN=' /etc/clucktalk/pilot.env 2>/dev/null | cut -d= -f2- || echo "(no environment file)"
echo "== farm file"
if [ -e /var/lib/clucktalk-pilot/FARM_FILE_IS_EXAMPLE ]; then echo "WARNING: pilot_farm.json is still the EXAMPLE (fictional houses)"; else echo "farmer's own file in place"; fi
echo "== backups (newest 3) and last good stamp"
ls -1t /var/backups/clucktalk-pilot/pilot_state_*.sqlite3 2>/dev/null | head -3
cat /var/backups/clucktalk-pilot/LAST_GOOD_BACKUP 2>/dev/null || echo "no LAST_GOOD_BACKUP yet"
systemctl list-timers clucktalk-backup.timer --no-pager 2>/dev/null | sed -n 1,3p
echo "== disk"
df -h / | tail -1
[ -f /var/run/reboot-required ] && echo "NOTE: a reboot is pending (security updates)."
exit 0
