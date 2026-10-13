# Cloud pilot (additional to the PC pilot)

An **additional** way to run the pilot: the same CluckTalk build on one small AWS Lightsail server, so the farmer can use the
page from a phone while your PC is off. It does not change how CluckTalk runs locally. The local run (`python tasks.py run`,
the judges' path in `docs/JUDGES.md`) and the PC pilot with Tailscale Funnel (`docs/PILOT_RUNBOOK_WINDOWS.md`) are untouched
and stay the fallback.

**Status: deployed once on a real server (2026-10-13) with the sample farm file; no farmer has used it.** Every command for the
server is in `deploy/cloud/RUNBOOK.md`. What was and was not tested is listed at the end of this page.

## What runs where

| Where | What | Reachable from the internet? |
|---|---|---|
| Lightsail instance (Ubuntu, ap-south-1) | Caddy (HTTPS, ports 80 and 443) | yes, only the farmer's page paths |
| same instance | Simulator web page, `127.0.0.1:8766` | only through Caddy, and `/api/` needs the farmer's token |
| same instance | MCP server, `127.0.0.1:8765` | **no** (loopback only, and not proxied) |
| same instance | SQLite state, farm file, anonymous counters under `/var/lib/clucktalk-pilot` | no |
| same instance | daily backups under `/var/backups/clucktalk-pilot` (newest 7) | no |
| your PC | `deploy/cloud/*.ps1` (deploy, verify, stats) over SSH | SSH only, key-only |

## Exposure decision, from the code

- The farmer's phone page needs five URLs: `/`, `/static/*`, `/api/pilot/ui`, `/api/turn` and `/healthz`
  (`src/clucktalk/simulator/static/pilot.js`, `app.py`). Caddy forwards **only those**; everything else (`/desktop`, `/sandbox`,
  `/api/state`, `/api/resource`, any `/mcp`) answers 404 at the proxy.
- The **MCP server is not public**. In this design nothing outside the machine needs it: the Simulator talks to it on
  `127.0.0.1` with its own token (`CLUCKTALK_AUTH_TOKEN`, required in pilot mode). A public MCP endpoint would only be needed
  for a real Alexa+ connection, which this pilot does not use.
- The Simulator checks the `Host` header and, on `POST`, the `Origin` and a JSON content type; every `/api/` call needs
  `Authorization: Bearer <token>`, compared in constant time. A wrong or missing token answers 401. The farmer token
  allows 60 calls a minute (`CLUCKTALK_RATE_PER_MINUTE`); wrong tokens share a counter of 20 a minute and then answer 429;
  a request body over 8 KB answers 413. These limits are in the app, not in Caddy (stock Caddy has no rate limiter).
- **SSH key**: the scripts use `%USERPROFILE%\.ssh\clucktalk-pilot-ed25519` by default (`-KeyPath` overrides it). The first key, the
  one downloaded from the console, was replaced on 2026-10-13 after its text had been exposed; `authorized_keys` now holds only the
  new key (RUNBOOK section 11 has the steps). A private key file is never opened, pasted or committed.
- The firewall (ufw on the server and the Lightsail firewall in the console) allows 22, 80 and 443 only. SSH is key-only (no passwords),
  and you should restrict port 22 to your own IP in the console. (`ufw limit` was tried first and removed: it locked the deploy scripts out.)
- The app runs as its own system user with no shell, can write only `/var/lib/clucktalk-pilot`, and its code is owned by root.
  Secrets are in `/etc/clucktalk/pilot.env` (root and the app user only). The service restarts by itself (`Restart=always`).

## How the HTTPS name is built

No domain is bought. The hostname is the static IP with dashes plus `.sslip.io`: `203.0.113.10` becomes
`203-0-113-10.sslip.io`. sslip.io is a free public DNS service that answers with the IP written in the name. Caddy asks Let's
Encrypt for a certificate for that name by itself and renews it (it needs ports 80 and 443 open).
Why this and not something simpler: a Lightsail instance has no usable HTTPS name of its own, and plain `http://IP` would send the
farmer's token in clear text. Caveats, so you can decide:

- It depends on a third-party service (sslip.io DNS). If it is down, the name does not resolve. The link then needs a changed hostname.
- Let's Encrypt limits certificates per registered domain per week, and `sslip.io` is shared by everyone who uses it. If a
  certificate cannot be issued, `journalctl -u caddy` says so; the fix is another free name (for example nip.io) or a domain you own.
- The farmer's link contains the IP. If the static IP changes, the link changes (a static IP removes that risk while it stays attached).

## Data on the server (for the farmer's consent note)

When the instance is created in the **Mumbai region (ap-south-1)**, the data is stored on an AWS server in India. Confirm the
region in the console before you say this to the farmer.

- **Stored**: the houses in the farm file (house number, birds placed, placement date, birds that died before the pilot),
  what the farmer logs (deaths, feed, health checks and answers, confirmed or cancelled read-backs, with dates), the daily-deaths rule if used,
  and one anonymous counter file (numbers only).
- **Not stored**: audio, names, places, phone numbers, the words typed (they pick an action and are not saved), or the token.
- **Who can read it**: you, with SSH access to the server, and AWS as the host of the machine and any snapshot you take.
  Nobody else unless you give access. Caddy keeps no access log.
- **Backups** are kept on the same server for 7 days. A copy you download or a snapshot lives where you put it.
- **Deletion**: the farmer can ask at any time; deleting the instance (RUNBOOK section 10) removes the data and the backups.
- Say also, in Telugu and as the page's own notice does: this is a test and not a veterinary service, an alert is a
  reminder to look at the birds and not a diagnosis, and the phone's voice typing goes to its own speech service.
- Wording for the consent note is the builder's to write and to check with a native Telugu speaker.

## Limits

- One small server, one instance, no failover: if it is down, the page is down. There is no load balancer, no managed database and no
  automatic scaling. Backups on the same disk do not protect against losing the instance (use a snapshot or download a copy).
- The AI is the rule-based test model (`MOCK_BEDROCK=true` is required in pilot mode): no Bedrock calls, no AWS service except the Lightsail server.
- Telugu text on the page is a draft pending a native speaker's review (`docs/TELUGU_REVIEW.md`).
- Cost is not stated here because this repository could not look up current Lightsail prices offline. Read the plan price
  on the Lightsail pricing page for ap-south-1, multiply for 30 days, and add any snapshot. A static IP attached to a running instance has no extra charge; a detached one does.
- Rate limits are per app instance and per token, not per visitor address.

## Before sending to the farmer (checklist)

- [ ] The instance is in **ap-south-1**; there is exactly one instance and one static IP, named `clucktalk-...`.
- [ ] Lightsail firewall: 22 (restricted to your IP if possible), 80, 443 only.
- [ ] `deploy.ps1` finished without an error; `verify.ps1` printed no FAIL (and ran with `-Reboot` once).
- [ ] The farm file is the farmer's real one (`clucktalk-status` shows "farmer's own file in place", not the WARNING).
- [ ] Their `deaths_before_pilot` numbers and the daily-deaths rule were confirmed with them (`docs/PILOT_RUNBOOK.md`).
- [ ] You opened the link on a phone yourself: the notice screen appears, the Telugu reads naturally, one record can be made and confirmed.
- [ ] A backup was made (`sudo systemctl start clucktalk-backup`) and `clucktalk-restore` was tried once on a scratch copy; a snapshot or an off-server copy exists.
- [ ] The consent note (what is stored, in India, who can read it, deletion on request, test only, not a vet) was told to the farmer in Telugu.
- [ ] The link was sent privately (not in a group, not in a chat with an assistant); you know how to rotate it (RUNBOOK section 5).
- [ ] You know how to pause (RUNBOOK section 3) and how to delete everything (section 10).
- [ ] The PC pilot is still your fallback: its link is not the same as this one.

## Pilot numbers

`.\deploy\cloud\pilot-stats.ps1 -ServerIp IP` runs `python tasks.py pilot-stats` on the server over SSH and prints the
anonymous totals. There is no public statistics endpoint.

## What was tested, and what was not

**Status: first real deployment done on 2026-10-13** (Lightsail, Ubuntu 24.04.4, Mumbai, 1 GB memory plan, sample farm file).

Passed on the real server (`deploy.ps1` twice, `verify.ps1 -Reboot` twice, all PASS; the only WARN is the sample farm file):
HTTPS with a valid Let's Encrypt certificate for the sslip.io name; health ok; missing and wrong token 401; the right token 200;
`/desktop`, `/sandbox`, `/mcp`, `/api/state`, `/api/resource`, `/.env` all 404; ports 8765 and 8766 not reachable from outside and
listening on 127.0.0.1 only; failed-token rate limit 429; the app back after a service restart and after a reboot; app, Caddy and
backup timer enabled at boot; a manual backup that passes the restore test; a restore into a scratch folder (integrity ok, same
tables as live); `clucktalk-restore` itself; SSH key-only; ufw 22, 80, 443; a second `deploy.ps1` run kept the tokens and the data.
The farmer page was also driven in headless Chrome at phone size: the notice screen with its 7 items, the acknowledgement, a tap on
the farm-status button and a Telugu answer that came through the MCP server. The page requested only `/`, `/static/*`, `/api/pilot/ui`
and `/api/turn`; `/favicon.ico` answers 404 (the app has no icon).

Found and fixed on that run: `verify.ps1` could not see the "farm file is the example" marker (the folder is private to the app user),
so it reported PASS while the sample was in place; and `ufw limit 22` locked the deploy scripts out of SSH after a few quick
connections (now plain `allow 22`, key-only SSH, restrict 22 to your IP in the console).

**Still not tested:** the Ubuntu 22.04 route (Python 3.12 from deadsnakes); `clucktalk-rotate-token` and `clucktalk-show-link`
(the farmer token was read for the checks by a different command); certificate renewal after 60 days; the 02:30 timer firing by
itself (the same unit was started by hand); a snapshot or an off-server copy of the backups; the real farm file and a real day of
use; memory under real load (the plan has about 900 MB and about 460 MB was free after start). Record problems in `FRICTION_LOG.md`.

## Switching from the sample farm to the real one

The first deployment holds the **fictional sample** farm. Before the real farm file goes in, start from empty state so no
sample record or house is left behind (the state is empty or nearly so, but check `clucktalk-status`):

```bash
sudo systemctl stop clucktalk-pilot
sudo mv /var/lib/clucktalk-pilot/state /var/lib/clucktalk-pilot/state.sample-$(date +%Y%m%d)
sudo install -d -o clucktalk-pilot -g clucktalk-pilot -m 700 /var/lib/clucktalk-pilot/state
```

To make the farm file at the farm without typing JSON, ask the questions in `docs/FARMER_QUESTIONS_TE.md` and answer
`deploy/cloud/make-farm.ps1` (it checks the answers with the app's own parser and writes to `.local\real_pilot_farm.json`, which git ignores).

then, on your PC: `.\deploy\cloud\deploy.ps1 -ServerIp IP -FarmFile C:\path\real_pilot_farm.json`
(it installs the file, removes the "example" marker and restarts the app). This switch was not tested.
