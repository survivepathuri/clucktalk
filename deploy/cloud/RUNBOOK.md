# Cloud pilot runbook (Lightsail, Ubuntu)

Commands for the person who runs the server. Sections 1 to 4, 6 (backup and restore) and 7 were run on a real server on
2026-10-13; rotating the token, the snapshot or off-server copy, and deleting the resources were not (see "What was tested, and
what was not" in `docs/CLOUD_PILOT.md`). No secret belongs in this file.

Windows commands run in PowerShell on your PC; server commands run after `ssh -i KEY ubuntu@IP`. Replace `IP` with the static IP. `KEY` is your private key: the scripts use
`%USERPROFILE%\.ssh\clucktalk-pilot-ed25519` by default (`-KeyPath` overrides it). Never open, paste or commit a private key file.

## 0. One-time server set-up (done by you in the AWS console)

1. Lightsail, **Create instance**: region **Mumbai (ap-south-1)**, platform Linux/Unix, blueprint **OS only, Ubuntu 24.04**
   (22.04 also works, see `bootstrap.sh`), the smallest plan that has at least 1 GB of memory (check the price on the Lightsail
   pricing page before you click; this repository could not look it up).
2. Give the instance an SSH key. The console's key download is only for the first login: then replace it with your own
   ed25519 key (section 11) and delete the downloaded `.pem`. Keep private keys outside the repository; never commit one.
3. **Networking**: attach a **static IP** (free while attached to an instance; an unattached one is charged).
4. **Networking, IPv4 firewall**: keep SSH (22) but **restrict it to your own IP address** if you can; keep HTTP (80);
   **add HTTPS (443)**: a new Lightsail instance does not open it. Add nothing else. (Ports 8765 and 8766 must stay closed.)
5. Name everything starting with `clucktalk-` and list it in the table at the end of this file when you have the real names.

## 1. Deploy (two commands, from the repository on your PC)

```powershell
.\deploy\cloud\deploy.ps1 -ServerIp IP
.\deploy\cloud\verify.ps1 -ServerIp IP
```

- Before the first one, try it without a connection: `.\deploy\cloud\deploy.ps1 -ServerIp IP -KeyPath x -DryRun` lists the files that would be uploaded.
- `deploy.ps1 -FarmFile C:\path\pilot_farm.json` installs the farmer's real houses (shape: `docs/pilot_farm.example.json`).
  Without it the server starts with the **fictional example** and warns; do not send the link in that state.
- `bootstrap.sh` is safe to run again; so is `deploy.ps1`. Tokens already on the server are kept.
- The HTTPS name is your IP with dashes plus `.sslip.io`: `203.0.113.10` becomes `203-0-113-10.sslip.io`.

## 2. See the farmer link (screen only)

```powershell
ssh -t -i KEY ubuntu@IP sudo clucktalk-show-link
```

It prints `https://HOST/#t=TOKEN`. It refuses to print into a file or a pipe. Send it to the farmer by a private
channel, not in a group chat or an e-mail subject. Do not paste it into an issue, a log or a chat with an assistant.

## 3. Start, stop, status

On the server:

```bash
sudo clucktalk-status                       # one screen: services, health, backups, disk, farm file
sudo systemctl status clucktalk-pilot       # the app
sudo systemctl restart clucktalk-pilot      # restart the app
sudo systemctl stop clucktalk-pilot         # stop the app (Caddy stays up and answers 502)
sudo systemctl start clucktalk-pilot
sudo touch /var/lib/clucktalk-pilot/state/DISABLED   # kill switch: every call but /healthz answers 503 "paused"
sudo rm /var/lib/clucktalk-pilot/state/DISABLED      # resume
```

The app and Caddy start at boot (`Restart=always` for the app). After editing `/etc/caddy/Caddyfile` use
`sudo systemctl restart caddy` (the admin endpoint is switched off, so `reload` does not work).

## 4. Logs

```bash
sudo journalctl -u clucktalk-pilot -n 100 --no-pager     # the app
sudo journalctl -u caddy -n 100 --no-pager               # HTTPS, certificates
sudo journalctl -u clucktalk-backup -n 30 --no-pager     # the nightly backup
```

Logs go to the system journal, capped at 200 MB and 30 days (`/etc/systemd/journald.conf.d/clucktalk.conf`). Caddy writes
no access log (no addresses, paths or headers are recorded). The app logs no token, header or body.

## 5. Rotate the farmer's token

```bash
sudo clucktalk-rotate-token          # new farmer token; the old link stops working at once; the app restarts
sudo clucktalk-show-link             # then show the new link on screen
sudo clucktalk-rotate-token --mcp    # the Simulator-to-MCP token (the farmer sees no change)
```

## 6. Backup and restore

- A timer makes one backup a day at 02:30 server time (UTC) with `deploy/backup_sqlite.py`, keeps the **newest 7**, then runs
  `deploy/restore_test.py` on it; a backup that cannot be restored makes the unit fail (`systemctl --failed`).
  Files: `/var/backups/clucktalk-pilot/pilot_state_YYYYMMDD-HHMMSS.sqlite3` (plus the usage and farm files with the same stamp)
  and `LAST_GOOD_BACKUP`.
- Back up now: `sudo systemctl start clucktalk-backup.service`.
- Check a backup without touching live data: `sudo -u clucktalk-pilot /opt/clucktalk/.venv/bin/python /opt/clucktalk/deploy/restore_test.py --dest /var/backups/clucktalk-pilot`
- **Restore**: `sudo clucktalk-restore /var/backups/clucktalk-pilot/pilot_state_YYYYMMDD-HHMMSS.sqlite3`
  (tests the file, stops the app, keeps the current state as `*.before-restore-*.sqlite3.old`, puts the backup in place, starts the app).
- **The backups are on the same disk.** If the instance is lost, they are lost too. Either take a Lightsail snapshot before
  the pilot (console, instance, Snapshots; a snapshot is charged by the GB-month) or copy the folder to your PC (the folder is
  private to the app user, so plain `scp` cannot read it):
  `ssh -i KEY ubuntu@IP "sudo tar -C /var/backups -czf - clucktalk-pilot" > clucktalk-backups.tar.gz`
  The file holds the farmer's records: keep it private and out of git.

## 7. Pilot numbers (no public endpoint)

```powershell
.\deploy\cloud\pilot-stats.ps1 -ServerIp IP
```

It runs `python tasks.py pilot-stats` on the server over ssh and prints the anonymous totals and the age of the last good backup.
The usage file holds counts only (no names, dates, words, sheds or tokens).

## 8. Update the app

Run `deploy.ps1` again from the updated repository. The code is replaced, the virtual environment and the data are kept, the
app restarts. Run `verify.ps1` after it. Operating system security updates install by themselves (unattended-upgrades);
a pending reboot is shown by `clucktalk-status`.

## 9. The farmer's daily-deaths rule (optional)

```powershell
scp -i KEY daily_deaths_rule.json ubuntu@IP:/tmp/
ssh -i KEY ubuntu@IP "sudo install -o clucktalk-pilot -g clucktalk-pilot -m 600 /tmp/daily_deaths_rule.json /var/lib/clucktalk-pilot/ && rm /tmp/daily_deaths_rule.json && sudo systemctl restart clucktalk-pilot"
```

Shape: `docs/daily_deaths_rule.example.json` with `"is_example": false`. Without the file the feature is off.

## 10. Delete everything and stop all costs

Lightsail charges while an instance, a static IP that is not attached, or a snapshot exists. In the console, in this order:

1. Download anything you want to keep (section 6), and **tell the farmer**; delete their data on request at any time.
2. **Networking**: detach, then **delete the static IP** (`clucktalk-ip`).
3. **Instances**: **delete the instance** (`clucktalk-pilot`). This destroys the disk and the data on it.
4. **Snapshots**: delete any `clucktalk-` snapshot.
5. Check **Billing** the next day: Lightsail should show no running resource.

AWS CLI equivalent, only if you use it yourself (this repository never runs it):

```bash
aws lightsail detach-static-ip --static-ip-name clucktalk-ip --profile PROFILE --region ap-south-1
aws lightsail release-static-ip --static-ip-name clucktalk-ip --profile PROFILE --region ap-south-1
aws lightsail delete-instance --instance-name clucktalk-pilot --profile PROFILE --region ap-south-1
aws lightsail get-instance-snapshots --profile PROFILE --region ap-south-1   # then delete-instance-snapshot for each clucktalk- one
```

## Resources you create (names only, fill in the real ones)

| Kind | Name |
|---|---|
| Instance | `clucktalk-pilot` |
| Static IP | `clucktalk-ip` |
| SSH key | the one you chose (keep it outside the repository) |
| Firewall rules | 22 (your IP), 80, 443 |
| Snapshot (optional) | `clucktalk-snapshot-...` |

## 11. Rotate the SSH key (do this if a private key was ever shown, pasted or copied anywhere)

Rule: add the new key and test it **before** removing the old one, and never print or open a private key file.
(Done once on 2026-10-13 for this server; the old downloaded key had been pasted into a chat.)

1. New key on your PC (public part is safe to print):
   `ssh-keygen -t ed25519 -C "clucktalk-pilot-DATE" -f $env:USERPROFILE\.ssh\clucktalk-pilot-ed25519`
   (add a passphrase if you can use ssh-agent; the scripts use `BatchMode`, so a passphrase key must be loaded in the agent first).
   Then only your user may read it: `icacls $env:USERPROFILE\.ssh\clucktalk-pilot-ed25519 /inheritance:r /grant:r "$($env:USERNAME):(R)"`.
2. With the OLD key, append the new `.pub` line to `~/.ssh/authorized_keys` of the `ubuntu` user (`ssh -i OLD ubuntu@IP`, then `echo '<the .pub line>' >> ~/.ssh/authorized_keys`).
3. Test with the new key alone: `ssh -i NEW -o IdentitiesOnly=yes -o BatchMode=yes ubuntu@IP "echo ok"`. Stop here if it fails.
4. Remove the old line: find it by its public half (`ssh-keygen -y -f OLD` prints the PUBLIC key; compare the second field), delete only that
   line from `authorized_keys`, then check that the old key is refused and the new one works.
5. Check there is no other key line: `sudo grep -c "^ssh-" /home/*/.ssh/authorized_keys /root/.ssh/authorized_keys` should be 1 in total.
6. Delete the old private key file yourself, and run `verify.ps1`.

Not checked here: how Lightsail's browser-based SSH session authenticates, and whether a new instance always starts with the
console's default key. After the rotation on 2026-10-13 `authorized_keys` held exactly one line (the new key), so nothing else had been
injected into the `ubuntu` user at that time; check again after any console SSH session.
