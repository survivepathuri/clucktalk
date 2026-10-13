#!/usr/bin/env bash
# Installed as /usr/local/sbin/clucktalk-rotate-token. Replaces the farmer's token (the old link stops working at
# once) and restarts the app. With --mcp it also replaces the Simulator-to-MCP token. Prints no token.
set -euo pipefail
ENV_FILE=/etc/clucktalk/pilot.env
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 2; }
WHICH="CLUCKTALK_SIMULATOR_TOKENS"
case "${1:-}" in
  "") ;;
  --mcp) WHICH="CLUCKTALK_AUTH_TOKEN" ;;
  *) echo "usage: clucktalk-rotate-token [--mcp]" >&2; exit 2 ;;
esac
python3 - "$ENV_FILE" "$WHICH" <<'PYEOF'
import os, secrets, sys, tempfile
path, name = sys.argv[1], sys.argv[2]
lines = open(path, encoding="utf-8").read().splitlines()
hit = False
for i, line in enumerate(lines):
    if line.startswith(name + "="):
        lines[i] = f"{name}={secrets.token_urlsafe(32)}"
        hit = True
if not hit:
    sys.exit(f"rotate-token: {name} is not in {path}")
st = os.stat(path)
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
os.chmod(tmp, st.st_mode & 0o777)
os.chown(tmp, st.st_uid, st.st_gid)
os.replace(tmp, path)
PYEOF
systemctl restart clucktalk-pilot.service
echo "rotate-token: $WHICH replaced and the app restarted."
[ "$WHICH" = "CLUCKTALK_SIMULATOR_TOKENS" ] && echo "Show the new link on this terminal with:  sudo clucktalk-show-link"
exit 0
