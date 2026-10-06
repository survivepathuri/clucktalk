# Pilot runbook: the builder's own Windows PC (stage 1)

This is the plan for running the farmer pilot on **the builder's own Windows 11 PC**, published to the farmer's phone through
a free Tailscale Funnel at `https://dataanalyst.tail011920.ts.net`. There is no cloud server. The Linux version of this plan
is `docs/PILOT_RUNBOOK.md` (what the pilot is, what is stored, the alerts that can be wrong, rotating a token); read its
sections "What it is, and is not", "Pilot settings and the alerts that can be wrong" and "What is stored, and who can read it"
too, because they apply here unchanged.

**Nothing in this runbook has been run end to end yet.** The scripts in `deploy/windows/` were written and their pieces were
tried on a laptop in a temporary folder (token making, the refusals, backup, restore, the kill switch), and a harness test
checks their text. The server was **not** started through them with a real farm file, no tunnel was ever created, and no
phone was used. Treat every step as untried until you have done it once and written down what happened (in `FRICTION_LOG.md`
if something was awkward).

## How it fits together

```
farmer's phone --https--> Tailscale Funnel --> 127.0.0.1:8766 (the page, "Simulator")  --> 127.0.0.1:8765 (MCP server)
```

- **Forward the tunnel to port 8766 only.** That is the page and its API (`CLUCKTALK_SIMULATOR_PORT`). The MCP server on port
  8765 listens on `127.0.0.1` and is never forwarded; `start-pilot.ps1` refuses to start if `CLUCKTALK_HOST` is set.
- The page opens at the root path `/`. The farmer's link is `https://dataanalyst.tail011920.ts.net/#t=<farmer token>`.
  The token sits after the `#`, so the browser does not send it in the address, and the page removes it from the address
  bar after reading it.
- Every page and API call needs the token (the API answers 401 without it). The page also needs the right Host
  (`CLUCKTALK_PUBLIC_ORIGIN`); anything else answers 421.

## 1. Before you start

- The repository on this PC with its virtual environment: `python tasks.py setup` (Python 3.13). Run
  `python tasks.py check` once so you know the build is sound.
- Tailscale installed and signed in, with HTTPS and Funnel allowed for your tailnet (an admin-console setting). **Read
  Tailscale's own Funnel page before you start**: the commands below are from memory of its documentation and were not run
  here. `tailscale funnel --help` shows the exact words your version uses.
- Windows PowerShell 5.1 (the one that comes with Windows 11). The scripts run with `-ExecutionPolicy Bypass` only through
  `start-pilot.cmd`; to run the others directly, open PowerShell and use
  `powershell -NoProfile -ExecutionPolicy Bypass -File deploy\windows\<script>.ps1`.
- Turning on BitLocker for the drive is a good idea (the files below hold a real farmer's records).

## 2. Make the folders

Everything real lives **outside the repository**, in `C:\clucktalk-pilot\`. In PowerShell:

```
New-Item -ItemType Directory -Force C:\clucktalk-pilot\env, C:\clucktalk-pilot\state, C:\clucktalk-pilot\logs, C:\clucktalk-pilot\backups
```

| What | Where |
|---|---|
| The private settings and tokens | `C:\clucktalk-pilot\env\pilot.env` |
| The state file (his records) | `C:\clucktalk-pilot\state\pilot_state.sqlite3` |
| The farm file (his houses) | `C:\clucktalk-pilot\pilot_farm.json` |
| His deaths rule | `C:\clucktalk-pilot\daily_deaths_rule.json` |
| Usage counters and the kill switch | `C:\clucktalk-pilot\state\usage_pilot.json`, `C:\clucktalk-pilot\state\DISABLED` |
| Backups, logs | `C:\clucktalk-pilot\backups\`, `C:\clucktalk-pilot\logs\` |

`start-pilot.ps1` refuses to start if the state file or the farm file lies inside the repository or is the demo's file.

## 3. Make the tokens

```
deploy\windows\new-token.ps1
```

- It copies `deploy\windows\env.windows.example` to `pilot.env` (if there is none), makes two random tokens (32 random bytes
  each, from Windows' cryptographic generator) and writes them into the file, then limits the file to your Windows account.
- Open `C:\clucktalk-pilot\env\pilot.env` and set `CLUCKTALK_PUBLIC_ORIGIN=https://dataanalyst.tail011920.ts.net`. Then run
  `deploy\windows\new-token.ps1 -ShowLink`. It prints the **farmer link** once on the screen. It is never saved anywhere
  else; copy it into the message to the farmer yourself and do not keep it in a chat history you do not control.
- The tokens are never printed by any other script and never appear in the logs. To make a new farmer token (a lost phone,
  a shared link), put the placeholder `<TOKEN_FOR_THE_FARMER>` back in place of the value and run `new-token.ps1` again; the
  old link stops working at the next start.

## 4. Create the real pilot farm file

The real file is `C:\clucktalk-pilot\pilot_farm.json`. **It is never committed and never lives in the repository.** Start from
the example, `docs\pilot_farm.example.json`, copy it to that path and edit it. Ask the farmer, **for each house**:

1. **How many birds were placed** (`birds_placed`).
2. **The placement date** (`placed_on`, as `YYYY-MM-DD`).
3. **How many birds died before the pilot started**, since the chicks were placed (`deaths_before_pilot`; a whole number from
   0 up to the birds placed). Without it the live birds, the room for new deaths and the total-mortality percentage would all
   be too optimistic.

Also in the file: his feed price and the label for it (the example shows the shape), and `supplier_lead_days`. Put his number
for the daily deaths rule in `C:\clucktalk-pilot\daily_deaths_rule.json` (shape: `docs\daily_deaths_rule.example.json`, with
`"is_example": false`). His "2 per 1000" was relayed, **not confirmed in writing**: confirm it with him. Use no names and no
places in these files.

## 5. Start the server

```
deploy\windows\start-pilot.cmd
```

(or `deploy\windows\start-pilot.ps1`). It checks the settings, refuses with a plain message if anything is wrong, starts the
page and the MCP server in a hidden window on `127.0.0.1`, and waits for the health check. Then:

```
deploy\windows\status-pilot.ps1
```

shows whether the page answers, the kill switch, the age of the last backup and the anonymous usage totals (numbers only).
The log files are `C:\clucktalk-pilot\logs\pilot.out.log` and `pilot.err.log`; they hold no tokens and none of the words the
farmer types (the app does not log them). They do hold times and startup lines.

Stop it with `deploy\windows\stop-pilot.ps1`.

## 6. Publish it: the Tailscale commands (you run these yourself)

Nothing in this repository runs Tailscale. In a normal PowerShell window, after the pilot is started:

```
tailscale funnel --bg 8766
tailscale funnel status
```

`--bg` keeps the Funnel running in the background; `status` should show `https://dataanalyst.tail011920.ts.net` forwarding to
`127.0.0.1:8766`. **Check that it points to 8766 and to nothing else.**

To turn the Funnel **off** (the farmer's link stops answering at once):

```
tailscale funnel --https=443 off
```

(`tailscale funnel reset` clears the whole serve and funnel configuration.) Also pause the pilot itself if you want the data
untouched: section 9.

**Not verified:** that Funnel passes the original Host header (`dataanalyst.tail011920.ts.net`) through to the page. The page
accepts only that host and the loopback names. If the first-run check below shows `{"error":"unknown host"}` (421), stop
and tell the maintainers: it means Funnel changes the Host and the page needs a change.

## 7. First-run check, on your own phone, before the farmer

Use mobile data (not the PC's Wi-Fi) so the request really goes through the public link.

1. Open the farmer link. The page should open and the address bar should lose the `#t=...` part.
2. Read the Telugu notice with its seven items and tap the acknowledge button. Nothing else works before that.
3. Log a test record (a deaths number for house 1), see the read-back, tap **no / cancel**, and confirm nothing was saved.
   Then log one and tap yes if you want to see it saved, and **delete the test data afterwards**: stop the pilot, move the state
   file aside (not the backup), and start again (a new empty state file is made).
4. **Without the token, the page must answer 401.** In a private tab on the phone open
   `https://dataanalyst.tail011920.ts.net/api/state`. It must show `{"error":"unauthorized"}`. Any answer with data is a failure:
   stop the Funnel (`tailscale funnel --https=443 off`) and the pilot.
5. On the PC, `deploy\windows\kill-switch.ps1 -Action pause`, reload the page (it must show it is paused), then
   `-Action resume`.
6. Run `deploy\windows\backup-pilot.ps1` once and read its last line. It runs the restore test on the new backup.

## 8. Power cut, restart and when it is down

- After a power cut or a restart, the pilot does **not** start by itself. Log in to Windows and run
  `deploy\windows\start-pilot.cmd`. Then run `tailscale funnel status` (the Funnel setting is kept by Tailscale across
  restarts as I recall; check, and run `tailscale funnel --bg 8766` again if it is gone) and `deploy\windows\status-pilot.ps1`.
- Nothing is lost by a power cut that the farmer already saw saved: a record is written when he taps yes. The state file is
  a SQLite database; if it is damaged, restore the newest backup (section 11).
- **What the farmer sees when the server is down:** not observed here. With the page already open, his next tap shows the
  page's Telugu "something went wrong, try again" message and nothing is saved. With a fresh link open, his browser shows
  whatever error Tailscale's public gateway or his browser gives for an unreachable site. Tell him once, in words, that when it does not open he should try again later and call you, and that this is a helper and
  not an alarm: he keeps checking the birds with his own eyes.
- **Availability depends on that PC and its internet.** Windows updates restart it, the PC can sleep (turn sleep off while
  plugged in), and a home connection can drop. Nothing here promises or measures uptime.

## 9. Pause and resume (the kill switch)

```
deploy\windows\kill-switch.ps1 -Action pause
deploy\windows\kill-switch.ps1 -Action resume
deploy\windows\kill-switch.ps1 -Action status
```

`pause` creates the file `C:\clucktalk-pilot\state\DISABLED`; at once every page and call answers 503 and `/healthz` says
"not ok". `resume` removes the file. No restart is needed. The Funnel stays up while it is paused.

## 10. Daily backup with Task Scheduler

`backup-pilot.ps1` makes a consistent copy of the state file with Python's SQLite online backup (never a plain file copy),
checks it, keeps the newest 14 in `C:\clucktalk-pilot\backups\`, writes the `LAST_GOOD_BACKUP` stamp only after a copy passed
its check, then proves the newest backup can be restored. **Review this command before you run it**, and replace `<REPO>` with
the repository folder:

```
schtasks /Create /TN "CluckTalk pilot backup" /SC DAILY /ST 02:30 /RL LIMITED /TR "powershell -NoProfile -ExecutionPolicy Bypass -File \"<REPO>\deploy\windows\backup-pilot.ps1\""
```

- It runs as your own account, only when you are logged in, and **a task that was due while the PC was off or asleep is not
  made up** (this command does not set "run as soon as possible after a missed start": open Task Scheduler, the task's
  Settings tab, to set it if you want that).
- Check it: `schtasks /Run /TN "CluckTalk pilot backup"`, then `deploy\windows\status-pilot.ps1`. It prints "Last good backup:
  N hours ago" and a WARNING when that is more than 26 hours. Look at it every few days: nothing else tells you.
- Remove it with `schtasks /Delete /TN "CluckTalk pilot backup"`.

## 11. Weekly copy to a USB drive, and restoring

Once a week, with the drive plugged in (replace `E:` with its letter):

```
deploy\windows\backup-pilot.ps1 -CopyTo E:\clucktalk-backup
```

It copies the newest backup to that folder and checks the size. The drive then holds the farmer's records: keep it private,
and wipe it if you stop the pilot.

To restore for real: `deploy\windows\stop-pilot.ps1`, then
`deploy\windows\restore-pilot.ps1 -BackupFile C:\clucktalk-pilot\backups\<the backup file>`. It tests the backup first, asks
you to type RESTORE, moves the damaged state file **aside** (it never deletes it) and also any `-journal`, `-wal` or `-shm` file
lying beside it (they belong to the old file and can undo or corrupt the restored one), then copies the backup into place. Then
`start-pilot.cmd` and `status-pilot.ps1`.

## 12. Delete on request

If the farmer asks: stop the Funnel (`tailscale funnel --https=443 off`), run `stop-pilot.ps1`, then delete **every copy** and
write down the date:

- `C:\clucktalk-pilot\state\` (the state file, any `-journal`, `-wal` or `-shm` file, and every `.aside-...` file a restore
  left), `usage_pilot.json`, `pilot_farm.json`, `daily_deaths_rule.json`;
- every file in `C:\clucktalk-pilot\backups\` and the `clucktalk-backup` folder on every USB drive;
- the logs in `C:\clucktalk-pilot\logs\` (no words he typed, but dates and startup lines);
- copies you made yourself (a download, a screenshot, a message holding his link) and his token (remove it from `pilot.env`);
- the Recycle Bin, and a deleted file is not gone from a drive that is not wiped or encrypted: BitLocker on the drive helps.

His records exist only in these places. Then tell him it is done.

## 13. Who can read the data

The builder, and **anyone with access to this PC** (another Windows account with administrator rights, anyone who can sit at
it logged in, anyone who takes the USB drive, and malware on it). The two files that matter (`pilot.env` and the backups
folder) are restricted to your Windows account, which does not stop an administrator or someone with the disk itself.
Tailscale's servers relay the public connection; this runbook does not claim what they can or cannot see (read Tailscale's
Funnel documentation for that). The anonymous counters hold numbers only.

## 14. For the README and the video (say exactly this)

Once the pilot has really run on this PC (not before), say:

> The pilot ran on the builder's own PC, published through a free Tailscale Funnel; availability depends on that PC and its
> internet.

Before it has run, the README says the same thing in the present tense and adds that it has not been started yet. Nothing more
about uptime, speed or reliability may be said, because none of it has been measured.
