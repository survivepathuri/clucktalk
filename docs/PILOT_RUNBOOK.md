# Pilot runbook (stage 1)

This is the plan for running ONE live link that a farmer uses himself for a few days, and the same build for the demo.
**Nothing in it has been run on a server yet**: the templates in `deploy/` were written and tested on a laptop only
(file contents, the backup and restore scripts, the launcher). No cloud account was touched. Treat every step below as
untried until you have done it once and written down what happened (in `FRICTION_LOG.md` if something was awkward).

## What it is, and is not

- A prototype. A farmer types Telugu (his keyboard's voice typing does the speaking) or taps buttons; CluckTalk answers in
  Telugu text. There is no Telugu audio, no Alexa+ involved, and no card on the phone page.
- Not a veterinary service. An alert is a prompt to look at the birds, not a diagnosis. The weight and cumulative
  mortality targets are general curves that may not fit his birds; in the pilot no bird weights are logged at all.
- Two separate instances, never sharing data: **pilot** (his real houses, his own state file, a token) and **demo**
  (the fictional farm, for the judges).

## The two instances

| | pilot | demo |
|---|---|---|
| Mode | `CLUCKTALK_MODE=pilot` | `demo` (the default) |
| Farm | the farmer's file (`pilot_farm.json`: house numbers, birds placed, placement dates; no names, no places) | the fictional seed |
| State file | `/var/lib/clucktalk-pilot/state/pilot_state.sqlite3` | `/var/lib/clucktalk-demo/state/demo_state.sqlite3` |
| OS user | `clucktalk-pilot` | `clucktalk-demo` |
| Ports (loopback only) | 8765 (MCP) and 8766 (page) | 8775 and 8776 |
| Token | required | optional |
| Badge on the page | "Pilot (real farm, prototype)" | "Demo data · mock host" |

They are kept apart in four ways, and the software enforces the first two: (1) a pilot refuses to start unless its state
file name contains its instance name and lies outside the demo's folder, and a demo refuses a state file with "pilot" in
its name; (2) a pilot never loads the demo seed and never reads the demo's default weather or rule file (it needs
explicit paths); (3) different OS users and folders (the `.service` templates); (4) different ports and hostnames.

## What you need first (not done by this repository)

- A server with a public address and two hostnames (`PILOT_HOST`, `DEMO_HOST`) pointing at it. Lightsail (a small fixed-price
  instance) or EC2 fit; **App Runner is not suggested** (a container with no durable disk, and I recall it no longer taking
  new customers: check before relying on this). Our own log shows this AWS account is a new India account with a
  verification gate and low quotas (FL-012 to FL-018); nothing in it says whether Lightsail or EC2 are restricted for it, so
  look in the console on day one: an account problem could cost days.
- Python 3.13 and `git` on the server, and Caddy (HTTPS certificates by themselves).

## Deploy (first time)

1. As root, make the users and folders (the commands are in the comments at the top of each `.service` file), **and the backup
   folder, owned by the pilot user and private to it, before the first backup runs**:
   `install -d -o clucktalk-pilot -g clucktalk-pilot -m 700 /var/backups/clucktalk-pilot` (without it the first night's backup fails).
2. `git clone` the repository to `/opt/clucktalk`, then `cd /opt/clucktalk && python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
3. Put the farmer's real houses in `/var/lib/clucktalk-pilot/pilot_farm.json` (shape: `docs/pilot_farm.example.json`; the real
   file is never committed). His feed price goes in the file with a label saying where it comes from (the example file
   shows the shape with an invented blend of three feeds); the file keeps that wording with the number. Put his number for the daily deaths rule in
   `/var/lib/clucktalk-pilot/daily_deaths_rule.json` (shape: `docs/daily_deaths_rule.example.json`, with `"is_example": false`).
   His "2 per 1000" is a rule from a broiler farmer's practice (not measured data), relayed and **not confirmed in writing**: confirm it with him.
   **Ask him, for each house, how many birds died before the pilot started** (since the chicks were placed) and enter that
   number as `deaths_before_pilot` for the house (a whole number from 0 up to the birds placed; the example file shows it).
   CluckTalk only sees the deaths logged from now on; without this number the live birds, the room for new deaths and the
   total-mortality percentage would all be too optimistic. A number above the birds placed stops the start with a message.
4. Make two tokens (`python -c "import secrets; print(secrets.token_urlsafe(32))"`, once for the farmer, once for
   the Simulator to the MCP server) and put them with the other settings in `/etc/clucktalk/pilot.env` (`deploy/env.example` has
   the names). Do the same for `demo.env`.
5. Copy `deploy/Caddyfile.template` to `/etc/caddy/Caddyfile` (replace the two names), then `systemctl reload caddy`.
6. Copy the `.service` and `.timer` files from `deploy/` to `/etc/systemd/system/`, then
   `systemctl daemon-reload && systemctl enable --now clucktalk-pilot clucktalk-demo clucktalk-backup.timer`.
7. Check: `curl -s https://PILOT_HOST/healthz` gives `{"status":"ok","mode":"pilot"}`; `curl -s https://PILOT_HOST/api/state` gives
   401 (no token). Give the farmer ONE link: `https://PILOT_HOST/#t=<his token>`. The token sits after the `#`, so it is not
   sent to the server or written in any log, and the page removes it from the address bar after reading it.
8. **Test it on his phone before he does**, in a quiet room and then with the shed noise if you can: type Telugu with the
   keyboard's voice typing, tap each of the 8 buttons, confirm one record and cancel one.

## Update

`cd /opt/clucktalk && git pull && .venv/bin/pip install -r requirements.txt && sudo systemctl restart clucktalk-pilot clucktalk-demo`.
Run `python tasks.py check` on your own machine first. Restarting changes no data.

## Backup and restore

- The timer runs `deploy/backup_sqlite.py` every night at 02:30 (SQLite's online backup, integrity-checked, private to the
  pilot user, 14 kept) and then `deploy/restore_test.py` on the newest one. A backup that cannot be restored makes that
  unit fail, which `systemctl status clucktalk-backup` shows.
- Copy `/var/backups/clucktalk-pilot` to a **private** bucket yourself (encryption on, no public access); this repository does
  not do that for you and nothing here has ever written to one.
- **Do the restore test by hand once before the farmer starts**:
  `sudo -u clucktalk-pilot /opt/clucktalk/.venv/bin/python deploy/restore_test.py --dest /var/backups/clucktalk-pilot --live /var/lib/clucktalk-pilot/state/pilot_state.sqlite3`
  It prints `restore test: PASS`, the table names and row counts (never a row).
- **How old is the last good backup?** `python tasks.py pilot-stats --usage /var/lib/clucktalk-pilot/state/usage_pilot.json --backups /var/backups/clucktalk-pilot`
  prints "Last good backup: N hours ago" (from the stamp the backup script writes only after a copy passed its integrity
  check) and a WARNING when it is more than 26 hours old, missing or unreadable. Look at it every few days; nothing else tells you.
- To restore for real: stop the pilot, move the damaged file aside (do not delete it), copy the chosen backup to
  `pilot_state.sqlite3`, start the pilot, and run the health check. **Also move aside any `pilot_state.sqlite3-journal`,
  `-wal` or `-shm` file lying beside the replaced database** (they belong to the old file and can undo or corrupt the restored one).

## Kill switch

- `touch /var/lib/clucktalk-pilot/state/DISABLED` pauses the pilot at once: every page and API call answers 503, and
  `/healthz` says `disabled`. `rm` the file to resume. No restart is needed (it is checked at every request).
- Or set `CLUCKTALK_DISABLED=true` in the environment file and restart. `systemctl stop clucktalk-pilot` stops it fully.
- Taking away a farmer's access alone: remove his token from `CLUCKTALK_SIMULATOR_TOKENS` and restart.

## Delete on request

If the farmer asks: `systemctl stop clucktalk-pilot`; copy nothing; then delete **every copy**, and write down the date:

- the state file `pilot_state.sqlite3` and any `-journal`, `-wal` or `-shm` file beside it, and the state folder's
  `state/backups` folder if `reset-demo` or anything else ever moved a file there;
- `usage_pilot.json`, `pilot_farm.json` and `daily_deaths_rule.json` (and `weather_rules.json` if used);
- every file in `/var/backups/clucktalk-pilot`, and in the private bucket **including old versions** if versioning is on;
- the journald logs of the pilot units (`journalctl --vacuum-time=1s` after stopping it, or rotate them out): they hold no
  words he typed, but they hold dates and startup lines;
- copies you made yourself (a laptop, a download, a screenshot) and his token (remove it from `CLUCKTALK_SIMULATOR_TOKENS`).

His records exist only in these places. Then tell him it is done.

## Rotating a token

Use this when a link was shared by mistake, a phone was lost, or on a schedule. Revocation is a restart; to give him no gap, use
two tokens that overlap:

1. Make a new token (`python -c "import secrets; print(secrets.token_urlsafe(32))"`).
2. Add the new token after the old one in `CLUCKTALK_SIMULATOR_TOKENS` (two tokens, comma separated) and restart the pilot. Both work now.
3. Send him the new link, `https://PILOT_HOST/#t=<new token>`, and ask him to open it once on his phone (the page keeps it for that tab).
4. When he has, remove the old token from the list and restart again. The old link stops working at once: that is the revoking.
5. If the old link leaked, do steps 2 to 4 with no waiting (he opens the new link, then you remove the old token).
   The MCP server's own token (`CLUCKTALK_AUTH_TOKEN`) is a different value and is rotated the same way, in one restart.

## Service hardening

The two instance units run as their own users with a read-only system, private temporary files, no new privileges, a hidden
`/proc`, a private user namespace, no kernel access and a native-only system call architecture. Two settings were **skipped on
purpose**: `MemoryDenyWriteExecute` (Python libraries that use libffi or a JIT need memory that is writable and executable, so
it can stop the service starting) and `SystemCallFilter` (a filter that is too tight kills Python without a message). Neither was
tested on a real server, so neither is claimed. `PrivateUsers` needs user namespaces: if the host forbids them the unit will not
start, and the line can be removed with a note in the friction log.

## What is stored, and who can read it

- **Stored**: his houses (number, birds placed, placement date), what he logs (deaths, feed, health checks and answers,
  confirmed or cancelled read-backs, with dates), his rule file, and one anonymous counter file.
- **Not stored**: audio (his keyboard's speech service hears his voice, not CluckTalk), names, places, phone numbers, the words
  he types (they are used to pick an action and are not logged or saved, only the confirmed result is), or the token.
- **Anonymous counters** (`usage_pilot.json`, shown by `python tasks.py pilot-stats --usage FILE`): days used, records
  confirmed, watch and alert answers shown, read-backs confirmed and cancelled. Numbers only: safe to publish.
- **Who can read it**: you (the builder) with your server access, and AWS as the host of the machine and the backups. Nobody
  else, unless you give access. The demo's user cannot read the pilot's files.
- **First open: one notice screen with seven items** (a test and not a veterinary service; for a sick bird call his vet; an alert
  is a reminder to look and not a diagnosis; the targets are general numbers that may not fit his birds; his keyboard's voice typing goes to
  its own speech service; what is stored and that you can read it; he can ask for deletion at any time). He acknowledges it with one big button; nothing
  else on the page works until he has, and the page remembers it on that device (it asks again if the wording changes or the browser keeps
  nothing). Check it reads naturally to him before he starts: the Telugu is a draft pending a native speaker's review.
- **What the farmer must be told, in Telugu, before he starts** (a Telugu draft, to be reviewed by a
  native speaker): what is stored; that you can read it; that he can ask for deletion; that this is a test and not a
  veterinary service; that an alert is a prompt to look, not a diagnosis; that the weight and total-mortality targets are
  general curves that may not fit his birds; and that his keyboard's voice typing sends his voice to its own speech service.

## When the morning count belongs to a day

The farmer counts the deaths of the last 24 hours once each morning; CluckTalk files that count under **today's date
(Asia/Kolkata)**. Tell him this once. A second number for the same house on the same day is most likely a correction, so the
page asks him: **add** (the new number is added to the existing one and the total is shown), **replace** (the new number
replaces the existing one, and the old value that goes is shown) or **no**. A plain yes does not answer it. A total above the
birds in the house is refused. The first log of a day, and a log for another day, are not asked about. This changes no alert
rule.

## Pilot settings and the alerts that can be wrong

- No bird weights are logged (the tool refuses, with the "no verified growth standard" message), so the weight and feed
  conversion alerts cannot fire. His houses have no breed, so feed and sale plans say there is no growth standard for them.
- The total-mortality alerts (5 and 10 percent) and the death-spike rule (3 times the week before, at least 3 birds) are the
  general rules and **can be wrong for his farm**. They stay as they are (they are safety rules); tell him so.
- His own deaths rule only ever raises a shed to "needs a closer look"; it never lowers anything or removes vet advice.
- A day with only deaths logged records zero feed for that day; the feed alerts are off for his houses, but the record book
  will show zero feed. Ask him to log feed too, or ignore the feed number.
- The health check runs the rule-based test model, labelled as such, not a live model. The live weather forecast is off
  unless you set both `CLUCKTALK_WEATHER_RULES_PATH` and `CLUCKTALK_WEATHER_LIVE=true`, and it has never been run against the
  real service.
- Speech recognition accuracy in a noisy shed is **untested**: he can always tap. The cards (Echo Show pictures) are not
  shown on the phone page.
