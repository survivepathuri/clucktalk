#!/usr/bin/env bash
# CluckTalk cloud pilot: idempotent server setup for Ubuntu 22.04 / 24.04. Run as root (deploy.ps1 does this over ssh).
#
#   sudo bash bootstrap.sh --bundle /tmp/clucktalk-stage/bundle.tar.gz --host 203-0-113-10.sslip.io [--farm-file FILE]
#
# Safe to run twice: packages are installed only when missing, the app is replaced in place, an existing
# /etc/clucktalk/pilot.env keeps its tokens (only the public origin line may change), and nothing is deleted
# except the previous copy of the app code. It prints no token. The farmer link is shown only by show-link.sh.
set -euo pipefail

BUNDLE=""
HOST=""
FARM_FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --bundle) BUNDLE="${2:-}"; shift 2 ;;
    --host) HOST="${2:-}"; shift 2 ;;
    --farm-file) FARM_FILE="${2:-}"; shift 2 ;;
    *) echo "bootstrap: unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ "$(id -u)" -eq 0 ] || { echo "bootstrap: run as root (sudo)." >&2; exit 2; }
[ -f "$BUNDLE" ] || { echo "bootstrap: --bundle FILE is required and must exist." >&2; exit 2; }
# A hostname built from the static IP, e.g. 203-0-113-10.sslip.io (lowercase letters, digits, dots, hyphens only).
[[ "$HOST" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || { echo "bootstrap: --host must be a lowercase hostname." >&2; exit 2; }

# Refuse to start if no SSH public key is installed: key-only SSH below would lock the owner out.
if ! grep -qsE '^(ssh-|ecdsa-|sk-)' /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys; then
  echo "bootstrap: no SSH public key found in authorized_keys; nothing was changed." >&2
  exit 1
fi

APP_DIR=/opt/clucktalk
APP_USER=clucktalk-pilot
STATE_DIR=/var/lib/clucktalk-pilot
BACKUP_DIR=/var/backups/clucktalk-pilot
ENV_DIR=/etc/clucktalk
ENV_FILE=$ENV_DIR/pilot.env
STAGE=$(dirname "$BUNDLE")
HERE=$(mktemp -d /tmp/clucktalk-unpack.XXXXXX)
trap 'rm -rf "$HERE"' EXIT

log() { echo "bootstrap: $*"; }

# ---------------------------------------------------------------- 1. packages
. /etc/os-release
export DEBIAN_FRONTEND=noninteractive
log "ubuntu ${VERSION_ID:-unknown}"
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg ufw unattended-upgrades sqlite3

# Python 3.12 or newer (the project needs >= 3.12). 24.04 ships 3.12; 22.04 gets it from the deadsnakes PPA.
PYTHON=""
for candidate in python3.13 python3.12; do
  if command -v "$candidate" >/dev/null 2>&1; then PYTHON=$candidate; break; fi
done
if [ -z "$PYTHON" ]; then
  if [ "${VERSION_ID:-}" = "22.04" ]; then
    log "adding the deadsnakes PPA for Python 3.12 (Ubuntu 22.04 ships 3.10)"
    apt-get install -y -qq software-properties-common
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -qq
    apt-get install -y -qq python3.12 python3.12-venv
    PYTHON=python3.12
  else
    apt-get install -y -qq python3 python3-venv
    PYTHON=python3
  fi
fi
apt-get install -y -qq "$(basename "$PYTHON")-venv" 2>/dev/null || apt-get install -y -qq python3-venv
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
  || { echo "bootstrap: Python 3.12 or newer is required; found $("$PYTHON" --version)." >&2; exit 1; }

# Caddy from its official apt repository (automatic HTTPS).
if ! command -v caddy >/dev/null 2>&1; then
  log "installing Caddy from the official Caddy apt repository"
  install -d -m 755 /usr/share/keyrings
  curl -fsSL 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -fsSL 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' -o /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq
  apt-get install -y -qq caddy
fi

# ---------------------------------------------------------------- 2. users and folders
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --home "$STATE_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
install -d -o "$APP_USER" -g "$APP_USER" -m 700 "$STATE_DIR" "$STATE_DIR/state"
install -d -o "$APP_USER" -g "$APP_USER" -m 700 "$BACKUP_DIR"
install -d -o root -g "$APP_USER" -m 750 "$ENV_DIR"

# ---------------------------------------------------------------- 3. the app (code is root-owned: the service cannot change it)
tar -xzf "$BUNDLE" -C "$HERE"
[ -f "$HERE/requirements.txt" ] && [ -f "$HERE/scripts/run_instance.py" ] || { echo "bootstrap: the bundle is incomplete." >&2; exit 1; }
install -d -m 755 "$APP_DIR"
# Replace the code, keep the virtual environment (so a re-run does not reinstall everything).
find "$APP_DIR" -mindepth 1 -maxdepth 1 ! -name .venv -exec rm -rf {} +
cp -a "$HERE"/. "$APP_DIR"/
chown -R root:root "$APP_DIR"
chmod -R go-w "$APP_DIR"
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
  log "creating the virtual environment"
  "$PYTHON" -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/python" -m pip install --quiet --disable-pip-version-check --require-virtualenv -r "$APP_DIR/requirements.txt"
chmod -R go-w "$APP_DIR/.venv"

# ---------------------------------------------------------------- 4. farm file
FARM_PATH=$STATE_DIR/pilot_farm.json
if [ -n "$FARM_FILE" ]; then
  [ -f "$FARM_FILE" ] || { echo "bootstrap: --farm-file does not exist." >&2; exit 1; }
  install -o "$APP_USER" -g "$APP_USER" -m 600 "$FARM_FILE" "$FARM_PATH"
  rm -f "$STATE_DIR/FARM_FILE_IS_EXAMPLE"
  log "installed the farmer's farm file"
elif [ ! -f "$FARM_PATH" ]; then
  install -o "$APP_USER" -g "$APP_USER" -m 600 "$APP_DIR/docs/pilot_farm.example.json" "$FARM_PATH"
  : > "$STATE_DIR/FARM_FILE_IS_EXAMPLE"
  chown "$APP_USER:$APP_USER" "$STATE_DIR/FARM_FILE_IS_EXAMPLE"
  log "WARNING: pilot_farm.json is the EXAMPLE (fictional houses). Put the farmer's real houses in it before sending the link (docs/CLOUD_PILOT.md)."
fi

# ---------------------------------------------------------------- 5. environment file (tokens are made here, once, on the server)
newtoken() { "$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(32))'; }
if [ ! -f "$ENV_FILE" ]; then
  log "creating $ENV_FILE with two new random tokens (not printed)"
  ( umask 077
  cat > "$ENV_FILE" <<EOF
# Created by deploy/cloud/bootstrap.sh. Root-only secrets: never copy this file into a chat, a ticket or git.
CLUCKTALK_MODE=pilot
MOCK_BEDROCK=true
CLUCKTALK_INSTANCE_NAME=pilot
CLUCKTALK_PORT=8765
CLUCKTALK_SIMULATOR_PORT=8766
CLUCKTALK_PUBLIC_ORIGIN=https://$HOST
CLUCKTALK_SIMULATOR_TOKENS=$(newtoken)
CLUCKTALK_AUTH_TOKEN=$(newtoken)
CLUCKTALK_STATE_PATH=$STATE_DIR/state/pilot_state.sqlite3
CLUCKTALK_PILOT_FARM_PATH=$FARM_PATH
CLUCKTALK_DAILY_DEATHS_RULE_PATH=$STATE_DIR/daily_deaths_rule.json
CLUCKTALK_USAGE_PATH=$STATE_DIR/state/usage_pilot.json
CLUCKTALK_DISABLED_FILE=$STATE_DIR/state/DISABLED
CLUCKTALK_RATE_PER_MINUTE=60
CLUCKTALK_MAX_SESSIONS=5
PYTHONDONTWRITEBYTECODE=1
EOF
  )
else
  # Existing file: tokens stay. Only the public origin follows the hostname.
  if ! grep -qx "CLUCKTALK_PUBLIC_ORIGIN=https://$HOST" "$ENV_FILE"; then
    log "updating CLUCKTALK_PUBLIC_ORIGIN in $ENV_FILE"
    sed -i "s|^CLUCKTALK_PUBLIC_ORIGIN=.*|CLUCKTALK_PUBLIC_ORIGIN=https://$HOST|" "$ENV_FILE"
  fi
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

# ---------------------------------------------------------------- 6. systemd units, Caddy, helper commands
install -m 644 "$APP_DIR/deploy/cloud/clucktalk-pilot.service" /etc/systemd/system/clucktalk-pilot.service
install -m 644 "$APP_DIR/deploy/cloud/clucktalk-backup.service" /etc/systemd/system/clucktalk-backup.service
install -m 644 "$APP_DIR/deploy/cloud/clucktalk-backup.timer" /etc/systemd/system/clucktalk-backup.timer

# Caddyfile from the template: the only substitution is the hostname.
sed "s|@HOST@|$HOST|g" "$APP_DIR/deploy/cloud/Caddyfile.cloud.template" > /etc/caddy/Caddyfile
chmod 644 /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null

for tool in show-link.sh rotate-token.sh restore.sh status.sh; do
  install -m 750 -o root -g root "$APP_DIR/deploy/cloud/$tool" "/usr/local/sbin/clucktalk-${tool%.sh}"
done

# ---------------------------------------------------------------- 7. journald limits, unattended upgrades, ssh, firewall
install -d -m 755 /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/clucktalk.conf <<'EOF'
[Journal]
SystemMaxUse=200M
MaxRetentionSec=30day
EOF
systemctl restart systemd-journald

cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

# SSH: key-only (the check at the top already made sure a key exists, so this cannot lock the owner out).
cat > /etc/ssh/sshd_config.d/00-clucktalk-hardening.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
sshd -t
systemctl reload ssh 2>/dev/null || systemctl reload sshd

ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
# Plain allow, not "ufw limit": limit blocks an address that opens 6 connections in 30 s, which deploy.ps1 and verify.ps1
# do (found on the first real run). SSH is key-only; restrict port 22 to your own IP in the Lightsail firewall instead.
ufw delete limit 22/tcp >/dev/null 2>&1 || true
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

# ---------------------------------------------------------------- 8. start
systemctl daemon-reload
systemctl enable --now clucktalk-pilot.service
systemctl restart clucktalk-pilot.service
systemctl enable --now clucktalk-backup.timer
systemctl enable caddy.service
systemctl restart caddy.service

# Wait up to 30 s for the app to answer on localhost.
ok=""
for _ in $(seq 1 30); do
  answer=$(curl -fsS --max-time 2 http://127.0.0.1:8766/healthz 2>/dev/null || true)
  if [[ "$answer" == *'"ok"'* ]]; then ok=1; break; fi
  sleep 1
done
[ -n "$ok" ] || { echo "bootstrap: the app did not answer on 127.0.0.1:8766; see: journalctl -u clucktalk-pilot -n 50" >&2; exit 1; }

# Remove what deploy.ps1 uploaded (the bundle and, if given, the farm file) from the staging folder.
case "$STAGE" in /tmp/clucktalk-stage*) rm -rf "$STAGE" ;; esac
log "done. HTTPS hostname: https://$HOST"
log "farmer link: run  sudo clucktalk-show-link  on this server (it is shown on that screen only)."
