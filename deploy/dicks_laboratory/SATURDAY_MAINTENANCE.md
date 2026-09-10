# Dragon — Saturday Maintenance Procedure (operator-initiated)

**Why this is manual for now:** during the 0W-AZ3 → 0W-4 reliability-proving
period the futures host runs **continuously Sunday → Friday**, so automatic apt
upgrades / service restarts must not happen mid-session. All apt automation on
`dragon` is disabled (see "What AZ3 disabled" below). Security updates are
**not abandoned** — they move to a controlled **Saturday** window while the VM
is otherwise deallocated. Automating this window is a later hardening step
(post-0W-4), not part of AZ3.

Weekend timeline: `Stop-Dragon` deallocates ~Fri 16:45 CT; `Start-Dragon`
powers on ~Sun 15:30 CT. Saturday is entirely outside that.

---

## Procedure

Run from `robby` (or `weasel`/`robyn` once verified). Nothing here starts the
collector.

```bash
# 1. Power on for maintenance (manual — the Sunday schedule is separate)
az vm start -g rg-dev-environment -n dragon
#    wait for Tailscale, then:
ssh dragon

# 2. On dragon — verify baseline
findmnt -no SOURCE,TARGET,UUID /srv/dicks_laboratory   # UUID must be 890b7de2-a7e1-4650-a7c9-464124698b29
df -hT /srv/dicks_laboratory /                          # space check
systemctl --failed                                      # expect none
timedatectl | grep -E 'synchronized|NTP'                # expect yes / active
tailscale status | head -3                              # node healthy
systemctl is-enabled dicks-lab-es-session.timer         # expect: disabled (until AZ4 arms it)

# 3. Controlled package upgrade (needrestart in automatic mode to avoid prompts)
sudo apt-get update
sudo NEEDRESTART_MODE=a apt-get -y full-upgrade
sudo NEEDRESTART_MODE=a apt-get -y autoremove --purge

# 4. Reboot only if required
[ -f /var/run/reboot-required ] && sudo reboot
#    (after reboot: ssh back in, re-run step 2 checks — especially the data mount UUID)

# 5. Optional: pull the latest accepted Copper (explicit — never automatic)
cd ~/Documents/REPOs/copper
GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519_ghdeploy -o IdentitiesOnly=yes" git fetch origin
git merge --ff-only origin/master        # fast-forward only; abort if it would merge
git rev-parse HEAD                        # record this commit
~/.local/bin/uv sync --frozen --all-packages   # --all-packages installs every workspace member (K9, dicks_laboratory, …); plain `uv sync` only does the empty root project

# 6. Re-verify, then power back off
systemctl --failed
findmnt /srv/dicks_laboratory
exit
az vm deallocate -g rg-dev-environment -n dragon
```

Record in the ops log: date, packages upgraded (count), reboot y/n, Copper
commit before/after, any anomaly.

---

## What AZ3 disabled (and how to restore it)

| Unit | AZ3 action | Restore |
|---|---|---|
| `apt-daily.timer` | `disable --now` | `sudo systemctl enable --now apt-daily.timer` |
| `apt-daily-upgrade.timer` | `disable --now` | `sudo systemctl enable --now apt-daily-upgrade.timer` |
| `apt-daily.service` | `mask` | `sudo systemctl unmask apt-daily.service` |
| `apt-daily-upgrade.service` | `mask` | `sudo systemctl unmask apt-daily-upgrade.service` |
| `unattended-upgrades.service` | `disable --now` | `sudo systemctl enable --now unattended-upgrades.service` |
| `update-notifier-download.timer` | `disable --now` | `sudo systemctl enable --now update-notifier-download.timer` |
| `motd-news.timer` | `disable --now` | `sudo systemctl enable --now motd-news.timer` |

`/etc/apt/apt.conf.d/20auto-upgrades` is **left in place** (unmodified) so the
policy is restored simply by re-enabling the timers above.

**Not touched** (must keep working): `walinuxagent` (Azure agent),
`tailscaled`, time sync, `fstrim.timer`. `needrestart` is installed; it only
acts during an apt run, so with apt automation off it is dormant — use
`NEEDRESTART_MODE=a` during the manual upgrade above.

---

## Device-name warning (Azure)

`dragon`'s `/dev/sdX` letters are **not stable across reboots** (observed:
the 256 GiB data disk was `/dev/sdc` at rebuild and `/dev/sda` after the next
boot). Every mount is UUID- or Azure-stable-path-based, so this is cosmetic —
**but never hand-mount or script against `/dev/sdX` for dragon.** Use:

- data disk: `UUID=890b7de2-a7e1-4650-a7c9-464124698b29` or
  `/dev/disk/azure/scsi1/lun0`
- OS disk: `/dev/disk/azure/os`
- ephemeral: `/dev/disk/cloud/azure_resource-part1` (→ `/mnt`, wiped on
  deallocate — never put Laboratory data here)
