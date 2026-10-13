#!/usr/bin/env bash
# Installed as /usr/local/sbin/clucktalk-show-link. Shows the farmer link on THIS terminal only (root).
# It refuses to write to a pipe or a file, so the link does not end up in a log, a ticket or a chat by accident.
set -euo pipefail
ENV_FILE=/etc/clucktalk/pilot.env
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 2; }
[ -t 1 ] || { echo "clucktalk-show-link: output must go to the screen, not to a file or a pipe." >&2; exit 2; }
origin=$(grep -m1 '^CLUCKTALK_PUBLIC_ORIGIN=' "$ENV_FILE" | cut -d= -f2-)
token=$(grep -m1 '^CLUCKTALK_SIMULATOR_TOKENS=' "$ENV_FILE" | cut -d= -f2- | cut -d, -f1)
[ -n "$origin" ] && [ -n "$token" ] || { echo "clucktalk-show-link: the environment file has no origin or token." >&2; exit 1; }
echo "Farmer link (screen only; do not paste it into a chat, a ticket or git):"
echo "$origin/#t=$token"
