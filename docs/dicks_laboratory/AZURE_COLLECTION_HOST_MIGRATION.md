# Azure Collection-Host Migration — Dick's Laboratory Futures Capture

Planning + audit record for moving serious unattended ES futures collection off
`robby` (Ubuntu dev laptop) onto an Azure Linux VM.

- **Repo baseline (robby):** `master` @ `ae6f33a6362e2e063eb2de5b8d19f72f7ee728d6`,
  `origin/master` same, working tree clean.
- **Project state:** `0W-H1` COMPLETE/REVIEWED · `0W-2 Attempt 4` MISSED (robby
  power loss) · `0W-2` OPEN · `0W-3` ACCEPTED/CLOSED · `0W-4` BLOCKED.

---

# Phase 0W-AZ1 — Azure Host Inventory & Access Readiness Audit

**Scope:** inspection only. No package installs, no SSH/key/firewall/NSG
changes, no repo mutation, no credential copy, no schedule/service creation, no
collector run, no VM resize/reboot, **no VM power-on**.

**Run:** 2026-09-08 evening CT, from `robby`, using local SSH config + an
already-authenticated Azure CLI session (`az` 2.90.0). No `az login` initiated.
All `az` calls read-only.

## AZ1.A — Azure target resolution

| Item | Value |
|---|---|
| SSH alias (`~/.ssh/config` on robby) | `dragon` |
| Tailscale address | `100.103.127.127` (tailnet node `dragon`, linux) |
| Public endpoint | **none** — no public IP resource currently exists (see AZ1.I). README's `52.186.144.64` is stale (earlier deployment). |
| SSH username | `temckee8` |
| Client key selected | `~/.ssh/id_ed25519` (ED25519, `SHA256:2WcJzGv8CpgQ3Ay5sMBoPjgYmrN5sQtaAGVMmLwe2cg`, comment `mckee8@gmail.com`) |
| Azure VM name | `dragon` |
| Resource group | `rg-dev-environment` |
| Region | `eastus` |
| Subscription | "Pay-as-you-go" (id redacted) |
| Tenant | `temckee8outlook.onmicrosoft.com` (id redacted) |

**Evidence it is the Dick's Laboratory target (not guessed):** dedicated ops
tooling `~/Documents/REPOs/cloud/azure/scripts/dragon-{up,down,status}.sh`
(wrapping `az vm start` / `az vm deallocate` on `rg-dev-environment/dragon`);
IaC `~/Documents/REPOs/cloud/azure/main.bicep` with `param vmName = 'dragon'`,
`adminUsername = 'temckee8'`, `id_ed25519.pub` as the provisioning key;
`robby` `~/.bash_history` shows repeated `ssh dragon` / `ssh temckee8@dragon`;
`robby` `~/.ssh/known_hosts` already carries `dragon`'s host keys.

**Disambiguation:** a second VM `weasel_den` exists (`Standard_B4ms`,
**Windows Server**, RG `TradingVM-RG`, eastus, deallocated) — that is the
K9/trading Windows box, **not** this target. The tailnet also lists a stale
Windows node `weasel-den` (offline 84 d) distinct from the `weasel` client
machine.

## AZ1.B — Robby → Azure SSH test

```
ROBBY SSH: INCONCLUSIVE
```

`ssh -o BatchMode=yes -o ConnectTimeout=12 dragon` → `ssh: connect to host
100.103.127.127 port 22: Connection timed out` (rc 255). **Cause: the VM is
currently deallocated and its Tailscale node is offline (last seen ~12 h ago)**
— not an auth or config fault. robby's client side is fully prepared (alias,
key, trusted host keys) and prior successful logins are evidenced
(`known_hosts` entries + `bash_history`). A live PASS cannot be asserted
without powering the VM on, which AZ1 forbids.

## AZ1.C — SSH host fingerprints

**Recorded on robby (`ssh-keygen -F 100.103.127.127`)** — to be re-confirmed
against the guest's own `/etc/ssh/*_key.pub` once the VM is up:

| Alg | SHA256 fingerprint |
|---|---|
| ED25519 | `SHA256:Ai0gLE1EfclvMCXsGEND18JvgcMm1g6LuddNI3ocEao` |
| RSA | `SHA256:GOaHj0YqlEZ7Z4bcH2ZJNHsbKLil3WyfEe6Q6i2QQos` |
| ECDSA | `SHA256:UIHlwBK/B/6cJRl5VyyU9syNZk3t1576o7pTTwHZ+no` |

No private key material inspected or recorded.

## AZ1.D — Azure guest identity

**NOT OBSERVED FROM GUEST** — VM deallocated; AZ1 forbids power-on. From the
control plane:

| Item | Value |
|---|---|
| Image | `Canonical : ubuntu-24_04-lts : server`, exact `24.04.202606060` → **Ubuntu 24.04 LTS** |
| OS type | Linux |
| Disk generation | Hyper-V **V2 (Gen2)** |
| VM `securityType` | `Standard` (not Trusted Launch) |
| Hostname / kernel / exact patch level / `systemd-detect-virt` | pending power-on (expected `microsoft`/`hyperv`) |
| VM created | 2026-06-14T04:16:07Z |

## AZ1.E — Azure IMDS identity

**NOT OBSERVED** (IMDS is queryable only from inside a running guest). From the
control plane (redacted):

| Item | Value |
|---|---|
| Environment | AzureCloud |
| VM name | `dragon` |
| Region | `eastus` |
| Availability zone | none (not zonal) |
| VM size | `Standard_B2ms` (2 vCPU, 8 GiB, burstable B-series) |
| Priority | standard (`priority: null` → **not Spot**) |
| Managed identity | SystemAssigned (principal id redacted) |
| Image publisher/offer/sku/version | `Canonical` / `ubuntu-24_04-lts` / `server` / `24.04.202606060` |
| Subscription / tenant / resource IDs | redacted |

## AZ1.F — CPU

**NOT OBSERVED FROM GUEST.** Expected from SKU: `Standard_B2ms` = **2 vCPU**,
burstable (baseline 60% ×2 vCPU sustained, 24 credits/hr, max bank 576),
`x86_64`, typically Intel (host-dependent). `lscpu` detail pending power-on.

## AZ1.G — Memory / swap

**NOT OBSERVED FROM GUEST.** SKU RAM = **8 GiB**. Swap configuration and any
Ubuntu-cloud default swapfile pending power-on (Azure Ubuntu marketplace images
typically ship **no swap**; the Azure Linux Agent can create one on the
resource disk if `ResourceDisk.EnableSwap=y`, default `n`).

## AZ1.H — Disks / filesystems

| Item | Value | Persistence |
|---|---|---|
| OS disk `dragon_disk1_bb48fd67…` | **StandardSSD_LRS**, **32 GiB** (per `main.bicep`; API size null while VM Reserved), ~100 MB/s cap, Gen2, no zones | **persistent managed** |
| Data disks | **none** (`storageProfile.dataDisks = []`) | — |
| Resource / temp disk | B2ms provides a temp disk (~16 GiB) — presence/mount pending power-on | **ephemeral — never place project data here** |
| Root FS type/size/usage, mountpoints | pending power-on | — |

**Storage is the binding constraint for this migration (see AZ1.AB / AZ1.AC).**

## AZ1.I — Network

| Item | Value |
|---|---|
| VNet | `dragon-vnet` `10.0.0.0/16` |
| Subnet | `default` `10.0.1.0/24` (NSG `dragon-nsg` attached at subnet level) |
| NIC | `dragon-nic`, private IP `10.0.1.4` (Dynamic), no accelerated networking (B-series), IP-forwarding off, no custom DNS |
| Public IP | **none** (no `publicIPAddresses` resource in the RG) |
| Reachability | **Tailscale (WireGuard) only** — tailnet `100.103.127.127` |
| Listening services (`ss`), primary iface name, default route, DNS | pending power-on |

## AZ1.J — Guest firewall

**NOT OBSERVED** (ufw/nft/iptables need the guest). Pending power-on.

## AZ1.K — Azure NSG visibility

Fully visible from the control plane (`az network nsg show dragon-nsg`):

| Rule | Dir | Access | Proto | Src | Dst port |
|---|---|---|---|---|---|
| `Allow-Tailscale-Direct` (prio 1000) | Inbound | Allow | UDP | `*` | `41641` |
| `AllowVnetInBound` (65000) | Inbound | Allow | * | VirtualNetwork | * |
| `AllowAzureLoadBalancerInBound` (65001) | Inbound | Allow | * | AzureLoadBalancer | * |
| `DenyAllInBound` (65500) | Inbound | Deny | * | `*` | * |
| (default outbound: VNet + Internet allow, DenyAll 65500) | Outbound | — | — | — | — |

**No inbound TCP 22 from the internet.** SSH is reachable only across the
tailnet (Tailscale sets up its own WireGuard path; UDP 41641 is the direct
port, with DERP relay over outbound 443 as fallback). This is a deliberate,
strong posture. `AZURE NSG: VERIFIED` for this VM (subscription-wide NSG survey
not performed — only this VM's path).

## AZ1.L — Effective SSHD security

**NOT OBSERVED** (`sshd -T` needs the guest). From IaC:
`linuxConfiguration.disablePasswordAuthentication = true` → password auth
expected off; `PermitRootLogin`, `MaxAuthTries`, `AllowUsers/Groups`, port,
`AuthenticationMethods` pending power-on.

## AZ1.M — Authorized-key inventory

**NOT OBSERVED** (`~/.ssh/authorized_keys` on the guest). Provisioned key
(from `main.bicep`) is robby's `~/.ssh/id_ed25519.pub`
(`SHA256:2WcJzGv8CpgQ3Ay5sMBoPjgYmrN5sQtaAGVMmLwe2cg`, `mckee8@gmail.com`),
installed at `/home/temckee8/.ssh/authorized_keys`. Whether any additional keys
have been added since is **unknown** until power-on. Fingerprint/ownership/perm
audit pending.

## AZ1.N — Multi-client SSH state

```
robby:   INCONCLUSIVE — configured & previously connected; VM deallocated now, cannot re-verify live (AZ1 no power-on)
robyn:   NOT YET TESTED — and NOT on the tailnet at all (no `robyn` peer); cannot be tested from robby
weasel:  NOT YET TESTED — Windows tailnet node `weasel` is online, but Claudine runs on robby and cannot drive weasel; Human must run the client-side check there
```

Same `~/.ssh/id_ed25519` is currently the only client identity in play (used by
robby). Target end-state = **one independent keypair per machine**
(robby / robyn / weasel), each authorized separately on `dragon`. Not created
in AZ1.

**Commands for Human to run later, from each of robyn and weasel** (read-only;
do NOT copy any private key between machines):

```bash
# 1. client public-key fingerprint (generate a per-machine key first if none):
#    ssh-keygen -t ed25519 -C "<machine>-to-dragon" -f ~/.ssh/id_ed25519_dragon
ssh-keygen -lf ~/.ssh/id_ed25519_dragon.pub          # or id_ed25519.pub

# 2. after the pubkey is authorized on dragon (AZ2) and dragon is powered on:
ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519_dragon \
    -o StrictHostKeyChecking=accept-new temckee8@100.103.127.127 \
    'echo OK $(hostname) $(date -u +%FT%TZ)'

# 3. server host-key verification — compare against AZ1.C / the guest's
#    /etc/ssh/*_key.pub captured during the closing AZ1 power-on:
ssh-keygen -F 100.103.127.127 -l
```

(Both robyn and weasel must first be joined to the tailnet — `robyn` is not a
member yet.)

## AZ1.O — Azure agent / cloud-init

**NOT OBSERVED** (`waagent` / `cloud-init status` need the guest). IaC shows a
`Microsoft.Azure.Extensions/CustomScript` VM extension `TailscaleBootstrap`
(installs Tailscale + `tailscale up`) and a `cloud-init.yaml` writing
`/etc/default/tailscaled`. waagent + cloud-init presumed present (marketplace
Ubuntu default); versions/status pending.

## AZ1.P — Time / NTP

**NOT OBSERVED FROM GUEST.** Azure Ubuntu images default to
`systemd-timesyncd` against Azure's PTP/host time; expected `synchronized: yes`.
`timedatectl` + timezone (expected `UTC`) pending power-on. Collector session
logic must be timezone-explicit (America/Chicago for CME) regardless of guest
tz — do not rely on guest local time.

## AZ1.Q — Boot history / failed services

**NOT OBSERVED FROM GUEST** (`journalctl --list-boots`, `systemctl
--failed`). Control-plane deployment history: `main` (bicep) 2026-06-14,
`Microsoft.AutomationAccount` 2026-06-14; no redeploys since. Last power
transition `ProvisioningState/succeeded` 2026-09-08T15:15:26Z; current
`PowerState/deallocated`.

## AZ1.R — Journald persistence

**NOT OBSERVED FROM GUEST.** Ubuntu 24.04 default is `Storage=auto` with
`/var/log/journal` **present** → effectively persistent. Confirm at power-on;
serious collection wants persistent postmortem history (do not change in AZ1).

## AZ1.S — Automatic update / reboot risk

**Guest-side NOT OBSERVED** (`unattended-upgrades`, apt timers). Ubuntu 24.04
ships `unattended-upgrades` enabled by default (security pocket; can trigger a
reboot only if `Unattended-Upgrade::Automatic-Reboot "true"`, which is `false`
by default). **Azure-side:** VM has no Azure Update Manager / patch-orchestration
config visible. Confirm `apt-daily*.timer`, `unattended-upgrades`,
`/etc/apt/apt.conf.d/50unattended-upgrades`, and `needrestart` behaviour at
power-on. → risk register.

## AZ1.T — Sleep / suspend behaviour

**NOT OBSERVED** (`systemctl status sleep.target …`). It is a headless server
VM — no lid, no GNOME power, no seat. **Do not port robby's laptop workarounds**
(`systemd-inhibit --what=sleep:idle` wrappers, lid-open requirement, GNOME
`sleep-inactive-ac-type`). One migration goal is to delete those assumptions.
Confirm `sleep.target`/`suspend.target` are inert (they are `static` and
`WantedBy` nothing by default on a server) at power-on.

## AZ1.U — Runtime tool inventory

**NOT OBSERVED FROM GUEST.** Nothing on the VM inventoried — pending power-on:
`python3`, `python`, `uv`, `git`, `gh`, `sqlite3`, `curl`, `jq`, `gcc` /
`build-essential`, `venv`. A fresh `Canonical ubuntu-24_04-lts:server` image
ships `python3 3.12`, `curl`, `git`; typically **no** `uv`, `gh`, `sqlite3`
CLI, `jq`, or compiler.

**robby baseline for AZ3 parity** (reference only):

| tool | robby |
|---|---|
| OS | Ubuntu 25.10, kernel 6.17.0-41 |
| python3 | 3.13.7 |
| uv | 0.10.4 |
| git | 2.51.0 |
| gh | 2.100.0 |
| sqlite3 | 3.46.1 |
| jq | 1.8.1 |
| curl | 8.14.1 |
| tailscale | 1.102.3 |

## AZ1.V — User / sudo state

**NOT OBSERVED FROM GUEST.** Admin user `temckee8` (from IaC), home
`/home/temckee8`, UID/GID/shell/sudoers pending. Azure marketplace VMs put the
admin user in a passwordless-sudo group (`sudo` / cloud-init `sudo: ALL=(ALL)
NOPASSWD:ALL`). **No dedicated non-login runtime/service account is known to
exist** — creating one is an AZ2/AZ3 item, not done here.

## AZ1.W — Copper repository state on Azure

**NOT OBSERVED FROM GUEST.**
```
COPPER REPO: UNKNOWN (pending power-on) — presumed NOT PRESENT
```
No clone will be created in AZ1. Verify likely paths (`~/copper`,
`~/Documents/REPOs/copper`, `/opt/copper`, `/srv/copper`) at power-on;
read-only report of branch/HEAD/origin/dirty if found, no `pull`/`fetch`.

## AZ1.X — Credential-configuration presence

**NOT OBSERVED FROM GUEST.** No credentials copied. Tastytrade / `.env` /
keyring presence on `dragon` pending power-on (absence is expected and is an
AZ2/AZ3 concern). No secret values will be printed at any phase.

**IaC secret-hygiene finding (separate `cloud` repo, not Copper):**
`~/Documents/REPOs/cloud/azure/main.bicep` embeds a Tailscale auth key in
cleartext inside the `TailscaleBootstrap` `commandToExecute`; `cloud-init.yaml`
carries a placeholder. Flag to the `cloud` repo owner (rotate the key, move to
a secure parameter / Key Vault). **Not modified in AZ1** (out of Copper scope).

## AZ1.Y — Existing Dick's Laboratory services

**NOT OBSERVED FROM GUEST** (`systemctl list-unit-files | grep -Ei
'dick|copper'`). No collector/timer/supervisor is known to exist on `dragon`;
confirm at power-on. On `robby` the H1F cleanup already removed all
`dicks-*` units.

## AZ1.Z — Azure CLI / control-plane visibility

```
Azure CLI:            PRESENT on robby (az 2.90.0, extension: automation 1.0.0b2)
control-plane session: AUTHENTICATED (user temckee8@outlook.com; no `az login` initiated)
```
Subscription "Pay-as-you-go" (id redacted), single account. All `az` usage in
AZ1 was read-only (`vm show`, `vm get-instance-view`, `resource list/show`,
`network …`, `disk show`, `automation runbook/schedule list`,
`deployment group list`, `account show`). No resource altered.

## AZ1.AA — Existing VM power schedule

**Observable from the control plane (authenticated `az`):**

| Mechanism | State |
|---|---|
| DevTestLab auto-shutdown `shutdown-computevm-dragon` | **ENABLED — daily 06:08 UTC**, 30-min email warning → `mckee8@gmail.com`, created 2026-06-14 |
| Auto-**start** schedule | **NONE.** Automation accounts `automation-dragon` and `automation-k9` each hold a Published `Start-Dragon` runbook, but `az automation schedule list` returns `[]` for both — no schedule attached. (Webhook enumeration unsupported by the installed CLI; a webhook-triggered start cannot be positively excluded, but none is scheduled.) |
| Logic Apps / Function Apps | none in the subscription |
| Manual ops | `robby:~/Documents/REPOs/cloud/azure/scripts/dragon-{up,down}.sh` → `az vm start` / `az vm deallocate` |
| `shutdown-computevm-weasel_den` | separate DevTestLab shutdown on the K9 Windows VM (TradingVM-RG) — not this target |

**Net:** the VM will auto-deallocate every day at **06:08 UTC (01:08 CT)** and
will **not** auto-start. `06:08 UTC` lands mid-Globex-overnight — this schedule
is incompatible with unattended collection and must be redesigned in AZ3 (not
touched in AZ1).

```
AZURE POWER SCHEDULE: PARTIALLY OBSERVABLE — auto-shutdown 06:08 UTC daily (enabled); no auto-start
```

## AZ1.AB — Preliminary host-capacity classification

```
AZURE HOST CAPACITY:
  compute + RAM : LIKELY ADEQUATE (burstable-credit caveat — verify under AZ4)
  storage       : LIKELY UNDERSIZED as provisioned (32 GiB OS disk, no data disk)
```

Evidence vs measured `robby` requirements (Attempt-3 / H1):

| Dimension | Need (measured on robby) | `dragon` (`Standard_B2ms`) | Verdict |
|---|---|---|---|
| CPU | very low average; bursts to ~40–150 trades/s at the 08:30 CT cash open; writer queue ≪ 50 000; sub-second persist lag | 2 vCPU burstable; baseline ~1.2 vCPU sustained, banked credits for bursts | ADEQUATE, but a multi-hour high-rate afternoon could draw down B-series credits — **must be watched in AZ4** |
| RAM | low-hundreds-MB working set; old 2.2 GB finalization spike **already fixed** (COUNT(*)) | 8 GiB | AMPLE |
| Disk throughput | modest sustained writes (~0.5 GB over a full trading date) | StandardSSD ~100 MB/s | ADEQUATE |
| Disk capacity | ~0.47–0.50 GB per active ES trading date | 32 GiB OS disk, ~20 GiB usable after OS/logs | **UNDERSIZED** — ~20 dates ≈ 1 month, then full; **needs a dedicated managed data disk** |

No resize performed or recommended as a reflex — the fix is a **data disk**,
not a bigger VM.

## AZ1.AC — Storage headroom

| Horizon | Dataset projection (~0.49 GB/date) | Fits in ~20 GiB usable OS-disk space? |
|---|---|---|
| 20 dates (~1 month) | ~9–10 GB | tight — yes, barely |
| 60 dates (~1 quarter) | ~28–30 GB | **no** |
| 250 dates (~1 year) | ~118–125 GB | **no** |

OS / logs / runtime overhead (Ubuntu + `uv` toolchain + journald + Copper repo)
is estimated at ~8–12 GB, i.e. the 32 GiB OS disk leaves ~20 GiB. **Provision a
persistent managed data disk (StandardSSD or PremiumSSD, 128–256 GiB)** mounted
at a stable path (e.g. `/data` or `/srv/dicks_laboratory`) for the SQLite
datasets **and** persistent journald before 0W-4. Keep raw datasets off the OS
disk and off any resource/temp disk.

## AZ1.AD — Azure-specific risk register

| # | Risk | Current evidence | Severity | Next-phase action |
|---|---|---|---|---|
| R1 | **Daily auto-deallocate at 06:08 UTC** kills any in-flight session | DevTestLab `shutdown-computevm-dragon` ENABLED, 06:08 UTC | **HIGH** | AZ3 — replace with a session-aware Sun→Fri power design; until then, disable or retime |
| R2 | **No auto-start** — VM stays off; a missed manual start = missed session (repeat of Attempt-4 class failure, different cause) | no schedule on `Start-Dragon`; start is manual (`dragon-up.sh`) | **HIGH** | AZ3 — scheduled/automated start aligned to Sunday pre-open (CT) |
| R3 | **OS-disk capacity** — ~1 month of datasets then full | 32 GiB OS disk, 0 data disks | **HIGH** | AZ2/AZ3 — attach + mount a persistent managed data disk |
| R4 | **Access is single-key, single-machine, Tailscale-only**; `robyn` not on the tailnet; no per-machine keys | one `id_ed25519` used by robby; tailnet peers robby/dragon/weasel only | **MED** | AZ2 — per-machine keypairs, join robyn to tailnet, authorize each separately |
| R5 | **Azure platform maintenance / redeploy** can reboot or move the VM with little notice | single VM, no zone, standard priority; Scheduled Events facility not yet used | **MED** | later hardening — `AZURE SCHEDULED EVENTS: CANDIDATE FOR LATER HARDENING` |
| R6 | **Automatic OS updates / `needrestart`** could restart services mid-session | Ubuntu 24.04 default `unattended-upgrades` (auto-reboot off by default) — unconfirmed on guest | **MED** | AZ1-close / AZ3 — confirm + set a maintenance window outside market hours |
| R7 | **Guest interior unverified** — tools, repo, journald, sshd, timers, sleep targets all unread because the VM is off | AZ1 could not power on the VM | **MED** | AZ1-close — one authorized brief power-on + read-only guest sweep |
| R8 | **Secret storage** on Azure undefined | no `.env`/keyring inspected; none copied | **MED** | AZ3 — Key Vault + managed identity, or root-owned mode-600 env file provisioned out-of-band |
| R9 | **Service ownership** — no dedicated runtime account, no system-level supervisor | admin user `temckee8` only; no `dicks-*` units on guest (unconfirmed) | **MED** | AZ3 — system-level `systemd` unit, dedicated `--no-create-home` service user |
| R10 | **Time-zone correctness** for CME session boundaries | guest tz expected UTC; collector must be tz-explicit | **LOW** | AZ3 — collector owns America/Chicago session logic; do not rely on guest local tz |
| R11 | **IaC secret in cleartext** (Tailscale auth key in `main.bicep`, separate `cloud` repo) | observed in `~/Documents/REPOs/cloud/azure/main.bicep` | **LOW** (not Copper) | flag to `cloud` repo owner — rotate + move to secure param |
| R12 | **B-series burst-credit exhaustion** under a long high-rate afternoon | `Standard_B2ms` burstable; robby bursts observed in H1B (156k trades/hr) | **LOW–MED** | AZ4 — watch CPU-credit metrics during the real verification run |
| R13 | **No boot diagnostics** configured → harder Azure-side postmortem | `diagnosticsProfile` empty | **LOW** | AZ2/AZ3 — enable managed boot diagnostics |

## AZ1.AE — Proposed Azure runtime architecture (proposal only — not implemented)

- **Power:** `dragon` runs continuously from **Sunday before the CME futures
  open through Friday after the CME futures close** (CT-aligned), deallocated
  over the weekend for cost. Power transitions owned by a deliberate,
  session-aware mechanism (candidate: Azure Automation `Start-Dragon` /
  `Stop-Dragon` runbooks on CT cron schedules, or an Azure-native scheduler) —
  **technology chosen in AZ3, not now.** Retire / retime the ad-hoc 06:08 UTC
  DevTestLab shutdown.
- **Supervision:** **system-level `systemd`** owns the collector / session
  supervisor. No GUI, no terminal ownership, no user-login dependency, no
  lid/suspend logic. `Restart=` policy + a session supervisor that opens/closes
  datasets on CME session boundaries.
- **Identity:** dedicated non-login service account; secrets via Azure Key
  Vault + the VM's SystemAssigned managed identity (fallback: root-owned
  mode-600 env file provisioned out-of-band). No secrets in the repo or in
  unit files.
- **Storage:** persistent managed **data disk** (StandardSSD/PremiumSSD,
  128–256 GiB) mounted at a stable path for SQLite datasets; persistent
  journald (`Storage=persistent`, `SystemMaxUse=` bounded). Never the OS disk
  for bulk data, never the resource/temp disk.
- **Source:** Git-backed Copper checkout, updated by an explicit deploy step
  (never auto-`pull` mid-session).
- **Session lifecycle:** owned by the collector / supervisor, tz-explicit
  (America/Chicago), independent of guest local time.
- **Resilience (later):** consume Azure Scheduled Events to drain/finalize a
  dataset ahead of a platform reboot/redeploy.

## AZ1.AF — Proposed next-phase sequence (refined)

```
0W-AZ1    Azure Host Inventory & Access Readiness            ── control-plane portion COMPLETE
0W-AZ1c   Guest-interior read-only sweep (one authorized     ── NEW: closes the guest half of AZ1
          brief power-on: identity, IMDS, CPU/mem/disk,
          network, sshd -T, authorized_keys, /etc/ssh
          host fingerprints, tool inventory, repo &
          credential presence, journald, timers, sleep
          targets, waagent/cloud-init) → power back off
        ↓
0W-AZ2    SSH / security / host bootstrap: per-machine       ── incl. join robyn to tailnet;
          keypairs (robby/robyn/weasel), authorize each         attach + mount persistent data disk;
          on dragon, sshd hardening, data disk, boot            resolve 06:08 UTC auto-shutdown
          diagnostics, service account
        ↓
0W-AZ3    Copper runtime + system-level systemd supervisor   ── secrets mechanism; persistent journald;
          + persistent data mount + Sunday→Friday power         deliberate CT-aligned power schedule
          schedule
        ↓
0W-AZ4    Short real collector verification (one bounded      ── watch B-series CPU credits, disk, writer
          session on Azure)
        ↓
0W-2 Att4 Formal gap-free full trading-date proof ON AZURE
        ↓
0W-4      2–3 day unattended soak ON AZURE
```

## AZ1.AG — Guest read-only sweep block (for 0W-AZ1c / Human)

Run once the VM is powered on; all read-only, no changes:

```bash
# identity + virt + time
hostnamectl; uname -a; cat /etc/os-release; systemd-detect-virt; arch
date; date -u; timedatectl

# IMDS (no install)
curl -s -H Metadata:true --noproxy '*' \
  "http://169.254.169.254/metadata/instance?api-version=2025-04-07" | python3 -m json.tool

# cpu / mem / disk
lscpu; nproc; free -h; sed -n '1,20p' /proc/meminfo; swapon --show
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,ROTA,PHY-SEC,LOG-SEC
df -hT; findmnt; mount | grep -Ev 'cgroup|proc|sysfs'
for d in /sys/block/sd*; do echo "$d $(cat $d/queue/scheduler) rota=$(cat $d/queue/rotational)"; done

# network
ip -br addr; ip route; resolvectl status | sed -n '1,25p'; ss -lntup

# guest firewall
sudo ufw status verbose 2>/dev/null; sudo nft list ruleset 2>/dev/null | head -40; sudo iptables -S 2>/dev/null

# sshd effective + host fingerprints
sudo sshd -T | grep -Ei '^(port|passwordauthentication|pubkeyauthentication|permitrootlogin|authenticationmethods|maxauthtries|x11forwarding|allowusers|allowgroups|kbdinteractiveauthentication)'
systemctl status ssh --no-pager | head -12
for k in ed25519 ecdsa rsa; do f=/etc/ssh/ssh_host_${k}_key.pub; [ -f "$f" ] && ssh-keygen -lf "$f"; done

# authorized keys (fingerprints only)
ls -la ~/.ssh; ssh-keygen -lf ~/.ssh/authorized_keys 2>/dev/null; awk '{print $NF}' ~/.ssh/authorized_keys

# agent / cloud-init
systemctl is-active walinuxagent waagent 2>/dev/null; (waagent --version 2>/dev/null || true)
cloud-init status --long

# boot / units / timers / sleep
systemctl get-default; systemctl --failed --no-pager
systemctl list-unit-files --state=enabled --no-pager | grep -Ei 'ssh|cron|unattended|apt|walinux|snap' 
journalctl --list-boots | tail -10
systemctl list-timers --all --no-pager
systemctl status sleep.target suspend.target hibernate.target --no-pager | grep -E 'Loaded|Active'
grep -Ri 'Automatic-Reboot' /etc/apt/apt.conf.d/ 2>/dev/null

# journald persistence
grep -E '^\s*Storage' /etc/systemd/journald.conf /etc/systemd/journald.conf.d/* 2>/dev/null; ls -ld /var/log/journal

# tools
for t in "python3 --version" "python --version" "uv --version" "git --version" "gh --version" \
         "sqlite3 --version" "curl --version" "jq --version" "gcc --version"; do printf '%-22s' "$t: "; eval "$t" 2>&1 | head -1; done
dpkg -l build-essential 2>/dev/null | tail -1

# user / sudo
id; echo "$HOME"; getent passwd "$USER"; sudo -n true 2>/dev/null && echo "passwordless sudo: yes" || echo "passwordless sudo: no/limited"

# copper repo + credential presence (no mutation, no secret printing)
for p in ~/copper ~/Documents/REPOs/copper /opt/copper /srv/copper; do
  [ -d "$p/.git" ] && { echo "== $p"; git -C "$p" rev-parse --abbrev-ref HEAD; git -C "$p" rev-parse HEAD; \
    git -C "$p" remote -v; git -C "$p" status --porcelain | head; }
done
for p in ~/copper/.env ~/Documents/REPOs/copper/.env /opt/copper/.env; do [ -e "$p" ] && ls -l "$p"; done

# existing lab units
systemctl list-unit-files | grep -Ei 'dick|copper'; systemctl --user list-unit-files 2>/dev/null | grep -Ei 'dick|copper'
```

---

## AZ1.AH — Files changed

| File | Change |
|---|---|
| `docs/dicks_laboratory/AZURE_COLLECTION_HOST_MIGRATION.md` | **new** (this document) — untracked, not committed |

No other file created or modified. No collector / production source touched.

## AZ1.AI — Git status

```
robby:  branch master
        HEAD ae6f33a6362e2e063eb2de5b8d19f72f7ee728d6  == origin/master
        working tree: only ?? docs/dicks_laboratory/AZURE_COLLECTION_HOST_MIGRATION.md
Azure:  no repo mutated (none confirmed present; VM off)
```

```
0W-AZ1: INCOMPLETE — control-plane inventory COMPLETE; guest-interior inventory
        BLOCKED because `dragon` is deallocated and AZ1 forbids powering it on.
        Closes with one authorized brief power-on (0W-AZ1c) running AZ1.AG.

AZURE CHANGES MADE: NONE
```

---

# Phase 0W-AZ1c — Guest-Interior Read-Only Inventory

**Run:** 2026-09-09 ~04:10–04:20 UTC, one authorized power-on of `dragon`,
read-only guest inspection over Tailscale SSH from `robby`, then explicit
`az vm deallocate`. **No persistent Azure or guest change.**

## HEADLINE FINDING — `dragon` is already a live production host

`dragon` is **not a spare VM** — it is the running **Copper / K9 options-trading
collection host**, with:

- the Copper repo checked out at `~/Documents/REPOs/copper` (branch `master`,
  HEAD `1c433e3`, clean, **3 commits behind** robby's `ae6f33a`);
- a live `.env` (Tradier + Tastytrade OAuth credentials, `600`, not read);
- **7 enabled `copper-k9-*` systemd timers** (system-level, CT-scheduled,
  run as user `temckee8`) driving XSP 0DTE dry-runs, morning checks, daily
  close, weekly reports, log compression;
- a **self-deallocation** job: `copper-k9-smart-shutdown.timer` @ **10:15 CT
  (15:15 UTC) Mon–Fri** runs `scripts/smart_shutdown.sh`, which uses the VM's
  managed identity (`az login --identity` → `az vm deallocate`) — skipped only
  if a `pts/` session is active;
- a matching **daily start ~10:46 UTC** (control-plane; exact trigger not
  enumerable with the installed `az automation` extension — an Automation
  schedule or webhook on the `Start-Dragon` runbook is the likely source);
- the DevTestLab `06:08 UTC` auto-shutdown is, per `smart_shutdown.sh`'s own
  comment, the **failsafe** behind the 10:15 CT primary stop.

**Net:** `dragon`'s current lifecycle is **~4.5 h/day, Mon–Fri, US-day-session
only** (up ~10:46 UTC → K9 jobs 12:55–15:15 UTC → self-deallocate 15:15 UTC).
This is **fundamentally incompatible** with the Laboratory's need for
**continuous Sunday-open → Friday-close** futures coverage, and the host is
**shared** with live options trading. Choosing `dragon` as the futures
collection host therefore forces one of:

1. **Re-home the Laboratory to a dedicated VM** (clean separation from K9;
   K9's cost/lifecycle assumptions untouched), or
2. **Rework `dragon`'s entire power lifecycle** to Sun→Fri continuous and make
   K9 + the futures collector co-tenants on one `Standard_B2ms` (changes K9's
   cost profile, retires `smart_shutdown.sh`, needs the 06:08 UTC failsafe
   removed/retimed).

This decision belongs to AZ2 and is now the central open question of the
migration. **`dragon` is the futures target implied by all existing tooling,
but AZ1c shows it is not a blank host.**

## AZ1c.A — Dragon power-on

| | |
|---|---|
| Mechanism | `az vm start -g rg-dev-environment -n dragon` (equivalent of `dragon-up.sh`; script unaltered) |
| Start | 2026-09-09 04:10:02 UTC |
| Azure result | rc 0; completed 04:11:15 UTC (~73 s) |
| Instance view | `PowerState/running` (provisioning succeeded 04:11:04 UTC) |
| Kernel boot | 2026-09-09 04:10:26 UTC; Tailscale peer online by 04:11:23 UTC; SSH usable on first attempt 04:11:27 UTC |

No scheduler created; auto-shutdown, VM size, disks, and networking untouched.

## AZ1c.B — Robby SSH live verification

```
ROBBY SSH: PASS
```

| | |
|---|---|
| Command | `ssh dragon` (alias → `temckee8@100.103.127.127`, `IdentityFile ~/.ssh/id_ed25519`) |
| Auth method | `publickey` (`ssh -v`: "Authenticated to 100.103.127.127 ([100.103.127.127]:22) using \"publickey\"") |
| Client key | ED25519 `SHA256:2WcJzGv8CpgQ3Ay5sMBoPjgYmrN5sQtaAGVMmLwe2cg` (`mckee8@gmail.com`) |
| Remote user | `temckee8` (uid 1000) |
| Transport | Tailscale (`100.103.127.127:22`), remote sshd `OpenSSH_9.6p1 Ubuntu-3ubuntu13.18` |
| Server host key offered | `ssh-ed25519 SHA256:Ai0gLE1EfclvMCXsGEND18JvgcMm1g6LuddNI3ocEao` — "known and matches" |

## AZ1c.C — Host-key verification

```
HOST KEY MATCH: PASS
```

Live `ssh-keyscan` of `dragon` and the guest's own `/etc/ssh/*_key.pub`
(labelled `root@dragon`) both match robby's recorded `known_hosts` **exactly**:

| Alg | SHA256 | robby known_hosts | live scan | guest /etc/ssh |
|---|---|:--:|:--:|:--:|
| ED25519 | `Ai0gLE1EfclvMCXsGEND18JvgcMm1g6LuddNI3ocEao` | ✓ | ✓ | ✓ |
| ECDSA | `UIHlwBK/B/6cJRl5VyyU9syNZk3t1576o7pTTwHZ+no` | ✓ | ✓ | ✓ |
| RSA | `GOaHj0YqlEZ7Z4bcH2ZJNHsbKLil3WyfEe6Q6i2QQos` | ✓ | ✓ | ✓ |

## AZ1c.D — Guest identity

| Item | Value |
|---|---|
| hostname | `dragon` (static; chassis `vm`, "Microsoft Corporation Virtual Machine", Hyper-V UEFI v4.1) |
| distribution | **Ubuntu 24.04.4 LTS** (Noble Numbat) |
| kernel | **6.17.0-1022-azure** (`#22-Ubuntu SMP Mon Jul 27 2026`), x86-64 |
| virtualization | `microsoft` (Hyper-V) |
| Machine ID | `fcf2fcde…` (redacted); Boot ID `7c9f72c1…` |

Matches the AZ1 control-plane image expectation (`Canonical:ubuntu-24_04-lts:server`,
exact `24.04.202606060`) — the running patch level is `24.04.4` with the
Azure-tuned kernel. ✔

## AZ1c.E — IMDS verification

`curl -s -H Metadata:true --noproxy '*' "http://169.254.169.254/metadata/instance?api-version=2025-04-07"`
returned (non-secret fields; IDs redacted):

| Field | Value | Matches AZ1 control plane? |
|---|---|:--:|
| `compute.name` | `dragon` | ✔ |
| `compute.location` | `eastus` | ✔ |
| `compute.vmSize` | `Standard_B2ms` | ✔ |
| `compute.priority` / `compute.evictionPolicy` | `` / `` (standard, not Spot) | ✔ |
| `compute.zone` | `` (none) | ✔ |
| `compute.osType` | `Linux` | ✔ |
| `compute.storageProfile.imageReference` | Canonical / `ubuntu-24_04-lts` / `server` / `24.04.202606060` | ✔ |
| `network` private IP | `10.0.1.4/24`, no public IP object | ✔ |

Subscription/tenant/resource IDs, `vmId`, and any identity token were not
recorded.

## AZ1c.F — Time / NTP

| Item | Value |
|---|---|
| Timezone | `Etc/UTC` (UTC, +0000) |
| Local == UTC | `2026-09-09 04:11:50 UTC` |
| Clock synchronized | **yes** |
| NTP service | **active** (`systemd-timesyncd`; chrony present, listening `127.0.0.1:323` — Azure PTP `/dev/ptp0` available) |
| RTC in local TZ | no |

Not changed. Collector remains timezone-explicit (America/Chicago) in code.

## AZ1c.G — CPU

| Item | Value |
|---|---|
| Logical CPUs | **2** (`0,1`) |
| Model | **Intel Xeon Platinum 8171M @ 2.60 GHz** (family 6, model 85, stepping 4 — Skylake-SP) |
| Threads/core · cores/socket · sockets | 1 · 2 · 1 |
| Flags of note | AVX-512 (f/dq/cd/bw/vl), AES, RDRAND, `hypervisor` |
| Caches | L1 64K/64K ×2, L2 2 MiB ×2, L3 35.8 MiB |
| Mitigations | several **"Vulnerable"** (Retbleed, Spec store bypass, MMIO stale data — "no microcode") — typical of this older Azure host generation; noise, not a project blocker |

## AZ1c.H — RAM / swap

| Item | Value |
|---|---|
| RAM total | **7.8 GiB** (`MemTotal 8 128 880 kB`) |
| Available | ~7.2–7.3 GiB (idle: 647 MB used) |
| Swap | **none** (`SwapTotal 0`, `swapon --show` empty) |
| Hugepages | 0 |

## AZ1c.I — Persistent OS disk

`sda` (Azure managed **StandardSSD_LRS**, "Virtual Disk", `ROTA=1` cosmetic,
scheduler `none`/`mq-deadline`, logical 512 / physical 4096):

| Partition | Size | FS | Mount |
|---|---|---|---|
| `sda1` | 31 GiB | ext4 | `/` (`rw,relatime,discard,errors=remount-ro,commit=30`) |
| `sda14` | 4 MiB | — | (BIOS-boot) |
| `sda15` | 106 MiB | vfat | `/boot/efi` |
| `sda16` | 913 MiB | ext4 | `/boot` |

**PERSISTENT.** Note `commit=30` on `/` (30 s ext4 commit interval vs the 5 s
default) — SQLite `fsync` on commit still protects durably-committed
transactions, but non-fsync'd writes have a wider loss window; worth a look in
AZ3.

## AZ1c.J — Temporary resource disk

| Item | Value |
|---|---|
| Device | `sdb` → `sdb1` |
| Size | **16 GiB** |
| Filesystem | ext4 |
| Mountpoint | **`/mnt`** (`rw,relatime`) |
| State | freshly re-created — `28K` used / 15 GiB free after this power-on |

```
/mnt (/dev/sdb1) — Azure EPHEMERAL resource disk — NOT SUITABLE FOR CANONICAL SQLITE DATA
```

Wiped on every deallocate/reallocate (confirmed empty right after this
power-on). Never place datasets, journald, or the repo here.

## AZ1c.K — Root filesystem usage

`/dev/root` (= `/dev/sda1`), ext4: **30 GiB total · 9.1 GiB used · 21 GiB free
· 31 %**. `/boot` 881 MiB (15 %), `/boot/efi` 105 MiB (6 %).

At ~0.49 GB per ES trading date, 21 GiB free ≈ **~40 dates raw** before the
root FS fills — but datasets must not live on the OS disk regardless (no
headroom for OS growth, logs, updates). **Confirms AZ1: a dedicated persistent
data disk is required before sustained collection / 0W-4.**

## AZ1c.L — Networking

| Interface | Address | Notes |
|---|---|---|
| `eth0` | `10.0.1.4/24` (DHCP), default via `10.0.1.1` | Azure private; DNS `168.63.129.16`, search `…bx.internal.cloudapp.net` |
| `tailscale0` | `100.103.127.127/32` + `fd7a:115c:a1e0::2138:7f80` | MagicDNS `100.100.100.100`, tailnet `taildb247e.ts.net` |
| special routes | `168.63.129.16` (Azure wireserver), `169.254.169.254` (IMDS) | via `eth0` |

Listening (`ss -lntup`): `sshd` on `0.0.0.0:22` + `[::]:22`; `tailscaled` UDP
`*:41641`; localhost-only `chrony :323`, `systemd-resolved :53`; plus
ephemeral tailscale ports on the tailnet IP. **No public IP exists; NSG
`DenyAllInBound` blocks internet 22.** → **SSH is reachable only over the VNet
and Tailscale** — confirmed by combined control-plane + guest evidence.

## AZ1c.M — Tailscale

| Item | Value |
|---|---|
| Version | **1.102.3** (same as robby) |
| Service | `tailscaled` active / running / enabled (started 04:10:37 UTC at boot) |
| dragon tailnet addr | `100.103.127.127` |
| Peers seen | `robby` (active, relay "ord"), `weasel` (Windows, active, relay "ord"), `weasel-den` (Windows, offline 84 d) — **no `robyn`** |
| Node health | healthy; enrolled and connected without intervention |

No `tailscale up/set/logout` run.

## AZ1c.N — Guest firewall

`ufw`: not inspected as changed — **inactive** is expected (no `ufw` rules;
Ubuntu default). `nft list ruleset` shows only Tailscale's own tables
(`ts-input`/`ts-forward`/`ts-postrouting` for `100.64.0.0/10` + `fd7a:115c:a1e0::/48`).
No host firewall restricting or exposing SSH beyond the NSG. No unexpected
inbound exposure. **No rules altered.**

## AZ1c.O — Effective SSHD settings

From `sudo sshd -T`:

| Key | Value | Note |
|---|---|---|
| `port` | 22 | |
| `passwordauthentication` | **no** | set by `50-cloud-init.conf` + `60-cloudimg-settings.conf` |
| `pubkeyauthentication` | yes | |
| `permitrootlogin` | **`without-password`** | key-based root login permitted → **AZ2: set `no`** |
| `kbdinteractiveauthentication` | no | |
| `maxauthtries` | 6 | |
| `authenticationmethods` | `any` | |
| `x11forwarding` | **yes** | needless on a headless server → AZ2 minor hardening |
| `permitemptypasswords` | no | |
| `allowusers` / `allowgroups` | (unset) | any local user with a key can log in → AZ2 could restrict |
| `clientaliveinterval` | 120 | |

No sshd change made.

## AZ1c.P — Authorized-key inventory

`~/.ssh` `700`, `~/.ssh/authorized_keys` `600`, owner `temckee8:temckee8`. **2
keys:**

| # | Fingerprint | Alg | Comment | Identity |
|---|---|---|---|---|
| 1 | `SHA256:2WcJzGv8CpgQ3Ay5sMBoPjgYmrN5sQtaAGVMmLwe2cg` | ED25519 | `mckee8@gmail.com` | **robby** (matches the expected fingerprint) |
| 2 | `SHA256:0OnoIpOb4a9jUH6hm7DDOqc3h1E5+y5G3dEXeZHrEnk` | ED25519 | `weasel` | **weasel** (Windows tailnet node) |

**Correction to an AZ1 assumption:** robby and weasel already use **separate
per-machine keys** — this is not a single shared key. What is missing is a
**robyn** key (and robyn is not on the tailnet). The guest also holds its own
outbound client key `~/.ssh/id_ed25519(.pub)` (not further inspected).

## AZ1c.Q — Azure agent / cloud-init

| Component | State |
|---|---|
| Azure Linux Agent | `walinuxagent.service` **active / enabled**; `WALinuxAgent-2.15.0.1` (Python 3.12.3); goal-state agent 2.16.0.2 |
| cloud-init | `/usr/bin/cloud-init 26.1-0ubuntu1~24.04.1`; `status: done`, no errors; `DataSourceAzure` |

Not re-run.

## AZ1c.R — Boot history / failed units

- Current boot: **2026-09-09 04:10:26 UTC** (this power-on). Uptime 2 min at first check.
- `journalctl --list-boots` + `last -x`: a **very regular Mon–Fri pattern** for the past ~2 weeks — **up ~10:46 UTC, down ~15:15 UTC** (≈4.5 h/day). No crash signatures — these are deliberate `az vm start` / `smart_shutdown.sh` deallocate cycles (see headline).
- `systemctl --failed`: **0 failed units.**
- `systemctl get-default`: **`graphical.target`** (unusual for a headless server — likely image default / VS Code Remote; harmless, AZ2 could switch to `multi-user.target`).

## AZ1c.S — Journald persistence

- `journald.conf` = `[Journal]` only → no explicit `Storage=` → default **`auto`**.
- `/var/log/journal/` **exists** (since 2026-06-14) → `auto` resolves to **persistent**.
- Current usage: **433.4 MB**.

```
JOURNALD: AUTO / PERSISTENT IN PRACTICE
```

Not altered.

## AZ1c.T — Automatic updates / reboot risk

| Item | State |
|---|---|
| `unattended-upgrades` | **enabled + active** |
| `/etc/apt/apt.conf.d/20auto-upgrades` | `Update-Package-Lists "1"`, `Unattended-Upgrade "1"` → daily auto security updates |
| `Unattended-Upgrade::Automatic-Reboot` | line **commented** in `50unattended-upgrades` → default **`false`** → **no automatic reboot** |
| `needrestart` | config not present → package default (may restart *services* during an unattended run, not the kernel) |
| Timers | `apt-daily.timer` next ~06:32 UTC, `apt-daily-upgrade.timer` next **~06:39 UTC (01:39 CT)**, `update-notifier-download.timer`, `motd-news.timer`, `fwupd-refresh.timer`, `fstrim.timer` (weekly Mon 00:44 UTC), `man-db.timer`, `e2scrub_all` (Sun 03:10 UTC) |

Under the *current* ~4.5 h/day lifecycle these mostly fire while the VM is
deallocated. Under a **Sun→Fri continuous** model, `apt-daily-upgrade` at
~01:39 CT would run **mid-Globex-session** every night → AZ3 must set a
maintenance window or disable it. Nothing disabled in AZ1c.

## AZ1c.U — Sleep / suspend

`sleep.target`, `suspend.target`, `hibernate.target` — all `static` and
`inactive (dead)`. `logind.conf` all defaults (headless, no seat, no lid).
**No idle-suspend behaviour of any kind.** Do **not** port robby's
`systemd-inhibit --what=sleep:idle` wrappers or GNOME power settings.

## AZ1c.V — Runtime tools

| Tool | Version | State |
|---|---|---|
| `python3` (system) | 3.12.3 | PRESENT (no `python` alias; no system `pip`) |
| `python3 -m venv` | — | PRESENT (`python3-venv` OK) |
| **`uv`** | **0.11.21** (`~/.local/bin/uv`) | **PRESENT** (user install; newer than robby's 0.10.4) |
| uv-managed CPython | **3.13.14** (`~/.local/bin/python3.13`) | PRESENT (matches robby's 3.13 line) |
| `git` | 2.43.0 | PRESENT |
| `sqlite3` | 3.45.1 | PRESENT |
| `curl` | 8.5.0 | PRESENT |
| `jq` | 1.7 | PRESENT |
| `gcc` | 13.3.0 | PRESENT |
| `az` | 2.88.0 | PRESENT + **authenticated** (same subscription/tenant, IDs redacted) |
| `gh` | — | **MISSING** |
| `make` / `build-essential` | — | **MISSING** (bare `gcc` only) |

The Copper runtime toolchain (`uv` + uv Python 3.13) is **already installed and
in production use by K9** — directly reusable for the Laboratory collector
(`dicks_lab_collect_es.py` needs no compiler; `gh` is not needed at runtime).

## AZ1c.W — Copper repository

| Item | Value |
|---|---|
| Path | `/home/temckee8/Documents/REPOs/copper` (221 MB; `.git` 4.2 MB) |
| Branch | `master` (`* master … [origin/master]`) |
| HEAD | **`1c433e3c429cebcfb3f6e41fe2298642a97a0ad1`** — "fix: use DXLink for Tastytrade underlying quotes" (2026-09-02) |
| origin | `git@github.com:bigmcdaddy8/copper.git` (fetch + push) |
| Working tree | **clean** (`git status --porcelain` empty) |
| Position vs robby | **3 commits behind** robby's `ae6f33a` (`c5be3ff`, `9f7cff5`, `ae6f33a` absent — `git cat-file -t ae6f33a` → "could not get object info"); dragon has not fetched since 2026-09-02 |
| `apps/` present | `K9`, `bic`, `captains_log`, `dicks_laboratory`, `encyclopedia_galactica`, `holodeck`, `trade_hunter`, `tradier_sniffer` |
| `apps/dicks_laboratory/data/` | **absent** — no futures dataset has ever been captured on `dragon` |

No `fetch` / `pull` / `checkout` / `reset` / `stash` / `clean` performed — read
only.

## AZ1c.X — Credential presence

| Path | State |
|---|---|
| `~/Documents/REPOs/copper/.env` | **present**, `-rw-------`, `temckee8:temckee8`, 1493 B, mtime 2026-07-30 |
| Key **names** (values redacted, not read) | `TRADIER_ACCOUNT_ID`, `TRADIER_SANDBOX_ACCOUNT_ID`, `TRADIER_API_KEY`, `TRADIER_SANDBOX_API_KEY`, `TRADIER_ENV`, `TW_SANDBOX_APP_NAME`, `TW_SANDBOX_CLIENT_*`, `TW_APP_NAME`, `TW_CLIENT_*`, `TW_ACCOUNT_NUMBER`, `TW_REFRESH_TOKEN` |
| `secret-tool` / user keyring | absent (no `~/.local/share/keyrings`) |

This is **K9's** live Tradier + Tastytrade config. The Tastytrade `TW_*` OAuth
material is the same family the futures collector's quote-token path needs — so
credential material for the Laboratory collector is **already on the host**
(as K9's `.env`). Whether the Laboratory reuses it or gets its own is an AZ3
decision. **No value read; nothing copied.**

## AZ1c.Y — Existing Copper / Dick's units

**System-level (`/etc/systemd/system`), all `enabled`, run as `temckee8`,
`OnCalendar=… America/Chicago`:**

| Timer | Schedule | Job |
|---|---|---|
| `copper-k9-tastytrade-entry-xsp.timer` | Mon–Fri 08:55 CT | XSP 0DTE broker dry-run |
| `copper-k9-morning-check.timer` | Mon–Fri 09:30 CT | morning check |
| `copper-k9-tastytrade-diagnostic.timer` | Mon–Fri 09:45 CT | Tastytrade diagnostic |
| `copper-k9-smart-shutdown.timer` | **Mon–Fri 10:15 CT** | **`smart_shutdown.sh` → `az vm deallocate`** |
| `copper-k9-daily-close.timer` | Mon–Fri 07:15 CT | daily close reconciliation |
| `copper-k9-weekly-flow-report.timer` | Mon 07:00 CT | weekly flow report |
| `copper-k9-compress-logs.timer` | Fri 07:18 CT | log compression |

Template unit `copper-k9-job@.service` (`Type=oneshot`, `User=temckee8`,
`WorkingDirectory=…/copper`, `ExecStart=bash scripts/run_k9_scheduled_job.sh %i`)
+ slice `system-copper\x2dk9\x2djob.slice`.

**No futures / `dicks_lab` / ES collector unit exists** — the ES collector
*code* is in the checkout but has never been scheduled or run on `dragon`.
Nothing started or stopped.

## AZ1c.Z — Current VM power-shutdown context

`scripts/smart_shutdown.sh` (in the repo): at **10:15 CT** it `az login
--identity` (VM SystemAssigned managed identity — the `smart_shutdown.sh`
comment states the MI holds *Virtual Machine Contributor on dragon*; a
read-only `az role assignment list` from the guest returned `[]`, i.e. the
directory read was not permitted from here, so the exact role could not be
independently confirmed) then `az vm deallocate --no-wait` — **unless** a
`pts/` session is active, in which case it defers to "the 01:08 AM
Auto-Shutdown failsafe" (the DevTestLab `06:08 UTC` schedule, re-confirmed
still `Enabled`, `time 0608`, `zone UTC`). **Not changed.** Still classified
**HIGH-RISK / INCOMPATIBLE** with Sun→Fri collection.

## AZ1c.AA — Refined capacity assessment (guest evidence)

| Dimension | Verdict | Guest evidence |
|---|---|---|
| **CPU** | **WATCH** | 2 × Xeon 8171M @ 2.6 GHz, burstable B2ms. Idle load 0.13. Fine on average; the concern is B-series credit draw-down over a multi-hour high-rate afternoon (H1B saw 156k trades/hr) **plus** co-tenancy with K9's morning jobs. Confirm with CPU-credit metrics in AZ4. |
| **RAM** | **LIKELY ADEQUATE** | 7.8 GiB, no swap, 647 MB used idle. Collector working set is low-hundreds-MB; the old 2.2 GB finalization spike is fixed. Ample even shared with K9. **Consider adding a small swapfile** (data disk) as a safety margin given zero swap. |
| **DISK THROUGHPUT** | **LIKELY ADEQUATE** | StandardSSD ~100 MB/s ≫ ~0.5 GB written per trading date. `commit=30` on `/` noted. |
| **DISK CAPACITY** | **PROBLEM (as provisioned)** | 21 GiB free on a 32 GiB OS disk, **no data disk**. ~40 dates raw, but datasets must not live on the OS disk. **A dedicated persistent data disk is mandatory before 0W-4.** |

Guest reality **does not contradict** the AZ1 control-plane conclusions — it
sharpens them and adds the co-tenancy + power-lifecycle findings.

## AZ1c.AB — Recommended persistent data-disk size

**Recommend 256 GiB** (StandardSSD_LRS), mounted at a stable path
(e.g. `/data` or `/srv/dicks_laboratory`), holding SQLite datasets, retained
forensic captures, and — optionally — a relocated persistent journald and a
small swapfile.

| Horizon | ES datasets (~0.49 GB/date) | + logs / forensic snapshots / FS overhead / 2nd instrument later | Fits 128 GiB? | Fits 256 GiB? |
|---|---|---|---|---|
| 60 dates (~1 qtr) | ~30 GB | ~45–55 GB | yes | yes |
| 130 dates (~½ yr) | ~64 GB | ~95–115 GB | marginal | yes |
| 250 dates (~1 yr) | ~120 GB | ~160–200 GB | **no** | yes (≈75–80 % full) |

128 GiB covers ~1–2 quarters with headroom; **256 GiB gives ~a year** plus
room for a second instrument, forensic retention (H1B alone was ~0.5 GB), and
comfortable free-space margin. Cost delta is small at StandardSSD rates. **Do
not attach in AZ1c** — AZ2/AZ3.

## AZ1c.AC — Refined SSH multi-client plan

Live `authorized_keys` shows **robby** and **weasel** already present as
**distinct** ED25519 keys. AZ2 work:

| Machine | Current state | AZ2 action |
|---|---|---|
| **robby** | key `SHA256:2WcJz…we2cg` authorized; SSH PASS today | keep; optionally re-issue a dedicated `*-to-dragon` key so `id_ed25519` isn't dual-purposed |
| **weasel** | key `SHA256:0OnoI…rEnk` (comment `weasel`) authorized; Windows tailnet node online; **not verified from weasel this phase** | Human runs the client-side verification from weasel (block in AZ1.N); confirm host fingerprint against AZ1c.C |
| **robyn** | **no key; not a tailnet member** | enrol robyn in the tailnet **first**, then generate a dedicated robyn keypair and authorize its public key on `dragon` |

Model stays: **one independent keypair per machine**, each authorized
separately. No key added in AZ1c.

## AZ1c.AD — Security findings carried forward

1. **Tailscale auth key in plaintext** in `~/Documents/REPOs/cloud/azure/main.bicep`
   (`TailscaleBootstrap` `commandToExecute`) and placeholder in
   `cloud-init.yaml` — **not touched** (separate `cloud` repo). The live
   Tailscale node on `dragon` is **healthy and already enrolled** (the key is
   a one-time enrolment key), but it is still a live secret committed to a
   repo. **AZ2:** rotate/revoke the exposed key; replace the plaintext IaC
   embedding with a secure parameter / Key Vault reference. Key not printed.
2. **`PermitRootLogin without-password`** and **`X11Forwarding yes`** on
   `dragon`'s sshd — AZ2 hardening (`PermitRootLogin no`, disable X11
   forwarding, consider `AllowUsers`).
3. **VM `securityType Standard`** (not Trusted Launch / no vTPM+SecureBoot at
   the VM level) — acceptable, note for AZ2 if a rebuild is ever on the table.
4. **`/` mounted `commit=30`** — wider non-fsync write-loss window; review for
   the collector's durability model in AZ3.

## AZ1c.AE — Migration document update

This section (0W-AZ1c) appended to
`docs/dicks_laboratory/AZURE_COLLECTION_HOST_MIGRATION.md`. Evidence layers are
kept distinct: **AZ1 = control-plane**, **AZ1c = guest interior**. Remaining
assumptions (all now small): exact daily *start* trigger for `dragon`
(Automation schedule vs webhook — not enumerable with the installed `az
automation` extension); managed-identity role name (MI works, name not
readable from the guest). **No commit.**

## AZ1c.AF — Dragon deallocation

| | |
|---|---|
| Mechanism | `az vm deallocate -g rg-dev-environment -n dragon` (equivalent of `dragon-down.sh`) |
| Start | 2026-09-09 04:2x UTC (see handoff for exact) |
| Result | rc 0 |
| Final instance state | `PowerState/deallocated` (re-verified via `az vm get-instance-view`) |

A guest `sudo shutdown` was **not** used — Azure `PowerState/deallocated` is
the required end state, restoring the pre-AZ1c cost/power baseline.

## AZ1c.AG — Azure baseline reconciliation (post-deallocation)

| Property | AZ1 baseline | After AZ1c |
|---|---|---|
| VM size | `Standard_B2ms` | unchanged |
| OS disk | 1 × StandardSSD_LRS 32 GiB | unchanged |
| Data disks | none | none |
| NIC / private IP | `dragon-nic`, `10.0.1.4` Dynamic, no public IP | unchanged |
| NSG `dragon-nsg` | UDP 41641 allow + Azure defaults | unchanged |
| Public IP | none | none |
| DevTestLab auto-shutdown | Enabled, 06:08 UTC | unchanged |
| Scheduled auto-start | none found | none found |
| Power state | deallocated | **deallocated** (returned) |

Only a temporary power-on/off cycle occurred.

## AZ1c.AH — Files changed

| File | Change |
|---|---|
| `docs/dicks_laboratory/AZURE_COLLECTION_HOST_MIGRATION.md` | AZ1c section appended — still **untracked, not committed** |

No source/test changes on robby. No guest file modified.

## AZ1c.AI — Git status

```
robby:  master @ ae6f33a6362e2e063eb2de5b8d19f72f7ee728d6  == origin/master
        working tree: only  ?? docs/dicks_laboratory/AZURE_COLLECTION_HOST_MIGRATION.md
dragon: repo NOT mutated — master @ 1c433e3, clean, no fetch/pull/checkout/reset
```

## AZ1c.AJ — AZ1 closure decision

```
0W-AZ1: ACCEPTANCE READY — CONTROL PLANE + GUEST INVENTORY COMPLETE
```

with the material finding that **`dragon` is a live, shared K9 production host
on a ~4.5 h/day Mon–Fri lifecycle** — the dedicated-VM-vs-re-home-dragon
decision is now the first task of AZ2.

```
AZURE PERSISTENT CHANGES MADE: NONE
TEMPORARY VM POWER-ON/DEALLOCATION: COMPLETE
```

---

# Phase 0W-AZ2A — Dragon 26.04.1 Rebuild & Futures-Host Conversion Plan

**Design / preservation / rebuild-planning only.** Nothing on `dragon`, K9, or
Azure was changed. No billable resource created. Read-only Azure inspection
only. Ends with a plan and an explicit Human approval request.

Run 2026-09-09 from `robby` (already-authenticated `az` 2.90.0).

## AZ2A.1 — Prior-phase closure

```
0W-AZ1  : ACCEPTED / CLOSED
0W-AZ1c : ACCEPTED / CLOSED
```

All AZ1 / AZ1c findings stand as historical evidence.

**Current `dragon` (unchanged):**

| | |
|---|---|
| VM | `dragon` (`rg-dev-environment`, `eastus`) |
| OS | Ubuntu 24.04.4 LTS, kernel 6.17.0-1022-azure |
| SKU | `Standard_B2ms` — 2 vCPU / 8 GiB |
| OS disk | 32 GiB StandardSSD_LRS (`dragon_disk1_bb48fd67…`), Gen2 |
| Data disks | none |
| Network | `dragon-nic` priv `10.0.1.4` (Dynamic) · `dragon-vnet` 10.0.0.0/16 · subnet `default` 10.0.1.0/24 · NSG `dragon-nsg` (inbound: UDP 41641 only) · **no public IP** · Tailscale `100.103.127.127` |
| Managed identity | SystemAssigned, principal `da55ad8d…` (redacted) |
| Copper | present, `~/Documents/REPOs/copper` @ `1c433e3`, clean |
| K9 | 7 enabled `copper-k9-*` timers + self-deallocate 10:15 CT; lower priority |
| Futures collection | not deployed; no `apps/dicks_laboratory/data/` on host |
| Power state | **deallocated** |

## AZ2A.2 — New host decision (recorded)

```
HOST                     : dragon
ROLE AFTER CONVERSION    : primary Dick's Laboratory futures collection host
K9                       : preserved (definitions kept) but PAUSED
OS TARGET                : Ubuntu 26.04.1 LTS (Canonical official Azure Server image, AMD64, Gen2)
MIGRATION METHOD         : CLEAN REBUILD
```

**Superseded (kept for history, not deleted):**

- *Dedicated-new-VM* proposal (AZ1c "re-home the Laboratory to a dedicated VM")
  → **SUPERSEDED** by Human decision to use `dragon`.
- *In-place `do-release-upgrade` of the 24.04 install* → **SUPERSEDED** by the
  Product Owner "clean rebuild" decision.

Prior reasoning is retained in the AZ1c section above.

## AZ2A.3 — Exact Ubuntu 26.04 Azure image (read-only)

`az vm image list --publisher Canonical --offer ubuntu-26_04-lts --sku server --all`
(eastus):

| Property | Value |
|---|---|
| Publisher | `Canonical` |
| Offer | `ubuntu-26_04-lts` |
| SKU | `server` (Gen2, AMD64) — *not* `server-gen1`, `server-arm64`, `server-cvm`, `pro-server`, or `*-daily` |
| Architecture | **x64 (AMD64)** |
| Hyper-V generation | **V2 (Gen2)** |
| Image `features` | `SecurityType = TrustedLaunchSupported`, `IsAcceleratedNetworkSupported = True`, `DiskControllerTypes = SCSI, NVMe`, `IsHibernateSupported = True` |
| `disallowed` | `vmDiskType = Unmanaged` (managed disks only — we comply) |
| `automaticOSUpgradeSupported` | false (normal for a marketplace image) |

**Stable `server` versions currently published** (Azure image "version" =
Canonical build date `YYYYMM.DD` form, *not* the `26.04.x` point-release label):

```
26.04.202604210  26.04.202605080  26.04.202606210  26.04.202607100
26.04.202607140  26.04.202607220  26.04.202608080  26.04.202608210
26.04.202608310  26.04.202609020   ← newest as of 2026-09-09
```

`Canonical:ubuntu-26_04-lts:server:latest` currently **resolves to
`26.04.202609020`** (built 2026-09-02).

**On "26.04.1":** the Azure marketplace does not expose the `.1` point-release
label — it ships rolling build-dated images in the same `server` SKU. The
26.04 GA image line began `26.04.202604210` (2026-04-21 build). A build dated
2026-09-02 is well past the normal first-point-release window and contains
26.04.1 content **plus** all archive updates through early September. The exact
`VERSION="26.04.x LTS"` string is only readable from `/etc/os-release` inside a
running guest (as with AZ1c, where control-plane said "24.04 / server /
`24.04.202606060`" and the guest reported `24.04.4`). So:

- **Confirmed:** official Canonical image, `ubuntu-26_04-lts:server`, **AMD64**,
  **Gen2**, **Trusted Launch supported**.
- **To pin:** `Canonical:ubuntu-26_04-lts:server:26.04.202609020` (or whatever
  is the newest stable `server` version at AZ2C execution time). Record the
  chosen version in the IaC and in the first dataset's provenance. **Do not
  deploy from `:latest`** (the current `dragon` VM uses `:latest`, which is
  exactly the non-reproducibility we are removing).
- The guest's `/etc/os-release` `VERSION` must be captured in AZ2C and is
  expected to read `26.04.1 LTS` or later.

## AZ2A.4 — B2ms / Gen2 / Trusted Launch compatibility

| Question | Finding |
|---|---|
| B2ms runs Gen2 Ubuntu 26.04? | **Yes** — the current `dragon` already runs a Gen2 image on B2ms; the 26.04 `server` SKU is Gen2. |
| Trusted Launch on B2ms + this image? | **Yes** — B-series v1 (incl. `Standard_B2ms`) supports Trusted Launch; the 26.04 `server` image advertises `TrustedLaunchSupported`. (The `az vm list-skus` capability dump timed out repeatedly under the CLI here; this rests on the image feature flag + the documented B-series capability and must be reconfirmed at AZ2C by `az vm create --security-type TrustedLaunch` succeeding, or a portal check.) |
| Secure Boot + vTPM | Available with Trusted Launch; recommend **both on**. |
| Accelerated networking | Not on B-series (image supports it, SKU does not) — irrelevant. |
| Availability zone | `dragon` is currently non-zonal; keep non-zonal (single VM, weekend-off model). |
| Current `dragon` security type | `Standard` (no Trusted Launch, no vTPM) — the rebuild is the moment to fix this. |

**SKU decision:** `Standard_B2ms` **KEEP** for the rebuild. Prove capacity
under AZ4 before any resize. B2ms Linux retail (eastus) ≈ **$0.0832/hr**
(~$43/mo at the Sun→Fri ~120 h/week schedule; ~$61/mo if left 24×7).

## AZ2A.5 — Clean-rebuild rationale (record)

### Advantages
- Known-clean OS baseline; **exact pinned** 26.04 image (removes today's
  `:latest` non-reproducibility).
- Sheds accumulated 24.04 package/config drift accumulated during the K9 era.
- Does not carry forward K9 scheduling, `smart_shutdown.sh`, or the
  ~4.5 h/day Mon–Fri lifecycle assumptions.
- Clean SSH baseline (`PermitRootLogin no`, `X11Forwarding no`, key-only).
- Corrected Tailscale bootstrap (no plaintext auth key in IaC — see AZ2A.L).
- Enables **Trusted Launch + Secure Boot + vTPM**.
- Clean disk/mount semantics — a purpose-made `/srv/dicks_laboratory` data
  mount with `fail-closed` collector startup, and no inherited `commit=30` on
  `/` unless deliberately re-accepted.
- Simple forensic provenance: this host begins life as **futures-host
  generation 1**.

### Costs / consequences
- OS disk is replaced (old one retained for rollback — see AZ2A.Y).
- Tailscale node re-enrolls; **SSH server host keys change** → every client's
  `known_hosts` for `dragon` becomes legitimately stale (managed in AZ2A.M).
- VM resource recreated → **new SystemAssigned MI principal**; current RBAC
  does **not** carry over (by design — see AZ2A.U).
- K9 host configuration must be reconstructed from preserved definitions if/when
  K9 resumes.
- `~/.../copper/.env` must be preserved out-of-band and restored (AZ2A.T).
- Existing Azure operational state (DevTestLab schedule, Automation VM-Contributor
  grants) must be inventoried and explicitly cleaned (AZ2A.K / AZ2A.U / AZ2A.31).

## AZ2A.6 — Recommended Azure rebuild mechanism

**Audit of existing IaC (`~/Documents/REPOs/cloud/azure/`, repo `cloud` @
`ecd6723`, read-only):**

| File | State |
|---|---|
| `main.bicep` | targets `dragon`, `Standard_B2ms`, `Canonical:ubuntu-24_04-lts:server:latest`, 32 GiB StandardSSD OS disk, `adminUsername temckee8`, `disablePasswordAuthentication true`. **Also declares a Standard Static Public IP `dragon-pip` + NIC public-IP config** and a `TailscaleBootstrap` CustomScript with a **plaintext `tskey-auth-…`**. |
| Live drift | the running deployment has **no public IP** and the NIC has no public config → `main.bicep` is **stale** vs reality. |
| `deploy_bicep_timeplate.sh` | passes `~/.ssh/id_rsa.pub` — stale (robby uses ed25519). |
| `bootstrap_tailscale.sh` / `startup_tailscale.sh` | reference `dev-ubuntu-vm` (old name) — stale. |
| `deploy_weasel.sh` | **contains a hardcoded Windows admin password and a second plaintext `tskey-auth-…`** (separate `weasel_den` VM). |

The IaC as written is **not safe to redeploy unmodified** (would re-add a
public IP, embed a plaintext key, and use `:latest`).

**Options evaluated:**

| | Mechanism | Verdict |
|---|---|---|
| A | `az vm delete dragon` (leaves OS disk + NIC + all network), then `az vm create` re-using **`dragon-nic`**, a **new pinned-26.04 OS disk**, `--security-type TrustedLaunch`, `--os-disk-size-gb 64`, `--attach-data-disk` (new 256 GiB), same `adminUsername`/key | **RECOMMENDED** |
| B | OS-disk swap on the existing VM object (`az vm update --os-disk`) | Rejected — cannot cleanly gain Trusted Launch, carries VM-object drift, no clean-provenance benefit |
| C | Full corrected-Bicep redeploy of the whole RG | Rejected for now — RG also holds K9-adjacent + Automation resources; whole-RG deployment is higher-blast-radius than needed. A **scoped** corrected Bicep limited to the `dragon` VM + data disk is acceptable as the implementation of option A. |

**Recommendation — Option A, implemented via a small corrected Bicep/CLI
module scoped to the VM + disks only:**

- keep `dragon-nic`, `dragon-vnet`, subnet `default`, `dragon-nsg` **as-is**
  (already correct: no public IP, inbound UDP 41641 only);
- **snapshot the current OS disk** *(or simply retain it — see AZ2A.Y)* for rollback;
- `az vm delete -g rg-dev-environment -n dragon --yes` (does **not** delete the
  OS disk by default → old disk becomes the rollback artifact);
- `az vm create -g rg-dev-environment -n dragon --nics dragon-nic
  --image Canonical:ubuntu-26_04-lts:server:26.04.2026NNNN
  --size Standard_B2ms --security-type TrustedLaunch --enable-secure-boot true
  --enable-vtpm true --os-disk-size-gb 64
  --storage-sku os=StandardSSD_LRS
  --admin-username temckee8 --ssh-key-values <robby.pub> <weasel.pub> [<robyn.pub>]
  --data-disk-sizes-gb 256 --data-disk-caching None
  --custom-data <cloud-init with NO secret>`
  then enrol Tailscale via `az vm run-command` with a **short-lived** auth key
  passed at run time (never stored) — see AZ2A.L.

Requirements satisfied: name stays `dragon`; no public IP; NSG unchanged; new
pinned OS image; Trusted Launch; data disk present from first boot; rollback =
retained old OS disk.

## AZ2A.7 — Resource / identity survival matrix (Option A)

| Resource / identity | Survives? | Changes? | Action required |
|---|:--:|:--:|---|
| VM name `dragon` | ✔ | no | reuse exact name |
| Azure VM **resource ID** | ✔ (same name+RG ⇒ same ID) | no | — but see DevTestLab/Automation rows |
| SystemAssigned **MI principal** | �’ new object | **yes — new principalId** | do **not** restore old RBAC; grant least-privilege (ideally none) — AZ2A.U |
| `dragon-nic` | ✔ | no | pass `--nics dragon-nic` to `az vm create` |
| Private IP `10.0.1.4` | ✔ | no (NIC retained) | — |
| `dragon-vnet` / subnet `default` | ✔ | no | untouched |
| `dragon-nsg` | ✔ | no | untouched (already correct) |
| Public IP | ✔ (still none) | no | keep none |
| **OS disk** | replaced | **yes — new disk** | retain old `dragon_disk1_bb48fd67…` as rollback; delete after acceptance |
| Data disk | n/a → created | **new** | 256 GiB StandardSSD_LRS, billable — AZ2A.19 approval |
| Boot diagnostics | currently none | add | enable managed boot diagnostics at create — AZ2A.X |
| DevTestLab `shutdown-computevm-dragon` | ✔ (targets VM by resource ID; **re-binds to the recreated VM**) | no | **must be explicitly deleted/disabled** — it is a K9-era 06:08 UTC failsafe incompatible with Sun→Fri — AZ2A.31 |
| Automation VM-Contributor grants at VM scope (SPs `6d277e79…`, `563c2651…`) | ✔ (scoped to resource ID) | no | review: keep the one used for the **Sunday start** automation; the K9 **stop** path is retired — AZ2A.U / AZ2A.27 |
| `automation-dragon` / `automation-k9` accounts + `Start-Dragon` runbooks | ✔ | no | repurpose `Start-Dragon` for the Sunday start; add a `Stop-Dragon` for Friday — AZ2A.27 |
| Tailscale node identity / IP | �’ | **likely new node + possibly new 100.x IP** | re-enrol as fresh node (AZ2A.L); update `~/.ssh/config` + clients only after fingerprint verification |
| **SSH host keys** | ✗ | **yes — regenerated on first boot** | capture new fingerprints from a trusted path; update every client `known_hosts` after independent verification — AZ2A.M |
| `authorized_keys` | ✗ (new OS disk) | rebuilt from `az vm create --ssh-key-values` | provide robby + weasel (+ robyn) public keys at create time — AZ2A.M |
| Copper repo checkout | ✗ | fresh clone | `git clone` on the new host; verify `HEAD == origin/master`, clean — AZ2A.S |
| `.env` | ✗ | restore from secure backup | out-of-band preserve + restore, `600`, `temckee8` — AZ2A.I / AZ2A.T |
| K9 systemd units | ✗ | not reinstalled | preserve definitions to the repo/doc; leave **NOT INSTALLED** post-rebuild — AZ2A.J |
| K9 logs / data | ✗ (on old OS disk) | preserved only via retained old OS disk / backup bundle | copy `~/.../copper/logs/K9` into the preservation bundle — AZ2A.H |

## AZ2A.8 — K9 preservation inventory

| Item | Git-backed / reproducible? | Action before rebuild |
|---|---|---|
| `scripts/run_k9_scheduled_job.sh`, `scripts/smart_shutdown.sh`, `scripts/k9_*` | **Yes** (in `origin/master`) | none — already durable |
| `apps/K9/**` source | **Yes** | none |
| `/etc/systemd/system/copper-k9-*.{timer,service}` + `copper-k9-job@.service` + slice | **host-local** (generated, not in repo) | **capture verbatim** into `docs/dicks_laboratory/` (or a `deploy/k9/` dir) as a non-secret preservation manifest |
| Timer schedules (07:00–10:15 CT set) | host-local | recorded in AZ1c.Z; copy exact `OnCalendar=` lines into the manifest |
| `~/.../copper/logs/K9/**` (operational logs incl. `smart_shutdown_*.log`) | **host-local** | copy into the backup bundle (non-secret; keep out of Git — size/noise) |
| `~/.../copper/.env` | **host-local, SECRET** | secure backup bundle only — AZ2A.I |
| `~/.ssh/authorized_keys` (2 keys) | fingerprints in AZ1c.P; bodies host-local | re-provision from client public keys, not from the old file |
| SSH client pubkey fingerprints (robby/weasel) | recorded (AZ1c.P) | already durable in this doc |
| Tailscale node config (`/var/lib/tailscale/tailscaled.state`) | host-local, SECRET-ish | **do not preserve** — re-enrol fresh (AZ2A.L) |
| Azure MI / RBAC facts | control-plane | recorded in AZ2A.U |
| Azure network / NSG defs | control-plane + stale bicep | recorded in AZ2A.1 / AZ2A.6 |

## AZ2A.9 — Sensitive-state preservation plan

Only real secret to preserve: **`~/Documents/REPOs/copper/.env`** (1493 B,
`600`, Tradier + Tastytrade `TW_*` incl. `TW_REFRESH_TOKEN`). Near-term
decision: **preserve and restore as-is** (do not redesign secrets management
during the OS rebuild).

**Recommended smallest safe method — encrypted local backup on robby:**

```
on dragon (pre-rebuild):
  gpg --symmetric --cipher-algo AES256 -o /tmp/dragon-env.gpg ~/Documents/REPOs/copper/.env
  sha256sum /tmp/dragon-env.gpg
robby: scp dragon:/tmp/dragon-env.gpg  ~/secure/dragon-env-YYYYMMDD.gpg   (mode 600, outside any repo)
dragon: shred -u /tmp/dragon-env.gpg
verify: sha256 matches on both ends
```

- Passphrase chosen by Human, entered interactively, never written down in
  chat/doc/repo.
- Alternative (heavier, deferred): a dedicated **Azure Key Vault** in
  `rg-dev-environment` with the `.env` as a secret and the rebuilt VM's MI
  granted `get` on that one secret. Cleaner long-term; **not** adopted for
  AZ2B — revisit in AZ3 hardening.
- **Retention:** keep the encrypted bundle on robby until AZ4 passes, then
  Human deletes it (`.env` also lives on the rebuilt host by then).
- **Nothing transferred in AZ2A.** No secret printed, copied, or committed.

## AZ2A.10 — Repository preservation

Canonical state is Git (`origin/master`). The `dragon` checkout at `1c433e3`
is **stale** (3 commits behind `ae6f33a`; now 4 behind `039a4dd`) and
**clean** (AZ1c.W verified `git status --porcelain` empty). No uncommitted
source exists on `dragon`.

**Pre-destruction checklist (AZ2B):**
- re-verify `git -C ~/.../copper status --porcelain` is empty;
- re-verify `git -C ~/.../copper stash list` is empty;
- re-verify no untracked files under `apps/` or `scripts/` (`git status
  --porcelain --untracked-files=all`);
- record `dragon` HEAD (`1c433e3…`) in the preservation manifest as historical
  provenance;
- confirm `origin/master` on GitHub (from robby) as the deployment source.

Do **not** preserve the stale checkout. The rebuilt host gets a **fresh
clone**.

## AZ2A.11 — K9 pause plan

Before rebuild (AZ2B), on `dragon`:

```
systemctl --now disable \
  copper-k9-tastytrade-entry-xsp.timer copper-k9-morning-check.timer \
  copper-k9-tastytrade-diagnostic.timer copper-k9-daily-close.timer \
  copper-k9-weekly-flow-report.timer copper-k9-compress-logs.timer \
  copper-k9-smart-shutdown.timer
```

— but the OS disk is being replaced, so the unit files vanish regardless. The
**durable** action is: **copy all `copper-k9-*` unit files + the
`copper-k9-job@.service` template + the slice unit verbatim into the repo**
(proposed `deploy/k9/systemd/`) or into this doc's appendix, so K9 scheduling
can be reconstructed later.

**Post-rebuild initial state — recommended:**

```
K9 TIMERS: NOT INSTALLED
```

Rationale (matches the Product Owner's stated preference): do not reinstall K9
scheduling on the futures-first host. Keep definitions in Git for a future
deliberate restoration (which would also need `smart_shutdown.sh` reworked to
not fight the Sun→Fri lifecycle). "Installed but disabled" is *less* clean —
it reintroduces `smart_shutdown.sh` and its VM-Contributor MI need.

## AZ2A.12 — Old power-lifecycle removal plan (no changes in AZ2A)

| Mechanism | Disposition |
|---|---|
| `copper-k9-smart-shutdown.timer` + `smart_shutdown.sh` | **not reinstalled** on the rebuilt host (definition kept in Git) |
| DevTestLab `shutdown-computevm-dragon` (06:08 UTC) | **delete** the schedule resource in AZ2C (it re-binds to a same-named recreated VM otherwise) |
| ~4.5 h/day Mon–Fri cycle (manual/Automation start + 10:15 CT stop) | replaced by the Sun→Fri control-plane schedule — AZ2A.26 / AZ2A.27 |
| Automation `Start-Dragon` runbook | **repurpose** for the Sunday pre-open start; add a `Stop-Dragon` for Friday post-close |

## AZ2A.13 — New OS baseline (target)

- Ubuntu Server **26.04.1 LTS** (pinned image, AZ2A.3), headless, AMD64, Gen2,
  Trusted Launch + Secure Boot + vTPM.
- `systemctl get-default` → **`multi-user.target`** (24.04 `dragon` currently
  shows `graphical.target`; set/verify `multi-user.target` on the rebuild —
  report if the fresh image already differs).
- No desktop packages. No `sleep`/`suspend`/`hibernate` active (verify
  `static` + inert as in AZ1c.U).
- Guest timezone `Etc/UTC` acceptable; `systemd-timesyncd` synchronized.
  Collector stays timezone-explicit (America/Chicago) in code.
- System-level `systemd` owns the collector/supervisor (not `--user`).

## AZ2A.14 — SSH / host-key transition plan

- **Pre-rebuild:** current host-key fingerprints are already recorded
  (AZ1c.C) — ED25519 `Ai0gLE1EfclvMCXsGEND18JvgcMm1g6LuddNI3ocEao`, ECDSA
  `UIHlwBK/…`, RSA `GOaHj0Yq…`. These become *historical* the moment the OS
  disk is replaced.
- **Post-rebuild:** obtain the **new** host-key fingerprints from a trusted
  path — either `az vm run-command invoke … "ssh-keygen -lf
  /etc/ssh/ssh_host_ed25519_key.pub"` (control-plane, not the network), or the
  serial console / boot diagnostics — **before** any client trusts them.
- Then, per client, and only after independent match: `ssh-keygen -R` the old
  entry **and** add the verified new key (`ssh-keyscan` compared to the
  control-plane value), for robby / weasel / robyn `known_hosts`. **Never**
  a blind `-R` + accept-new.
- **authorized_keys:** provisioned at `az vm create` time via
  `--ssh-key-values` with **independent per-machine public keys**: robby
  (`SHA256:2WcJzGv8CpgQ3Ay5sMBoPjgYmrN5sQtaAGVMmLwe2cg`), weasel
  (`SHA256:0OnoIpOb4a9jUH6hm7DDOqc3h1E5+y5G3dEXeZHrEnk`), and robyn once its
  key exists. No shared private key.
- **Target sshd** (drop-in `/etc/ssh/sshd_config.d/60-dicks.conf`):
  ```
  PasswordAuthentication no
  PubkeyAuthentication yes
  PermitRootLogin no
  X11Forwarding no
  KbdInteractiveAuthentication no
  ```
  Do not go further (no `AllowUsers` lockout, no non-22 port, no MaxAuthTries 1)
  until post-0W-4 hardening — keep it recoverable.

## AZ2A.15 — Tailscale rebuild plan

- **Do not** reuse any `tskey-auth-…` from `cloud/main.bicep` or
  `deploy_weasel.sh` (both plaintext in Git — AZ2A.AC).
- **Recommendation: enrol the rebuilt `dragon` as a FRESH Tailscale node.**
  Operationally cleaner than trying to preserve
  `/var/lib/tailscale/tailscaled.state` across an OS-disk replace; the old node
  object is simply removed from the tailnet admin console.
- Enrolment mechanism:
  - generate a **fresh, single-use, ~1-hour-expiry, pre-approved** auth key in
    the Tailscale admin console at rebuild time (tagged e.g. `tag:dragon`);
  - pass it to the guest **once** via `az vm run-command invoke … "curl -fsSL
    https://tailscale.com/install.sh | sh && tailscale up --auth-key=… --ssh=false
    --hostname=dragon"` — the key is in the run-command payload, **not** in
    cloud-init, **not** in Git, and expires within the hour;
  - immediately mark the key used/revoked in the console.
- Expect a **possibly different `100.x` IP**. Update `~/.ssh/config`
  (`Host dragon HostName …`) and each client only **after** SSH + host-key
  verification succeeds on the new address.
- Node naming predictable: `--hostname=dragon`, tag `tag:dragon`.
- No public SSH exposure (NSG unchanged; no public IP).

## AZ2A.16 — Trusted Launch

Recommend **enable Trusted Launch + Secure Boot + vTPM** on the rebuild
(supported per AZ2A.3 / AZ2A.4). This forces the delete/recreate path (Option
A) rather than an in-place disk swap — already the recommended mechanism, so no
extra cost. If a `--security-type TrustedLaunch` create unexpectedly fails on
B2ms in `eastus` at AZ2C, fall back to `Standard` and note it; do not block the
rebuild on it.

## AZ2A.17 — OS-disk recommendation

**64 GiB StandardSSD_LRS** for the rebuilt OS disk (current is 32 GiB).

Rationale: the clean host holds OS + `uv`/managed Python + Copper checkout
(~220 MB) + system logs + persistent journald (bounded, AZ2A.20) + apt cache
+ Saturday upgrade headroom — but **no datasets** (those go on the data disk).
32 GiB (currently 31 % used at 24.04 with K9) leaves too little margin for a
year of journald + kernel images + a comfortable `apt full-upgrade`. 64 GiB
removes that worry for ~**+$2.40/mo** (E6→E10 tier: $4.80→$9.60/mo). Not worth
going to 128 GiB — datasets are elsewhere.

## AZ2A.18 — Persistent data-disk recommendation

| | |
|---|---|
| Size | **256 GiB** |
| SKU | **StandardSSD_LRS** (E15) |
| Mount | **`/srv/dicks_laboratory`** |
| Layout | `/srv/dicks_laboratory/{data,logs,forensic}` |
| Filesystem | `ext4`, **default mount options** (no `commit=30`), `noatime` optional |
| fstab | **UUID-based**, `nofail` **not** used for the collector's own dependency (see below) |
| Caching | host caching **None** (write-heavy append workload; avoids cache-related loss surprises) |

Capacity vs empirical ~0.49 GB/ES-trading-date:

| Horizon | datasets | + logs + forensic (H1B ≈ 0.5 GB each) + FS overhead + 2nd instrument later | 128 GiB? | 256 GiB? |
|---|---|---|:--:|:--:|
| 60 dates (~1 qtr) | ~30 GB | ~45–55 GB | ok | ok |
| 130 dates (~½ yr) | ~64 GB | ~95–115 GB | marginal | ok |
| 250 dates (~1 yr) | ~120 GB | ~160–200 GB | **no** | ok (~75–80 %) |

**256 GiB** gives ~a year plus forensic-retention and second-instrument
headroom. Retail (eastus): **E15 256 GiB StandardSSD_LRS ≈ $19.20/mo**
(billed whether the VM runs or is deallocated). 128 GiB (E10) would be
$9.60/mo but only covers ~1–2 quarters.

## AZ2A.18b — Filesystem / mount safety (fail-closed)

The futures collector unit must **fail to start** if the data disk is not
mounted:

```
[Unit]
RequiresMountsFor=/srv/dicks_laboratory
ConditionPathIsMountPoint=/srv/dicks_laboratory
After=srv-dicks_laboratory.mount

[Service]
# writes only under /srv/dicks_laboratory/{data,logs}
```

- Use a real `srv-dicks_laboratory.mount` unit (or fstab entry systemd
  generates one from) — **not** `nofail` for the collector's dependency chain,
  so a missing disk is a hard stop, not a silent write to the OS disk.
- The mountpoint directory on the OS disk should be `chattr +i` or owned
  `root:root 0555` when empty so a pre-mount write fails loudly.

## AZ2A.19 — Data-disk approval gate

```
PROPOSED         : 256 GiB StandardSSD_LRS managed disk (E15), mounted /srv/dicks_laboratory
ESTIMATED COST   : ≈ $19.20 / month (eastus retail, Azure Retail Prices API, 2026-09-09) — billed even while the VM is deallocated
APPROVAL REQUIRED: YES — new billable resource, created in AZ2C, not before
```

Alternative if cost-sensitive: 128 GiB (E10) ≈ $9.60/mo, revisit at ~60 % full.

## AZ2A.20 — Journald / swap

- **Journald:** persistent, on the **OS disk** initially
  (`/etc/systemd/journald.conf.d/10-dicks.conf`):
  ```
  [Journal]
  Storage=persistent
  SystemMaxUse=2G
  SystemKeepFree=1G
  MaxRetentionSec=1month
  ```
  2 GiB cap is ample for reboot/postmortem history and fits comfortably on a
  64 GiB OS disk. Revisit moving it to `/srv/dicks_laboratory` only if
  evidence later shows OS-disk pressure.
- Collector's own high-volume logs → `/srv/dicks_laboratory/logs/` (not
  journald), rotated by the collector or `logrotate`.
- **Swap: NONE.** 8 GiB RAM ≫ the low-hundreds-MB collector working set; the
  2.2 GB finalization spike is fixed. Do not add pre-emptive complexity. (If
  AZ4 ever shows memory pressure, add a swapfile on `/srv/dicks_laboratory`,
  not the OS disk.)

## AZ2A.21 — Swap
Covered in AZ2A.20: **NO SWAP** initially.

## AZ2A.22 — Runtime toolchain bootstrap plan (26.04.1)

Reproducible bootstrap (no installs in AZ2A; executed in AZ2C):

```
# base (apt) — only what uv sync / the collector actually needs at runtime
sudo apt-get update
sudo apt-get install -y --no-install-recommends git curl ca-certificates sqlite3 jq
# Azure Linux Agent + cloud-init ship in the marketplace image (verify, don't reinstall)
# Tailscale — see AZ2A.15 (fresh node, run-command, short-lived key)

# uv (user install, matches K9's current pattern on 24.04)
curl -LsSf https://astral.sh/uv/install.sh | sh          # -> ~/.local/bin/uv
uv python install 3.13                                    # Copper's canonical Python line
# project deps
cd ~/Documents/REPOs/copper && uv sync --frozen --all-packages   # --all-packages required: the workspace root is empty; deps live in apps/*
```

- **Python:** whatever `copper/pyproject.toml` / `.python-version` pins
  (currently the 3.13 line — matches robby and the K9 install). `uv` resolves
  it; do not hand-install a system Python.
- **Build tools:** install `build-essential` **only if** `uv sync` fails
  needing a C build (Copper's deps are largely wheels; 24.04 `dragon` runs
  fine with bare `gcc`). Decide at AZ2C from the actual `uv sync` result.
- `gh`: **not installed** (not runtime-required).
- Do **not** copy `~/.local/bin/*` from the old host — re-run the installer.

## AZ2A.23 — Runtime user

**`User=temckee8`** for the futures collector systemd unit (initial).

Reasons: simple admin/recovery, owns the repo checkout, matches the existing
K9 `copper-k9-job@.service` pattern (`User=temckee8`), and avoids solving
service-account separation before the reliability proof. A dedicated
non-login service identity is **post-0W-4 hardening**, not now.

## AZ2A.24 — Fresh Copper deployment

- **Fresh `git clone git@github.com:bigmcdaddy8/copper.git`** into
  **`/home/temckee8/Documents/REPOs/copper`** (keep the path — existing tooling
  and unit `WorkingDirectory=` assume it).
- Requires an SSH deploy key or the `gh`/HTTPS token on the new host — decide
  at AZ2C (a read-only GitHub deploy key in the secure bundle is the cleanest;
  do not reuse a personal token).
- Before any collection: `git -C … rev-parse --abbrev-ref HEAD` = `master`,
  `HEAD == origin/master`, `git status --porcelain` empty.
- **No auto-`pull`.** Deployment is an explicit Saturday-window step (AZ2A.28).
- Every dataset's provenance records the exact deployed commit (the collector
  already writes `collector_git_commit`).

## AZ2A.25 — Credential restore

After fresh clone + `uv sync` validate:

```
robby:  scp ~/secure/dragon-env-YYYYMMDD.gpg  dragon:/tmp/
dragon: gpg -d /tmp/dragon-env-YYYYMMDD.gpg > ~/Documents/REPOs/copper/.env
        chmod 600 ~/Documents/REPOs/copper/.env ; chown temckee8:temckee8 …
        shred -u /tmp/dragon-env-YYYYMMDD.gpg
verify: sha256 of the restored .env == the pre-rebuild sha256 (recorded in the bundle manifest)
        ls -l / stat only — never cat
```

- Never committed, never printed, never pasted into this doc.
- Presence/permission validation only (`stat`, key **names** via
  `sed 's/=.*/=<redacted>/'` as in AZ1c.Y) before any live step.
- **No quote-token request / DXLink connect** until an explicitly authorized
  AZ4 preflight or collector start.

## AZ2A.26 — Sunday→Friday power plan (target, not implemented)

```
Sun ~15:30 CT  VM start  (≈90 min before the 17:00 CT Globex open — margin > cold-boot + Tailscale + collector arm)
Sun 17:00 CT   Globex open  → collector running continuously
Mon–Thu        continuous (no daily cycle, no guest self-deallocate)
Fri 16:00 CT   CME close
Fri ~16:45 CT  graceful collector stop + dataset finalize, THEN VM deallocate
Sat            off
```

Principle: **prefer being ON when uncertain.** No `smart_shutdown.sh`. No
DevTestLab schedule. All power transitions are control-plane and independent of
the guest being alive.

## AZ2A.27 — Azure scheduling (proposal, not implemented)

**Reuse the existing `automation-dragon` Automation account** (it already holds
a `Start-Dragon` runbook and has an MI with VM-Contributor at the `dragon`
scope):

- `Start-Dragon` runbook (PowerShell/Python) → `Start-AzVM -Name dragon -ResourceGroup rg-dev-environment`;
- new **`Stop-Dragon`** runbook → `Stop-AzVM … -Force` (deallocate);
- two **Automation Schedules** in **`America/Chicago`** time zone (Automation
  schedules are DST-correct): `Start` = weekly Sunday ~15:30, `Stop` = weekly
  Friday ~16:45;
- link schedules to runbooks;
- job history in the Automation account gives the required observability;
- runs entirely control-plane → **works while the VM is deallocated**, no guest
  dependency.

Discard: the DevTestLab auto-shutdown (single daily time, no start, UTC-only —
DST-wrong for a CT schedule). `dragon-up.sh`/`dragon-down.sh` remain as manual
operator overrides.

**Not implemented in AZ2A.** Exact runbook code + schedule creation = AZ3.

## AZ2A.28 — Saturday maintenance window (design)

Weekend (VM deallocated Fri 16:45 CT → Sun 15:30 CT) is the natural window.
Proposed: a **Saturday** control-plane job (or a first-boot Sunday pre-open
step) that, on a *separate* short boot:

- `apt-get update && apt-get -y full-upgrade`; reboot if `/var/run/reboot-required`;
- optional Copper redeploy (`git fetch` + fast-forward + `uv sync --frozen --all-packages`) —
  explicit, logged, never during a session;
- host validation (disk free, data mount, `uv sync` clean, credential presence);
- deallocate again until the Sunday start.

Security updates stay **regular** (weekly), just **never during Sun→Fri
capture**. `unattended-upgrades`: keep enabled but set
`Unattended-Upgrade::Automatic-Reboot "false"` (already the default) and shift
`apt-daily`/`apt-daily-upgrade` timers to the Saturday window (or disable the
timers and rely on the maintenance job). No implementation in AZ2A.

## AZ2A.29 — Boot diagnostics / metrics

- **Enable managed boot diagnostics** at `az vm create`
  (`--boot-diagnostics-storage ""` = managed) — currently absent on `dragon`.
- Azure Monitor metrics to watch from AZ4 on:
  `Percentage CPU`, `CPU Credits Remaining`, `CPU Credits Consumed`,
  `OS Disk / Data Disk IOPS + latency + queue depth`,
  `Network In/Out Total`, `VM Availability`.
- **B2ms stays** the baseline SKU; resize only on real AZ4 evidence
  (credit exhaustion or sustained >80 % CPU across a session).

## AZ2A.30 — Managed identity / RBAC plan

**Current MI (`da55ad8d…`) role assignments (control-plane audit):**

| Role | Scope | Purpose | Restore on rebuild? |
|---|---|---|:--:|
| `Contributor` | RG `rg-dev-environment` | broad — K9 era | **NO** |
| `Virtual Machine Contributor` | VM `dragon` | `smart_shutdown.sh` self-deallocate | **NO** |
| `Classic Virtual Machine Contributor` | RG | legacy ASM, vestigial | **NO** |

Plus two **other** service principals (`6d277e79…`, `563c2651…` — the
`automation-dragon` / `automation-k9` identities) hold `Virtual Machine
Contributor` **at the `dragon` VM scope**; these persist across a same-named
recreate and are what the Sunday-start automation will use — **keep**, but
in AZ3 tighten to just the one Automation account that owns the schedule.

**Rebuilt-host MI principle — least privilege:**
- The futures collector needs **nothing** from Azure at runtime (power is
  external; no Key Vault in the near-term plan).
- Grant the new MI **no role**, or at most **Reader** on the VM if we later
  want the guest to read its own Scheduled Events / metadata (Scheduled Events
  via IMDS needs no RBAC anyway).
- **Do not** re-grant `Contributor` or `Virtual Machine Contributor` to the
  guest. Guest-initiated self-deallocation is explicitly retired.

## AZ2A.31 — DevTestLab auto-shutdown resource

`shutdown-computevm-dragon` (`Microsoft.DevTestLab/schedules`) has
`targetResourceId = …/virtualMachines/dragon` (a name-based ARM ID). A
delete+recreate of `dragon` with the **same name in the same RG** yields the
**same resource ID**, so the schedule would **silently re-attach** to the new
VM and keep deallocating it at 06:08 UTC — directly breaking Sun→Fri capture.

**Plan (AZ2C):** explicitly `az resource delete` the
`shutdown-computevm-dragon` schedule (or `az vm auto-shutdown -g … -n dragon
--off`) as a named rebuild step, and verify post-rebuild that no
`Microsoft.DevTestLab/schedules` targets `dragon`. Not touched in AZ2A.

## AZ2A.32 — Rollback / old-OS preservation plan

`az vm delete` **does not delete the OS disk by default** → after the VM is
deleted, `dragon_disk1_bb48fd67c68342b4b4596a45879297f9` (32 GiB StandardSSD,
~9 GiB used) **remains** as a detached managed disk.

| Option | Cost while retained | Simplicity | Recommendation |
|---|---|---|---|
| **Retain the detached old OS disk** | ~$2.40/mo (E4 32 GiB StandardSSD) | trivial — it's automatic | **RECOMMENDED** |
| Snapshot the old OS disk, then delete the disk | ~$0.45–1.60/mo (incremental StandardSSD snapshot of ~9 GiB used) | one extra step + a restore step later | fallback if cost matters |

**Recommended:** keep the detached old OS disk untouched until the 26.04 host
passes the full gate — **boot, SSH (new host keys verified), Tailscale, Copper
clone + `uv sync`, credential restore + presence check, K9-preservation
manifest committed, and a short AZ4 futures verification**. Then Human deletes
the old disk. Rollback before that = `az vm create -n dragon --attach-os-disk
dragon_disk1_bb48fd67… --nics dragon-nic` (recreate the 24.04 VM from the
retained disk). No snapshot created in AZ2A (would be billable); marked as an
AZ2B approval item only if Human prefers snapshot over disk-retention.

## AZ2A.33 — Pre-rebuild preservation package

**Non-secret manifest (committed to the repo, e.g. `deploy/k9/PRESERVED.md` +
`deploy/k9/systemd/`):**
- all `copper-k9-*.{timer,service}` unit files + `copper-k9-job@.service` +
  `system-copper-k9-job.slice`, verbatim;
- the exact `OnCalendar=` schedule table (AZ1c.Z);
- `dragon` pre-rebuild git HEAD (`1c433e3…`) and "clean" attestation;
- SSH **public**-key fingerprints (robby / weasel) — already in this doc;
- old SSH **host**-key fingerprints (AZ1c.C) as historical;
- Azure resource inventory snapshot (VM/NIC/NSG/disk/schedule/automation) —
  already in AZ1 / AZ2A.

**Secure backup bundle (robby, `~/secure/`, mode 600, NOT Git):**
- `dragon-env-YYYYMMDD.gpg` (AES-256, Human passphrase) + its sha256;
- optionally `~/.../copper/logs/K9/**` as a plain tar (non-secret but noisy) —
  or skip and accept loss of K9 operational logs;
- a GitHub **read-only deploy key** for the fresh clone (generate new; do not
  reuse a personal key);
- `manifest.txt`: what / source host / sha256 / created-at / restore-verified /
  retention ("delete after AZ4 acceptance").

**No backup performed in AZ2A.**

## AZ2A.34 — Human multi-machine access prerequisites

| Access | Required before AZ2B destructive step? | Current state |
|---|---|---|
| robby → Azure control plane (`az`) | **YES** | **PASS** (authenticated; used throughout AZ1/AZ1c/AZ2A) |
| robby → *old* `dragon` SSH | **YES** | **PASS** (AZ1c.B) |
| weasel → `dragon` SSH | preferred | key already authorized (AZ1c.P); **not verified from weasel** — Human runs the check |
| robyn → tailnet + `dragon` SSH | preferred | **not configured** — robyn not on tailnet, no key |

**Pre-rebuild vs post-rebuild:** the rebuild changes the Tailscale node and all
host keys, so *pre-rebuild* client access does not carry over. **Post-rebuild
independent access verification from every machine that will operate the
futures host is MANDATORY before any unattended futures work** (part of AZ2C /
AZ3). robyn tailnet+key setup should happen in AZ2B/AZ2C so its public key can
be baked into `az vm create --ssh-key-values`.

## AZ2A.35 — Revised phase sequence

```
0W-AZ1 / 0W-AZ1c        ACCEPTED / CLOSED
        ↓
0W-AZ2A  26.04.1 rebuild + preservation DESIGN            ← this section
        ↓
   ┌─────────────  HUMAN APPROVAL GATE  ─────────────┐
   │  (a) config-only changes   (b) new billable      │
   │  resources   (c) destructive/rebuild actions     │
   └─────────────────────────────────────────────────┘
        ↓
0W-AZ2B  Pre-rebuild preservation: secure .env bundle; commit K9-unit
         manifest; K9 timers disabled; repo-clean attestation; robyn
         tailnet+key; retain old OS disk as rollback (no snapshot cost)
        ↓
0W-AZ2C  Rebuild dragon on pinned Ubuntu 26.04.1 (Option A): delete VM
         (keep NIC/OS-disk-as-rollback), az vm create w/ TrustedLaunch +
         64 GiB OS disk + 256 GiB data disk + boot diagnostics; fresh
         Tailscale node; sshd baseline; new host-key verification + client
         known_hosts update; delete DevTestLab schedule; new least-priv MI;
         fresh Copper clone + uv sync; restore .env; mount /srv/dicks_laboratory
         fail-closed
        ↓
0W-AZ3   Sunday→Friday Automation schedule (Start-Dragon / Stop-Dragon,
         America/Chicago); futures systemd supervisor (RequiresMountsFor,
         Type=exec, RuntimeMax, session lifecycle); Saturday maintenance
         window; unattended-upgrades retimed
        ↓
0W-AZ4   Short live collector verification (one bounded session) — watch
         CPU-credit / disk / writer metrics
        ↓
0W-2 Attempt 4   Formal gap-free full trading-date proof ON AZURE
        ↓
0W-4     2–3 day unattended soak ON AZURE
```

The Human approval gate after AZ2A is **mandatory** and is not skipped.

## AZ2A.36 — Migration document

This section (0W-AZ2A) appended to
`docs/dicks_laboratory/AZURE_COLLECTION_HOST_MIGRATION.md`. Records: AZ1/AZ1c
accepted; Human decision **USE DRAGON**; Human OS decision **Ubuntu 26.04.1**;
PO method **CLEAN REBUILD**; K9 **preserve/pause**; dedicated-new-VM
**superseded**; in-place upgrade **rejected**; exact 26.04 image findings;
rebuild mechanism + survival matrix; preservation + rollback plans; revised
phase sequence. Prior alternatives retained above, not erased.

## AZ2A.37 — Secret audit (this document)

Grep of the committed doc for secret material:
- **Tailscale auth keys:** none (the `cloud`-repo `tskey-auth-…` values are
  *referenced as a finding* but **not reproduced**).
- **OAuth / tokens / `.env` values:** none (only key **names**, already
  redacted-style in AZ1c.Y).
- **Private keys:** none.
- **Azure identifiers:** subscription/tenant/principal/resource GUIDs are
  redacted (`<SUB>`, `da55ad8d…`, `fcf2fcde…`); public SSH **fingerprints**
  are retained (acceptable and useful).
- Windows admin password from `deploy_weasel.sh`: **not reproduced** (finding
  only).

Document is safe to commit.

## AZ2A.38 — Commit / push

Product Owner authorized the AZ2A doc commit. Details in the handoff
(`docs: plan dragon 26.04 futures-host rebuild`). No other Copper source
changed in AZ2A.

## AZ2A.39 — Security findings (updated, carried to AZ2B/AZ2C)

1. **Plaintext Tailscale auth keys** in the `cloud` repo — now **two**
   confirmed: `main.bicep` (`TailscaleBootstrap`) and
   `scripts/deploy_weasel.sh`. Plus a **hardcoded Windows admin password** in
   `deploy_weasel.sh`. All in repo `cloud` @ `ecd6723` (not Copper, not
   touched). **AZ2B/AZ2C:** rotate/revoke every exposed key + the weasel
   password; the rebuilt `dragon` enrols with a **fresh short-lived** key via
   run-command (never stored). Recommend Human also scrubs the `cloud` repo
   history.
2. Rebuilt sshd baseline: `PermitRootLogin no`, `X11Forwarding no`,
   `PasswordAuthentication no`, `PubkeyAuthentication yes` (AZ2A.14).
3. **Least-privilege MI** — do not restore RG `Contributor` / VM `Contributor`
   to the guest (AZ2A.30).
4. **Trusted Launch + Secure Boot + vTPM** on the rebuild (AZ2A.16).
5. `.env` preserved via **AES-256 encrypted bundle**, Human passphrase, never
   in Git (AZ2A.9).
6. Data mount **fail-closed** so a missing disk never silently writes datasets
   to the OS disk (AZ2A.18b).

## AZ2A.AF — Exact mutating actions AZ2B would perform

**On `dragon` (guest, pre-rebuild — via SSH):**
1. `gpg --symmetric --cipher-algo AES256` the `.env` to a temp file; record its
   sha256; `scp` the `.gpg` to robby `~/secure/`; `shred -u` the temp file.
2. `systemctl --now disable` the 7 `copper-k9-*.timer` units.
3. Copy the `copper-k9-*` unit files + template + slice to a working dir for
   commit into the Copper repo.
4. Re-attest repo cleanliness (`git status --porcelain`, `stash list`).
5. (optional) tar `~/.../copper/logs/K9` into the secure bundle.

**On robby (repo — committed to `origin/master`):**
6. Add `deploy/k9/systemd/*` + `deploy/k9/PRESERVED.md` (non-secret K9
   preservation manifest). Commit + push.

**Client/tailnet:**
7. Enrol **robyn** in the tailnet; generate a dedicated robyn ed25519 keypair;
   record its public fingerprint in the doc.

**Azure (control plane):**
8. **None destructive.** (Retaining the old OS disk as rollback is automatic
   at AZ2C's `az vm delete`; a *snapshot* would be the only billable AZ2B
   action and is **not** proposed unless Human prefers it.)

AZ2B makes **no Azure resource changes** and **does not power on `dragon`**
except a brief SSH session for steps 1–5 (which requires starting the VM — that
start is itself an approval item, see AZ2A.AG).

## AZ2A.AG — Human approval requirements

### (a) No-cost / configuration changes
- Brief power-on of `dragon` for the AZ2B preservation SSH session, then
  deallocate.
- `systemctl disable` the K9 timers on `dragon`.
- Commit the non-secret K9 preservation manifest to `origin/master`.
- Create an AES-256 encrypted `.env` backup on robby (local file only).
- Enrol robyn in the tailnet; generate robyn's keypair.
- sshd hardening drop-in on the rebuilt host (AZ2C).
- Delete the DevTestLab `shutdown-computevm-dragon` schedule (AZ2C).
- Fresh Tailscale node enrolment with a short-lived key (AZ2C).

### (b) New billable resources
- **256 GiB StandardSSD_LRS data disk ≈ $19.20/mo** (AZ2C). *(128 GiB ≈
  $9.60/mo alternative.)*
- **OS disk 32 → 64 GiB ≈ +$2.40/mo** (AZ2C).
- *(Optional)* old-OS-disk **snapshot** for rollback ≈ $0.5–1.6/mo — only if
  Human prefers it over simply retaining the detached disk (~$2.40/mo, which
  happens automatically anyway).
- Managed boot diagnostics — negligible storage cost.

### (c) Destructive / rebuild actions
- **`az vm delete -g rg-dev-environment -n dragon`** (AZ2C) — deletes the VM
  object + its SystemAssigned MI; **retains** the OS disk (rollback) and NIC.
- **`az vm create … dragon …`** on the pinned 26.04 image with Trusted Launch
  (AZ2C) — new OS disk, new MI principal, new SSH host keys, new Tailscale
  node.
- Delete the DevTestLab shutdown schedule (AZ2C).
- Eventually (post-AZ4 acceptance): delete the retained old 24.04 OS disk.

---

```
0W-AZ2A: DESIGN COMPLETE — DRAGON 26.04.1 CLEAN REBUILD PLANNED

DRAGON CHANGES MADE            : NONE
K9 CHANGES MADE                : NONE
AZURE BILLABLE RESOURCES CREATED: NONE
DESTRUCTIVE ACTIONS            : NONE
NEXT                          : HUMAN APPROVAL FOR AZ2B
```

---

# Phase 0W-AZ2B — Pre-Rebuild Preservation & K9 Pause

**Last reversible checkpoint before the AZ2C destructive rebuild.** Executed
2026-09-09 from `robby`. Allowed: brief power-on, preserve host-local state,
disable K9 scheduling, prepare rollback evidence, commit non-secret artifacts,
deallocate. **Not done:** any VM/disk/network/Tailscale/RBAC/DevTestLab
mutation, any Copper redeploy, any collector start.

## AZ2B.A — AZ2A acceptance

```
0W-AZ2A : ACCEPTED / CLOSED
```

Accepted architecture: rebuild `dragon` clean on Ubuntu 26.04.1 LTS
(pinned image), `Standard_B2ms`, 64 GiB OS disk, 256 GiB StandardSSD data disk,
Trusted Launch + Secure Boot + vTPM; K9 preserved + paused.

## AZ2B.B — Pinned 26.04 image (frozen)

```
AZ2C PINNED IMAGE: Canonical:ubuntu-26_04-lts:server:26.04.202609020
```

Re-verified available in `eastus` on 2026-09-09 (`az vm image show` →
`name 26.04.202609020`, `hyperVGeneration V2`, `architecture x64`). Do **not**
substitute `:latest` or a newer build before AZ2C without a deliberate PO/Human
decision. AZ2C may re-check availability immediately before the rebuild; if the
version is gone or a material issue surfaces → **STOP / REPORT / request
decision**.

## AZ2B.C — Dragon power-on / SSH

| | |
|---|---|
| State at phase start | already `PowerState/running` (up since 2026-09-09 10:46:10 UTC — daily start automation) |
| `az vm start` | issued anyway; rc 0 (no-op), 16:51:32→16:51:45 UTC |
| Tailscale | `dragon` online, `100.103.127.127` |
| **ROBBY → OLD DRAGON SSH** | **PASS** — `publickey` (`id_ed25519` `SHA256:2WcJz…we2cg`), user `temckee8`, host key ED25519 `SHA256:Ai0gLE1EfclvMCXsGEND18JvgcMm1g6LuddNI3ocEao` matched (unchanged); `SSH_OK dragon 2026-09-09T16:52:05Z` |

Only session present during AZ2B was robby's own.

## AZ2B.D — Pre-rebuild host manifest ("DRAGON GENERATION 0", Ubuntu 24.04.4 / K9-era)

| Property | Value |
|---|---|
| VM name / size | `dragon` / `Standard_B2ms` (2 vCPU, 8 GiB) |
| securityType / zones / priority | `Standard` / none / standard (not Spot) |
| OS image ref | `Canonical:ubuntu-24_04-lts:server:latest` (exactVersion `24.04.202606060`) |
| Guest OS / kernel | Ubuntu **24.04.4 LTS** (Noble) / `6.17.0-1022-azure` |
| Machine ID | `fcf2fcde…` (redacted) |
| VM `timeCreated` | 2026-06-14T04:16:07Z |
| MI | SystemAssigned, principal `da55ad8d…` (redacted) |
| NIC | `dragon-nic`, private IP `10.0.1.4` (Dynamic), **no public IP**, NIC-level NSG none |
| VNet / subnet | `dragon-vnet` 10.0.0.0/16 / `default` 10.0.1.0/24 (NSG `dragon-nsg` at subnet) |
| NSG `dragon-nsg` | inbound custom: `Allow-Tailscale-Direct` UDP 41641 from `*`; else Azure defaults + `DenyAllInBound` |
| OS disk | `dragon_disk1_bb48fd67c68342b4b4596a45879297f9`, StandardSSD_LRS, 32 GiB, Gen2, `caching ReadWrite`, `createOption FromImage` |
| Data disks | none |
| DevTestLab shutdown | `shutdown-computevm-dragon` — **ENABLED**, daily 06:08 UTC, 30-min email warning |
| Automation | `automation-dragon` + `automation-k9` accounts, each a Published `Start-Dragon` runbook (no schedules); 2 SPs (`6d277e79…`, `563c2651…`) hold `Virtual Machine Contributor` at the `dragon` VM scope |
| Tailscale | hostname `dragon`, `100.103.127.127`, node up; peers robby + weasel active, weasel-den offline 85 d; **no `robyn`** |
| SSH host fingerprints (GEN 0) | ED25519 `SHA256:Ai0gLE1EfclvMCXsGEND18JvgcMm1g6LuddNI3ocEao` · ECDSA `SHA256:UIHlwBK/B/6cJRl5VyyU9syNZk3t1576o7pTTwHZ+no` · RSA `SHA256:GOaHj0YqlEZ7Z4bcH2ZJNHsbKLil3WyfEe6Q6i2QQos` |
| authorized_keys | robby `SHA256:2WcJzGv8CpgQ3Ay5sMBoPjgYmrN5sQtaAGVMmLwe2cg` (`mckee8@gmail.com`) · weasel `SHA256:0OnoIpOb4a9jUH6hm7DDOqc3h1E5+y5G3dEXeZHrEnk` (`weasel`) |
| default target | `graphical.target` |
| journald | `auto` + `/var/log/journal` present → persistent (~433 MB) |

No secret values captured.

## AZ2B.E — Actual OS-disk `deleteOption` (critical)

`az vm show -g rg-dev-environment -n dragon --query storageProfile.osDisk`:

```
"deleteOption": "Detach"
```

**✔ The old OS disk survives VM deletion automatically.** No pre-delete action
is required to preserve it. (`diskControllerType SCSI`; `dataDisks []`.)

NIC deletion semantics: the VM `networkProfile.networkInterfaces[].deleteOption`
is `null` (unset) → Azure default for a VM-attached NIC is **Detach** — the
NIC (and its private IP `10.0.1.4`) survives VM deletion. AZ2C reuses it via
`az vm create --nics dragon-nic`.

## AZ2B.F — Old OS-disk rollback identification

| Field | Value |
|---|---|
| name | `dragon_disk1_bb48fd67c68342b4b4596a45879297f9` |
| resource ID | `/subscriptions/<SUB>/resourceGroups/rg-dev-environment/providers/Microsoft.Compute/disks/dragon_disk1_bb48fd67c68342b4b4596a45879297f9` |
| SKU / size | StandardSSD_LRS / 32 GiB |
| osType / Hyper-V gen | Linux / V2 |
| state / provisioningState | Attached / Succeeded |
| timeCreated | 2026-06-14T04:16:09Z |
| built from | `Canonical:ubuntu-24_04-lts:server:latest` (`24.04.202606060`) |

**Rollback = `az vm create -g rg-dev-environment -n dragon --attach-os-disk
dragon_disk1_bb48fd67c68342b4b4596a45879297f9 --os-type Linux --nics
dragon-nic --size Standard_B2ms`** (recreates the 24.04 VM from the retained
disk). Retain untouched until the 26.04 host passes the full AZ2C/AZ4 gate;
then Human deletes it. Retention cost ≈ $2.40/mo (E4 32 GiB StandardSSD).

## AZ2B.G — `.env` encrypted backup

**Guaranteed preservation:** `~/Documents/REPOs/copper/.env` (mode `600`, owner
`temckee8`, 1493 B) remains on the **retained old OS disk** (deleteOption
`Detach`, AZ2B.E) — it is not lost by the rebuild.

**Second copy (encrypted, on robby) — command prepared, one interactive Human
run required** (the passphrase must be entered interactively and must never
reach shell history / a script / an env file / this document):

```bash
# run on robby via the ! prefix; prompts once for an AES-256 passphrase (Human-held)
mkdir -p ~/secure/dragon-pre-rebuild && chmod 700 ~/secure ~/secure/dragon-pre-rebuild
ssh -o BatchMode=yes dragon 'cat ~/Documents/REPOs/copper/.env' \
  | gpg --symmetric --cipher-algo AES256 --no-symkey-cache \
        -o ~/secure/dragon-pre-rebuild/dragon-env-20260909.env.gpg
chmod 600 ~/secure/dragon-pre-rebuild/dragon-env-20260909.env.gpg
sha256sum ~/secure/dragon-pre-rebuild/dragon-env-20260909.env.gpg
stat -c '%s bytes  %A  %U:%G' ~/secure/dragon-pre-rebuild/dragon-env-20260909.env.gpg
```

No plaintext temp file on either host; `.env` is streamed straight into `gpg`.
Recorded on completion: artifact path `~/secure/dragon-pre-rebuild/dragon-env-20260909.env.gpg`,
its SHA-256, size, and the source mode/owner (`600` / `temckee8`).
**Source `.env` value never printed, never committed.** This is **AZ2C gate
#1** — not an AZ2B blocker (the retained disk already preserves `.env`).

## AZ2B.H — K9 unit preservation

The K9 systemd units are **already tracked in Git** at `deploy/systemd/`
(8 files: 7 timers + `copper-k9-job@.service`). On 2026-09-09 the copies
installed on `dragon` (`/etc/systemd/system/copper-k9-*`) were verified
**byte-for-byte identical** to the repo copies (SHA-256 of all 8 matched
exactly). `system-copper\x2dk9\x2djob.slice` is auto-generated — no file.

Added: **`deploy/k9/PRESERVED.md`** — records the pause, the schedule table,
the restoration procedure, and an explicit warning that
`copper-k9-smart-shutdown` must **not** be re-enabled while futures collection
owns the host lifecycle.

**AZ2A's assumption that the K9 units were host-local is corrected: they are
fully reproducible from Git.**

## AZ2B.I — K9 runtime evidence preservation

| Item | Size | Class | Action |
|---|---|---|---|
| `~/…/copper/logs/K9/` (dry-run `xsp_pcs_0dte_*.json` + `smart_shutdown_*.log`) | 2.1 MB | PRESERVE | tar → `robby:~/secure/dragon-pre-rebuild/dragon-k9-logs-20260909.tgz` |
| `deploy/systemd/copper-k9-*` | — | REPRODUCIBLE (Git) | none |
| `scripts/{run_k9_scheduled_job,smart_shutdown,k9_*,compress_old_logs}.sh` | — | REPRODUCIBLE (Git) | none |
| `apps/K9/**` | — | REPRODUCIBLE (Git) | none |
| systemd auto-slice, `timers.target.wants` symlinks | — | DISCARDABLE (regenerated) | none |

Archive: `dragon-k9-logs-20260909.tgz`, **115 161 bytes**, SHA-256
`cbac7ef8d86256593380c0a1099cfa3ae12b52986356c3773410f404967c8081` — copied to
`robby:~/secure/dragon-pre-rebuild/` (mode 600), hash re-verified there (`OK`),
temp removed from `dragon`. **Not committed to Git** (runtime noise). Nothing
deleted on `dragon`.

## AZ2B.J — K9 timer pause result

`sudo systemctl disable --now` the seven `copper-k9-*.timer` units. Result:

| Timer | enabled | active |
|---|---|---|
| `copper-k9-tastytrade-entry-xsp` | **disabled** | **inactive** |
| `copper-k9-morning-check` | **disabled** | **inactive** |
| `copper-k9-tastytrade-diagnostic` | **disabled** | **inactive** |
| `copper-k9-daily-close` | **disabled** | **inactive** |
| `copper-k9-weekly-flow-report` | **disabled** | **inactive** |
| `copper-k9-compress-logs` | **disabled** | **inactive** |
| `copper-k9-smart-shutdown` | **disabled** | **inactive** |

All 7 `timers.target.wants` symlinks removed. `systemctl list-timers --all` →
no `copper-k9-*`. No `copper-k9-*` unit active/running. **Unit files remain on
disk** (`/etc/systemd/system/copper-k9-*`, 8 files) — disabled, not deleted.
No K9 job was executed for testing.

## AZ2B.K — Smart-shutdown pause result

`copper-k9-smart-shutdown.timer` — **`disabled`, `inactive (dead)`, `Trigger:
n/a`**. The old host will **not** self-deallocate during AZ2B or afterward.
(Observed earlier the same day: the K9-era 10:15 CT `smart_shutdown` run had
*not* deallocated the VM — still up ~1h40m later — independent of this pause.)

## AZ2B.L — DevTestLab shutdown state

`shutdown-computevm-dragon` — **left ENABLED** (06:08 UTC daily). AZ2B is
non-destructive; this resource is **explicitly removed in AZ2C** before the
rebuilt host is operational (it would otherwise re-bind to a same-named
recreated VM — see AZ2A.31). AZ2B preservation work completed ~13 h before the
next 06:08 UTC firing; no interference.

## AZ2B.M — Current MI / RBAC evidence

MI principal `da55ad8d…` (full object ID held out of this document; recorded
only in the operator's Azure console). Role assignments (re-verified
2026-09-09, unchanged from AZ2A):

| Role | Scope | Class |
|---|---|---|
| `Virtual Machine Contributor` | VM `dragon` | **K9 SELF-DEALLOCATION LEGACY** (`smart_shutdown.sh`) |
| `Contributor` | RG `rg-dev-environment` | **OTHER** — broad, K9-era; not needed by a futures host |
| `Classic Virtual Machine Contributor` | RG | **OTHER** — legacy ASM, vestigial |
| `Virtual Machine Contributor` (SP `6d277e79…`) | VM `dragon` | **AUTOMATION CONTROL-PLANE** (`automation-*` account) |
| `Virtual Machine Contributor` (SP `563c2651…`) | VM `dragon` | **AUTOMATION CONTROL-PLANE** (`automation-*` account) |

No RBAC mutated. The rebuilt VM gets a **new** MI principal; none of the above
is restored to it — least privilege (AZ2A.30).

## AZ2B.N — Tailscale legacy-secret finding

Unchanged from AZ2A: plaintext `tskey-auth-…` in the separate `cloud` repo
(`main.bicep` **and** `scripts/deploy_weasel.sh`, plus a hardcoded Windows
password in the latter). **MUST NOT be reused.** No secret value recorded. No
attempt to preserve `dragon`'s `/var/lib/tailscale/tailscaled.state` — the
rebuilt host enrols as a **fresh** node with a short-lived key (AZ2A.15).

## AZ2B.O — Robby access state

```
robby → Azure control plane : PASS  (az authenticated; used throughout)
robby → OLD dragon SSH      : PASS  (AZ2B.C)
```

## AZ2B.P — Weasel access state

```
WEASEL → OLD DRAGON : NOT TESTED
```

weasel's public key `SHA256:0OnoIpOb4a9jUH6hm7DDOqc3h1E5+y5G3dEXeZHrEnk` is
already in `dragon`'s `authorized_keys` and the `weasel` tailnet node is
active, but the check must be run **from weasel** (Claudine runs on robby).
Not a blocker — robby control-plane + SSH are proven. Human may run the
client-side check from weasel (block in AZ1.N).

## AZ2B.Q — Robyn access state

```
ROBYN ACCESS : DEFERRED
```

`robyn` is not a tailnet member and has no key on `dragon`. If Human can work
on robyn before AZ2C: (1) enrol robyn in the tailnet; (2)
`ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_dragon -C "robyn-to-dragon"`;
(3) keep the private key **only** on robyn; (4) send Claudine the **public**
key + fingerprint for AZ2C `--ssh-key-values`. Not a blocker to AZ2B.
Post-rebuild independent access verification from every operating machine
remains mandatory before unattended collection.

## AZ2B.R — Old SSH host fingerprints (DRAGON GENERATION 0 / 24.04 host)

| Alg | SHA256 | Will change at rebuild? |
|---|---|---|
| ED25519 | `Ai0gLE1EfclvMCXsGEND18JvgcMm1g6LuddNI3ocEao` | **yes (intended)** |
| ECDSA | `UIHlwBK/B/6cJRl5VyyU9syNZk3t1576o7pTTwHZ+no` | **yes (intended)** |
| RSA | `GOaHj0YqlEZ7Z4bcH2ZJNHsbKLil3WyfEe6Q6i2QQos` | **yes (intended)** |

Recorded as historical only. No private host key preserved. AZ2C generates
fresh keys and every client's `known_hosts` is updated only after
control-plane-verified fingerprint match (AZ2A.14).

## AZ2B.S — Dragon repo uniqueness check

`~/Documents/REPOs/copper` on `dragon`:

```
branch        : master
HEAD          : 1c433e3c429cebcfb3f6e41fe2298642a97a0ad1
status        : ## master...origin/master   (clean — no porcelain output)
stash list    : empty
untracked (all): none
```

**No unique uncommitted source exists on `dragon`.** HEAD `1c433e3` is a
published ancestor (robby/`origin/master` is now `c9683f1…`, i.e. dragon is
4 commits behind — behind, never ahead). The stale checkout will be discarded
at rebuild; a fresh clone replaces it (AZ2A.24). Nothing to reconcile.

## AZ2B.T — Preservation files added

| File | Purpose |
|---|---|
| `deploy/k9/PRESERVED.md` | K9 pause record + restoration procedure + smart-shutdown warning |
| `docs/dicks_laboratory/AZURE_COLLECTION_HOST_MIGRATION.md` | this AZ2B section |

The K9 unit files themselves were **already** in `deploy/systemd/` — not
re-added.

**Out-of-Git preservation** (on `robby`, `~/secure/dragon-pre-rebuild/`,
mode 600): `dragon-k9-logs-20260909.tgz` (done); `dragon-env-20260909.env.gpg`
(command prepared — one Human run).

## AZ2B.U — Secret audit

Committed changes grepped: no `tskey-auth-…` values, no OAuth/token/`.env`
values, no private keys, no full GUIDs (subscription/tenant/principal/machine
IDs redacted). `deploy/k9/PRESERVED.md` contains only unit metadata, schedules,
and public restoration steps. Public SSH fingerprints retained (acceptable).
Encrypted `.env` bundle and K9 log tar are **not** in Git. Safe to commit.

## AZ2B.V — Commit / push

`ops: preserve K9 host scheduling before dragon rebuild` — see handoff for
hash. `git diff --check` clean; `deploy/k9/PRESERVED.md` is Markdown (no lint).

## AZ2B.W — Final robby git state

```
master · HEAD == origin/master · working tree clean
```
(exact hash in handoff)

## AZ2B.X — Dragon deallocation

`az vm deallocate -g rg-dev-environment -n dragon` after all preservation +
commit work. Required end state **`PowerState/deallocated`** (not a guest
shutdown). Exact timestamps in handoff.

## AZ2B.Y — Azure baseline reconciliation (post-deallocation)

| Property | Expected | Observed |
|---|---|---|
| VM `dragon` exists | yes | yes |
| OS disk `dragon_disk1_bb48fd67…` attached | yes | yes |
| NIC `dragon-nic` / private IP `10.0.1.4` | unchanged | unchanged |
| NSG `dragon-nsg` | unchanged | unchanged |
| Public IP | none | none |
| Data disks | none | none |
| DevTestLab `shutdown-computevm-dragon` | present, enabled | present, enabled |
| VM size / securityType | `Standard_B2ms` / `Standard` | unchanged |
| VM deleted / recreated | no | no |

AZ2B made **no destructive Azure change**. Only guest changes: 7 K9 timers
disabled (unit files retained). Guest state lives on the OS disk that is itself
the rebuild rollback.

## AZ2B.Z — Exact AZ2C execution packet (prepared — DO NOT EXECUTE)

```
# ---- PRE-DELETE SAFETY GATES (all must pass; see AZ2B.AA) ----
G1  verify sha256 of ~/secure/dragon-pre-rebuild/dragon-env-20260909.env.gpg == recorded
G2  git ls-remote origin master == local origin/master  AND  K9-preservation commit is on origin/master
G3  ssh dragon 'git -C ~/Documents/REPOs/copper status --porcelain; git -C … stash list'  == empty
G4  az disk show -g rg-dev-environment -n dragon_disk1_bb48fd67c68342b4b4596a45879297f9  -> exists, StandardSSD_LRS, 32GiB
G5  az vm show … storageProfile.osDisk.deleteOption == "Detach"
G6  az vm show … networkProfile…deleteOption in (null, "Detach")   # NIC survives
G7  az account show   -> authenticated, expected subscription
G8  az vm image show --location eastus --urn Canonical:ubuntu-26_04-lts:server:26.04.202609020  -> resolves
G9  robby.pub + weasel.pub present; robyn.pub present OR explicitly deferred
G10 Human has approved billable + destructive AZ2C execution (this packet)

# ---- STEP 1 — Azure: stop the K9-era power policy ----
az vm deallocate -g rg-dev-environment -n dragon                       # ensure deallocated
az vm auto-shutdown -g rg-dev-environment -n dragon --off              # or: az resource delete … shutdown-computevm-dragon
#   verify: no Microsoft.DevTestLab/schedules targets dragon

# ---- STEP 2 — Azure: delete the VM object (OS disk + NIC RETAINED via deleteOption=Detach) ----
az vm delete -g rg-dev-environment -n dragon --yes
#   verify: az disk show … dragon_disk1_bb48fd67…  -> state "Unattached", still present
#   verify: az network nic show -g rg-dev-environment -n dragon-nic  -> present, no VM

# ---- STEP 3 — Azure: create the data disk (NEW BILLABLE) ----
az disk create -g rg-dev-environment -n dragon-data1 \
  --size-gb 256 --sku StandardSSD_LRS --os-type "" --hyper-v-generation V2

# ---- STEP 4 — Azure: create the rebuilt VM (NEW BILLABLE OS disk; Trusted Launch) ----
az vm create -g rg-dev-environment -n dragon \
  --image Canonical:ubuntu-26_04-lts:server:26.04.202609020 \
  --size Standard_B2ms \
  --nics dragon-nic \
  --security-type TrustedLaunch --enable-secure-boot true --enable-vtpm true \
  --os-disk-name dragon-osdisk-gen1 --os-disk-size-gb 64 --storage-sku StandardSSD_LRS \
  --os-disk-delete-option Detach \
  --attach-data-disks dragon-data1 --data-disk-caching None \
  --admin-username temckee8 \
  --ssh-key-values <robby.pub> <weasel.pub> [<robyn.pub>] \
  --custom-data cloud-init-dragon-gen1.yaml \
  --boot-diagnostics-storage ""            # managed boot diagnostics
#   cloud-init MUST contain NO secret (no Tailscale key)

# ---- STEP 5 — Tailscale: fresh node ----
#   generate a 1-hour, single-use, pre-approved, tag:dragon auth key in the TS admin console
az vm run-command invoke -g rg-dev-environment -n dragon --command-id RunShellScript \
  --scripts "curl -fsSL https://tailscale.com/install.sh | sh && tailscale up --auth-key=<EPHEMERAL> --ssh=false --hostname=dragon"
#   revoke the key in the console immediately; record the new 100.x IP

# ---- STEP 6 — SSH host-key verification (control-plane path, before any client trusts) ----
az vm run-command invoke … --scripts "for k in ed25519 ecdsa rsa; do ssh-keygen -lf /etc/ssh/ssh_host_${k}_key.pub; done"
#   then on each client: ssh-keygen -R <old>  &&  add verified new key ; update ~/.ssh/config HostName if IP changed

# ---- STEP 7 — guest bootstrap (see AZ2A.22) ----
#   apt: git curl ca-certificates sqlite3 jq ; uv installer ; uv python install 3.13
#   sshd drop-in: PasswordAuthentication no / PubkeyAuthentication yes / PermitRootLogin no / X11Forwarding no
#   systemctl set-default multi-user.target (if not already)
#   journald drop-in: Storage=persistent, SystemMaxUse=2G, SystemKeepFree=1G, MaxRetentionSec=1month
#   mkfs.ext4 on the data disk; UUID fstab -> /srv/dicks_laboratory (default opts); mkdir data/ logs/ forensic/
#   mountpoint left root:root 0555 when unmounted (fail-closed)

# ---- STEP 8 — Copper deploy ----
git clone git@github.com:bigmcdaddy8/copper.git ~/Documents/REPOs/copper   # via new read-only deploy key
cd ~/Documents/REPOs/copper && git rev-parse HEAD  # == origin/master ; status --porcelain empty
uv sync --frozen --all-packages

# ---- STEP 9 — credential restore ----
scp ~/secure/dragon-pre-rebuild/dragon-env-20260909.env.gpg dragon:/tmp/
ssh dragon 'gpg -d /tmp/dragon-env-20260909.env.gpg > ~/Documents/REPOs/copper/.env && chmod 600 ~/…/.env && shred -u /tmp/dragon-env-20260909.env.gpg'
#   verify restored sha256 == pre-rebuild source sha256 (recorded in the bundle manifest); stat only, never cat

# ---- STEP 10 — validation gate (pre-AZ3) ----
#   boot ok; SSH (new host keys verified) from robby [+ weasel/robyn]; Tailscale up; uv sync clean;
#   /srv/dicks_laboratory mounted; .env present 600; systemctl --failed empty; get-default multi-user
#   THEN Human may authorise deletion of the retained old OS disk dragon_disk1_bb48fd67…
```

## AZ2B.AA — AZ2C safety gates

`az vm delete dragon` must be blocked unless **all** of:

1. `dragon-env-20260909.env.gpg` sha256 verified == recorded.
2. K9-preservation commit is on `origin/master`.
3. old `dragon` repo has no unique uncommitted source (re-checked live).
4. old OS disk `dragon_disk1_bb48fd67…` identified and present.
5. `storageProfile.osDisk.deleteOption == "Detach"` (**verified now** — AZ2B.E).
6. NIC deletion behaviour understood/preserved (**verified now** — default Detach — AZ2B.E).
7. `az account show` → authenticated, expected subscription.
8. pinned image `Canonical:ubuntu-26_04-lts:server:26.04.202609020` still resolves.
9. robby + weasel public keys available; robyn key available or explicitly deferred.
10. Human has approved billable + destructive AZ2C execution.

**Any gate fails → DO NOT DELETE DRAGON.**

## AZ2B.AB — AZ2C billable resources (no creation in AZ2B)

| Resource | Est. monthly cost (eastus retail, 2026-09-09) |
|---|---|
| New 64 GiB StandardSSD_LRS OS disk (E10) | ≈ $9.60 (vs current 32 GiB ≈ $2.40 → **+$7.20/mo**; AZ2A said +$2.40 using an E4→E6 estimate — corrected to E4→E10 here) |
| New 256 GiB StandardSSD_LRS data disk (E15) | ≈ **$19.20** |
| Retained old 32 GiB OS disk (rollback window) | ≈ $2.40 (until Human deletes it post-acceptance) |
| Managed boot diagnostics | negligible |
| B2ms compute (unchanged SKU) | ≈ $0.0832/hr (~$43/mo at the Sun→Fri schedule) |

**Nothing created in AZ2B.**

## AZ2B.AC — Human approval request

AZ2B completed all reversible preservation without further approval. **AZ2C
requires explicit Human authorization** for, together:

- **Config / no-cost:** delete the DevTestLab shutdown schedule; fresh Tailscale
  enrolment (short-lived key); sshd hardening drop-in; `set-default
  multi-user.target`.
- **New billable:** 256 GiB data disk (~$19.20/mo); 64 GiB OS disk (~$9.60/mo);
  transient overlap with the retained 32 GiB old OS disk (~$2.40/mo).
- **Destructive / rebuild:** `az vm delete dragon` (deletes VM object + its MI
  principal; OS disk + NIC retained); `az vm create dragon` on the pinned
  26.04.1 image with Trusted Launch; eventually delete the retained old OS disk
  after AZ4 acceptance.

Also outstanding for Human (non-blocking, ideally before AZ2C):
- run the one interactive `.env` encryption command (AZ2B.G) and report the sha256;
- (optional) verify weasel→dragon SSH from weasel;
- (optional) enrol robyn in the tailnet + generate robyn's key.

---

```
0W-AZ2B: PRESERVATION COMPLETE — READY FOR REBUILD APPROVAL
         (one non-blocking Human step outstanding: interactive .env encryption — AZ2B.G;
          .env itself is already preserved on the retained old OS disk)

DRAGON DELETED/REBUILT      : NO
NEW AZURE BILLABLE RESOURCES: NONE
K9                         : PRESERVED / PAUSED  (7 timers disabled, unit files retained + in Git)
```

---

# Phase 0W-AZ2C — Dragon Generation 1 Rebuild & Futures-Host Bootstrap

**Executed 2026-09-09 from `robby`.** Destructive rebuild performed under Human
authorization + all pre-delete gates. VM object replaced; **old 24.04 OS disk
retained**. Guest bootstrap done via Azure Run Command (control-plane root);
Tailscale later enrolled via persistent browser auth, after which
administration is ordinary OpenSSH over the tailnet.

```
0W-AZ2C: REBUILD COMPLETE — DRAGON GENERATION 1 READY FOR AZ3
```

**Update (later same day):** the initial BLOCK — Tailscale enrolment — was
resolved by the Product-Owner-preferred method: a **persistent** (non-ephemeral)
`tailscale up --hostname=dragon` with **no** `--auth-key` / `--ephemeral` /
`--ssh`, launched as an independent transient unit via Azure Run Command, which
emitted a browser login URL that Human authorized in an already-signed-in
Tailscale session. The node came up healthy; robby SSH, `.env` restore, and all
acceptance checks then passed.

## AZ2C.A — Pre-delete safety gates

| Gate | Result |
|---|---|
| G1 `.env` encrypted backup byte-for-byte vs source | **PASS** — `SHA256(dragon:.env)` = `SHA256(gpg -d dragon-env-20260909.env.gpg)` = `eae1c7d1d5ac82fd70ac9bc4bc644b475714b765c14d2eaa1840c0da0d8582ef` (source 1493 B, mode 600). Encrypted artifact `~/secure/dragon-pre-rebuild/dragon-env-20260909.env.gpg` — 1025 B, mode 600, sha256 `3f352b375759f95c6d343d9cf84cc0ee0cc152e237f54cf1f987c06995589838`, AES-256 symmetric. (Human's 2026-09-09 15:49 run; gpg-agent cache was reloaded afterward.) `.env` contents never printed. |
| G2 K9-preservation commits on `origin/master` | **PASS** — `0750b9d` + `c09e8ee` ancestors of `origin/master`; local HEAD == origin/master |
| G3 old dragon checkout has no unique source | **PASS** — `git status --porcelain` empty, `git stash list` empty, HEAD `1c433e3` (published ancestor) |
| G4 old OS disk exists / identified | **PASS** — `dragon_disk1_bb48fd67c68342b4b4596a45879297f9`, StandardSSD_LRS, Gen2, Linux |
| G5 old OS disk `deleteOption == Detach` | **PASS** |
| G6 `dragon-nic` survives VM deletion | **PASS** — VM `networkProfile…deleteOption == null` → default Detach |
| G7 correct Azure account/subscription | **PASS** — "Pay-as-you-go", `temckee8@outlook.com` |
| G8 pinned image resolves | **PASS** — `Canonical:ubuntu-26_04-lts:server:26.04.202609020` (V2, x64) |
| G9 robby + weasel public SSH keys available | **PASS** — captured from Gen-0 `authorized_keys` before deletion (robby `SHA256:2WcJz…we2cg`, weasel `SHA256:0Ono…rEnk`); robyn **DEFERRED** |
| G10 Human authorization | **PASS** — recorded in the 0W-AZ2C task |
| dragon PowerState | **deallocated** before delete |

## AZ2C.B — Generation-0 VM deletion

| | |
|---|---|
| `az vm deallocate` | 2026-09-09 20:56 UTC, rc 0 → `PowerState/deallocated` |
| `az vm auto-shutdown --off` | rc 0 — DevTestLab `shutdown-computevm-dragon` **deleted**; `az resource list …DevTestLab/schedules` in RG = `[]`; `az resource show shutdown-computevm-dragon` → ResourceNotFound |
| `az vm delete -g rg-dev-environment -n dragon --yes` | 20:56:53 → 20:57:26 UTC, rc 0 |
| VM object | **gone** (`az vm show dragon` → ResourceNotFound) |

## AZ2C.C — Rollback disk state (post-deletion)

`dragon_disk1_bb48fd67c68342b4b4596a45879297f9` — **PRESENT, `diskState:
Unattached`, StandardSSD_LRS, Gen2, Linux, provisioningState Succeeded** — byte
unchanged, not touched. `dragon-nic` — PRESENT, `virtualMachine: null`
(unattached), private IP `10.0.1.4` Dynamic, no public IP. `dragon-vnet` /
subnet `default` / `dragon-nsg` / automation accounts — all intact. **Rollback
remains possible.**

## AZ2C.D — DevTestLab shutdown removal

`shutdown-computevm-dragon` (`Microsoft.DevTestLab/schedules`) — **removed** in
AZ2C.B. Re-verified after the rebuild: `az resource list --resource-type
Microsoft.DevTestLab/schedules -g rg-dev-environment` → `[]`. **No daily
06:08 UTC shutdown remains.** The Sunday→Friday Automation schedule is **not**
created (AZ3).

## AZ2C.E — Data disk creation

`az disk create -g rg-dev-environment -n dragon-data1 --size-gb 256
--sku StandardSSD_LRS --hyper-v-generation V2` (tags `purpose=dicks_laboratory
role=futures-data`) — rc 0, `provisioningState Succeeded`, `diskState
Unattached`, `uniqueId a39bfa99…`, eastus. No filesystem at create.

## AZ2C.F — Generation-1 VM creation

`az vm create -g rg-dev-environment -n dragon` — rc 0, 2026-09-09
20:58:01→20:59:06 UTC. Args: `--image
Canonical:ubuntu-26_04-lts:server:26.04.202609020 --size Standard_B2ms
--nics dragon-nic --security-type TrustedLaunch --enable-secure-boot true
--enable-vtpm true --os-disk-name dragon-osdisk-gen1 --os-disk-size-gb 64
--storage-sku os=StandardSSD_LRS --os-disk-delete-option Detach
--attach-data-disks dragon-data1 --data-disk-caching None
--admin-username temckee8 --ssh-key-values <robby.pub> <weasel.pub>
--public-ip-address "" --assign-identity [system] --nic-delete-option Detach`.
No `--custom-data` (no cloud-init secret). Result: `powerState VM running`,
`privateIpAddress 10.0.1.4`, `publicIpAddress ""`.

## AZ2C.G — Exact Azure image

`storageProfile.imageReference` = `Canonical / ubuntu-26_04-lts / server /
26.04.202609020` (`exactVersion 26.04.202609020` — **pinned, not `:latest`**).

## AZ2C.H — Actual guest Ubuntu version

`/etc/os-release`: **`PRETTY_NAME="Ubuntu 26.04.1 LTS"`**, `VERSION="26.04.1
LTS (Resolute Raccoon)"`, `VERSION_ID="26.04"`, codename `resolute`. Kernel
**`7.0.0-1012-azure`**, `x86_64`. hostname `dragon`, virt `microsoft`, Machine
ID `9c109154…` (new). `timedatectl`: tz `Etc/UTC`, **clock synchronized: yes**,
**NTP service: active**. **Exactly the target point release** — no substitution.

## AZ2C.I — Trusted Launch / Secure Boot / vTPM

Azure: `securityType TrustedLaunch`, `uefiSettings.secureBootEnabled true`,
`uefiSettings.vTpmEnabled true`. Guest: `mokutil --sb-state` → **"SecureBoot
enabled"**; **`/dev/tpm0` + `/dev/tpmrm0` present**. Hyper-V generation V2. ✔

## AZ2C.J — New OS disk

`dragon-osdisk-gen1` — StandardSSD_LRS, 64 GiB, `deleteOption Detach`. Guest
`lsblk`: `sda` 64G → `sda1` 62.9G ext4 `/`, `sda13` 1023M ext4 `/boot`,
`sda15` 106M vfat `/boot/efi`.

## AZ2C.K — New data disk

`dragon-data1` — StandardSSD_LRS, 256 GiB, LUN 0, host caching **None**. Guest:
`/dev/disk/azure/scsi1/lun0 → /dev/sdc` (256 G, no partition table — whole-disk
ext4).

## AZ2C.L — Data mount / filesystem

- `mkfs.ext4` on `/dev/sdc` (**default mount options — no `commit=30`**), label
  `dicks_lab`, **UUID `890b7de2-a7e1-4650-a7c9-464124698b29`**.
- `/etc/fstab` (UUID-based): `UUID=890b7de2-… /srv/dicks_laboratory ext4
  defaults,nofail 0 2`.
- Mounted: `findmnt` → `/srv/dicks_laboratory ← /dev/sdc ext4 rw,relatime`;
  `df` → 251 G size, 239 G avail.
- Subdirs `data/ logs/ forensic/` created, owned `temckee8:temckee8`.
- **Backing device proven** = `/dev/sdc` = `dragon-data1` (LUN 0) — **not**
  `sda` (OS), **not** `sdb` (Azure temp).
- **Fail-closed verified:** with the disk unmounted, the underlying
  `/srv/dicks_laboratory` directory is `dr-xr-xr-x root:root` (0555) → a write
  before mount fails; remount succeeds. (The collector unit's
  `RequiresMountsFor=` / `ConditionPathIsMountPoint=` is added in AZ3.)

## AZ2C.M — Azure temporary disk

`sdb` 16 GiB → `sdb1` ext4 at **`/mnt`** = the Azure **EPHEMERAL** resource
disk. A `/mnt/README.EPHEMERAL` marker was written ("wiped on every
deallocate/reallocate; do not place Copper, .env, datasets, logs, forensic
evidence, or journald here"). Nothing of the Laboratory is on it.

## AZ2C.N — New managed identity / RBAC

New SystemAssigned MI principal `d8aa6899…` (distinct from Gen-0's `da55ad8d…`;
full ID held out of this doc). **`az role assignment list --assignee
<new-principal>` → `[]` — NO role assignments.** `az vm create` even warned
"No access was given yet … because '--scope' was not provided." **Generation-0
RBAC (RG `Contributor`, VM `Contributor`, `Classic VM Contributor`) is NOT
restored** — least privilege, as designed. The two Automation-account SPs
(`6d277e79…`, `563c2651…`) retain `Virtual Machine Contributor` at the
`dragon` VM scope (name-based ID, survived) — retained for the AZ3 Sunday-start
Automation; the guest itself has no Azure power.

## AZ2C.O — Boot diagnostics

`az vm boot-diagnostics enable -g rg-dev-environment -n dragon` — **managed
boot diagnostics enabled** (`diagnosticsProfile.bootDiagnostics.enabled:
true`).

## AZ2C.P — Generation-1 SSH host fingerprints ("DRAGON GENERATION 1" / 26.04)

| Alg | SHA256 | Gen-0 (now historical) |
|---|---|---|
| ED25519 | `3pirEF7Ey1G79JwcP9X8zY/fSuPv2sbSjHHLN66r4Rk` | `Ai0gLE1EfclvMCXsGEND18JvgcMm1g6LuddNI3ocEao` |
| ECDSA | `JBj1HY2v0nzFboecNyeUzxMaSaw7dIVzVwuNNcy+36Y` | `UIHlwBK/B/6cJRl5VyyU9syNZk3t1576o7pTTwHZ+no` |
| RSA | `QLisfhNHOLQv+w8LdygUEAHX/QyIhvkYCPn0mFiiDoc` | `GOaHj0YqlEZ7Z4bcH2ZJNHsbKLil3WyfEe6Q6i2QQos` |

Collected via **Azure Run Command** (control-plane, trusted path), then
re-confirmed by a live `ssh-keyscan` over the tailnet (AZ2C.R) — the two
match. Differ from Generation 0 as expected. Now installed in robby's
`known_hosts` for `100.64.112.117,dragon-1` (old `dragon`/`100.103.127.127`
entries removed).

## AZ2C.Q — Tailscale fresh enrolment — **BLOCKED (needs Human)**

**Method (Product-Owner-preferred — persistent node, browser auth):** an
ephemeral node is *inappropriate* for `dragon` (a persistent server whose Azure
VM intentionally deallocates Fri and returns Sun). Via Azure Run Command:
`curl -fsSL https://tailscale.com/install.sh | sh` → `systemctl enable --now
tailscaled` → **`systemd-run --unit=ts-up --service-type=exec /usr/bin/tailscale
up --hostname=dragon --accept-dns=false --reset`** (a transient unit, so the
headless auth wait survives the Run Command returning) — **no `--auth-key`, no
`--ephemeral`, no `--ssh`**. The unit printed
`https://login.tailscale.com/a/…`; Human opened it in an already-authenticated
browser and the node registered (the tailnet does not gate new devices).
`ts-up.service` exited `Result=success` ("Success.").

**Result:** stable client **1.102.3**, `tailscaled` **active + enabled**. New
node — internal hostname `dragon`, **tailnet machine name `dragon-1`** (the
name `dragon` is still held by the stale Gen-0 machine record), DNSName
`dragon-1.taildb247e.ts.net`, **IPv4 `100.64.112.117`** (IPv6
`fd7a:115c:a1e0::9838:7076`), `BackendState Running`, `Online: true`,
`Health: []` (no warnings), no tags. Ordinary OpenSSH over this transport is
the admin model; Tailscale SSH is **not** enabled.

**Device key expiry:** initially **enabled**, deadline `2027-03-08T21:25:44Z`
(~180 d). Human **disabled key expiry** for `dragon-1` in the admin console →
re-verified `KeyExpiry: None`. A persistent unattended collection host must not
carry a silent re-auth deadline — keep expiry disabled for this node (revisit
only if a tag/ACL model is later adopted).

**Stale Gen-0 node:** `dragon` `100.103.127.127`, offline (VM object already
deleted). **Left in place** until Gen-1 was confirmed healthy + robby SSH
passed (both now true) — safe to remove now; see AZ2C.AJ.

## AZ2C.R — Robby SSH verification — **PASS**

```
ROBBY → DRAGON GEN1 SSH: PASS
```

1. `ssh-keyscan 100.64.112.117` ED25519 =
   `SHA256:3pirEF7Ey1G79JwcP9X8zY/fSuPv2sbSjHHLN66r4Rk` — **matches** the
   control-plane value (AZ2C.P) exactly. **HOST KEY MATCH: PASS.**
2. robby `~/.ssh/known_hosts` — old `100.103.127.127` / `dragon` entries
   removed (`ssh-keygen -R`; backup `known_hosts.old`); the just-verified
   Gen-1 keys added for `100.64.112.117,dragon-1`.
3. `~/.ssh/config` (backup `config.pre-az2c`): `Host dragon` →
   `HostName 100.64.112.117`, and `StrictHostKeyChecking` tightened
   `accept-new` → **`yes`**.
4. `ssh -o StrictHostKeyChecking=yes dragon` → `SSH_OK host=dragon
   user=temckee8 kernel=7.0.0-1012-azure os=26.04.1 LTS`; `ssh -v` →
   `Authenticated to 100.64.112.117 ([100.64.112.117]:22) using "publickey"`
   (`id_ed25519`).

## AZ2C.S — SSHD baseline

`/etc/ssh/sshd_config.d/60-dicks.conf`:
```
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
X11Forwarding no
KbdInteractiveAuthentication no
```
`sshd -t` → OK; `systemctl reload ssh`. Effective (`sshd -T`): `port 22`,
`passwordauthentication no`, `pubkeyauthentication yes`, `permitrootlogin no`,
`x11forwarding no`, `kbdinteractiveauthentication no`. No `AllowUsers`, no port
change. (Recovery path during changes = Azure Run Command, always available.)

## AZ2C.T — Time / NTP / default target

tz `Etc/UTC`, `System clock synchronized: yes`, `NTP service: active`.
`systemctl set-default multi-user.target` → `systemctl get-default` =
**`multi-user.target`**. No GUI installed. `systemctl --failed` → empty.
`sleep.target` / `suspend.target` / `hibernate.target` → all `inactive`.

## AZ2C.U — Journald

`/etc/systemd/journald.conf.d/10-dicks.conf`:
```
[Journal]
Storage=persistent
SystemMaxUse=2G
SystemKeepFree=1G
MaxRetentionSec=1month
```
`systemctl restart systemd-journald`; `/var/log/journal` present (8 M). On the
OS disk (not the data disk), as planned.

## AZ2C.V — Runtime toolchain

| Tool | Version | Source |
|---|---|---|
| git | 2.53.0 | apt (`--no-install-recommends`) |
| curl | 8.18.0 | apt |
| sqlite3 | 3.46.1 | apt |
| jq | 1.8.1 | apt |
| ca-certificates | (current) | apt |
| WALinuxAgent | 2.15.0.1 | image (verified, not reinstalled) |
| cloud-init | 26.1-0ubuntu3~26.04.1 | image (`status: done`) |
| **uv** | **0.12.12** | Astral installer, `~temckee8/.local/bin/uv` (fresh — old `~/.local` **not** copied) |
| CPython (uv-managed) | **3.13.15** | `uv python install 3.13` + `uv sync` |

`build-essential` **not** installed — `uv sync --frozen` succeeded without a
compiler. No `gh` on the guest.

## AZ2C.W — GitHub read access

A **dedicated read-only deploy key** was created on `dragon`
(`~temckee8/.ssh/id_ed25519_ghdeploy`, `SHA256:qwNsG/S7p/FskNZ34xsSuR0jWg6GW/ybeLZZE1qax8Y`,
comment `dragon-gen1-copper-deploy`) and registered on
`bigmcdaddy8/copper` via `gh api` (from robby's authenticated `gh`,
`admin:public_key` scope) as deploy key id **162811278**, `read_only: true`,
`verified: true`. No PAT embedded; no personal private key copied to Azure.
The private key exists only on `dragon` (mode 600). Clone uses
`GIT_SSH_COMMAND="ssh -i …/id_ed25519_ghdeploy -o IdentitiesOnly=yes"`.

## AZ2C.X — Copper clone / commit

`git clone git@github.com:bigmcdaddy8/copper.git
/home/temckee8/Documents/REPOs/copper` (via the deploy key). State:
`branch master`, **HEAD `c09e8eeac675d2bfc9386f49c40d0889dfaf773e`**,
`git status --porcelain` empty, **HEAD == origin/master**. `apps/`: K9, bic,
captains_log, dicks_laboratory, encyclopedia_galactica, holodeck, trade_hunter,
tradier_sniffer. `scripts/dicks_lab_collect_es.py` present.

## AZ2C.Y — Dependency sync

`uv sync --frozen` (uv 0.12.12): resolved from `uv.lock`, CPython **3.13.15**,
`.venv` created, 8 packages installed (`pytest 9.0.2`, `ruff 0.15.9`,
`coverage 7.13.5`, `pytest-cov 7.1.0`, `pygments`, `pluggy`, `iniconfig`,
`packaging`). `uv run python --version` → **Python 3.13.15**
(`.venv/bin/python3`). No collector run.

## AZ2C.Z — `.env` restore verification — **PASS**

**RESTORED — verified byte-identical.** Human ran, on robby:
`gpg --quiet -d ~/secure/dragon-pre-rebuild/dragon-env-20260909.env.gpg | ssh
dragon 'umask 077; cat > ~/…/copper/.env && chmod 600 …'` — plaintext streamed
straight into the file over the tailnet SSH tunnel, no temp copy on either
host. On `dragon`:
`sha256sum ~/Documents/REPOs/copper/.env` =
**`eae1c7d1d5ac82fd70ac9bc4bc644b475714b765c14d2eaa1840c0da0d8582ef`** ==
Generation-0 source. `stat` → `-rw-------` `temckee8:temckee8`, 1493 bytes
(33 lines, 13 keys — matches the AZ1c.Y inventory). `git check-ignore .env` →
`.gitignore:34` (ignored — will not be committed). Contents never printed. The
encrypted master backup stays on robby through AZ4. **No quote-token / DXLink
requested.**

## AZ2C.AA — K9 state

Fresh 26.04 OS disk → **no K9 units installed, none running**
(`systemctl list-unit-files 'copper-k9-*'` → 0). `copper-k9-smart-shutdown`
not installed / not enabled. Definitions remain in `deploy/systemd/` + the
`deploy/k9/PRESERVED.md` note. ✔

## AZ2C.AB — Automatic-update state

`unattended-upgrades` enabled + active; `20auto-upgrades` = daily security
updates. `Unattended-Upgrade::Automatic-Reboot` line **commented → default
`false` → NO automatic reboot** (verified — AZ2C acceptance requirement met).
`needrestart` not present on 26.04 minimal server. `apt-daily-upgrade.timer`
next ~06:32 UTC — full Saturday-maintenance design is **AZ3**, not touched here.

## AZ2C.AC — Multi-client access state

```
robby  : PASS  (live, StrictHostKeyChecking=yes, verified Gen-1 fingerprint, publickey over tailnet — AZ2C.R)
weasel : READY / NOT YET TESTED  (weasel pubkey in dragon authorized_keys; weasel tailnet node active;
         the check must be run from weasel — Human)
robyn  : DEFERRED  (not a tailnet member, no key; to be set up before unattended AZ4/Attempt-4 work)
```

## AZ2C.AD — DevTestLab final state

`shutdown-computevm-dragon` — **ABSENT** (`az resource list …DevTestLab/schedules`
in `rg-dev-environment` → `[]`). No daily 06:08 UTC shutdown. Sunday/Friday
Automation schedule **not** created (AZ3).

## AZ2C.AE — Retained old-OS disk

`dragon_disk1_bb48fd67c68342b4b4596a45879297f9` — **PRESENT, `Unattached`,
StandardSSD_LRS, 32 GiB, Linux, unchanged.** Not deleted. Rollback =
`az vm create -n dragon --attach-os-disk dragon_disk1_bb48fd67… --os-type
Linux --nics dragon-nic --size Standard_B2ms` (would require deleting the Gen-1
VM first). Retain until AZ4 acceptance.

## AZ2C.AF — Migration document

This 0W-AZ2C section appended. Records Generation 1: exact image, actual
Ubuntu 26.04.1, new host fingerprints, disk identities + UUID, Trusted Launch
state, runtime versions, deployed commit `c09e8ee`, `.env` restore
verification, Tailscale node identity, and rollback disk state. No secret
material (MI object IDs held out; no Tailscale key was used — browser auth).

## AZ2C.AG — Repository changes

Documentation only (this section). No Copper source/bootstrap files added —
the guest bootstrap was performed directly on `dragon`, and its steps are
recorded here for reproducibility. `git diff --check` clean.

## AZ2C.AH — Final git state

```
robby: master · HEAD == origin/master · working tree clean
```
(hash in handoff)

## AZ2C.AI — AZ2C acceptance

| Bar item | State |
|---|---|
| Pinned image used exactly | ✔ `26.04.202609020` |
| Ubuntu 26.04 LTS guest verified | ✔ `26.04.1 LTS` |
| Trusted Launch / Secure Boot / vTPM | ✔ / ✔ / ✔ |
| 64 GiB persistent OS disk | ✔ `dragon-osdisk-gen1` |
| 256 GiB persistent data disk | ✔ `dragon-data1` |
| `/srv/dicks_laboratory` mounted correctly | ✔ `/dev/sdc`, UUID fstab, fail-closed verified |
| Azure ephemeral disk not used | ✔ `/mnt` labeled EPHEMERAL |
| DevTestLab daily shutdown absent | ✔ |
| Tailscale healthy | ✔ node `dragon-1` `100.64.112.117`, Online, `Health []`, key-expiry disabled |
| no public IP / NSG unchanged | ✔ / ✔ |
| Gen-1 SSH host keys independently verified | ✔ control-plane (AZ2C.P) **and** live scan (AZ2C.R) match |
| robby SSH PASS | ✔ **PASS** (AZ2C.R) |
| sshd baseline applied safely | ✔ |
| multi-user.target | ✔ |
| persistent/bounded journald | ✔ |
| Copper fresh clone / HEAD == origin/master | ✔ `c09e8ee` |
| `uv sync --frozen` PASS / Python 3.13 | ✔ / ✔ `3.13.15` |
| `.env` restored byte-identical / 600 | ✔ **PASS** — sha256 `eae1c7d1…82ef`, `-rw-------` temckee8 |
| K9 not installed/running | ✔ |
| no futures collector running | ✔ |
| old 24.04 OS disk retained | ✔ `Unattached` |

**ALL acceptance items PASS.**

## AZ2C.AJ — Cleanup carried forward (does not block AZ2C)

1. **Stale Gen-0 tailnet node** `dragon` (`100.103.127.127`, offline, VM object
   already deleted) — now safe to remove (Gen-1 healthy + robby SSH PASS).
   Human: admin console → Machines → `dragon` (kernel `6.17.0-1022-azure`,
   last seen ~3:56 PM CDT) → ⋯ → Remove. **Do not remove the Connected
   `dragon-1`.**
2. **Rename `dragon-1` → `dragon`** (optional, cosmetic) — only after step 1;
   the tailnet IP `100.64.112.117` does not change on rename, so robby's
   `~/.ssh/config` needs no further edit.
3. **weasel** — run the client-side SSH check from weasel against
   `100.64.112.117` and confirm the host fingerprint vs AZ2C.P.
4. **robyn** — enrol in the tailnet + issue a dedicated keypair; add its
   public key to `dragon:~/.ssh/authorized_keys` before unattended AZ4 work.
5. **Deploy key** `dragon-gen1-copper-deploy` (GitHub id 162811278, read-only)
   — keep; it is the guest's Copper pull mechanism.
6. Post-AZ4 acceptance: Human deletes the retained old OS disk
   `dragon_disk1_bb48fd67…`.

---

```
0W-AZ2C: REBUILD COMPLETE — DRAGON GENERATION 1 READY FOR AZ3

OLD 24.04 OS DISK  : RETAINED (Unattached, unchanged)
K9                 : PRESERVED / PAUSED (not installed on Gen-1)
FUTURES COLLECTOR  : NOT STARTED
NEXT               : 0W-AZ3 — power scheduling (Sun→Fri) + futures systemd supervisor + Saturday maintenance
```

---

# Phase 0W-AZ3 — Azure Power Lifecycle + Daily Futures Session Supervision

**Executed 2026-09-09 from `robby`.** Turns Generation 1 into an operational
(but **not yet live-armed**) collection platform. No DXLink / quote-token /
market activity. The daily collector timer is installed and validated but
**left DISABLED** pending 0W-AZ4.

## AZ3.O — Collector architecture decision

```
DAILY PROCESS PER TRADING DATE — NOT ONE MULTI-DAY PROCESS
```

Two independent lifecycles:

| | Azure host | Collector |
|---|---|---|
| cadence | starts Sun ~15:30 CT, runs continuously, deallocates Fri ~16:45 CT, off Sat | one bounded process per ordinary CME trading date |
| launch | Automation schedules (control-plane) | systemd timer `Sun–Thu 16:55:00 America/Chicago` |
| span | week | 17:00 CT → next day ~16:00 CT close; process self-exits ~16:10 |
| gap | — | ≈45 min between a completed run and the next 16:55 launch |
| credential | — | **fresh DXLink quote token per trading date** |

A multi-day collector would violate the 0W-2D credential-lifetime model
(24 h quote-token lifetime; horizon guard = requested duration + 900 s must fit
inside remaining token lifetime). Daily bounded processes keep that guarantee
and isolate every outage/session.

## AZ3.C — Generation-0 daily-start root cause — **IDENTIFIED**

The `az automation schedule` CLI extension returned `[]` (incomplete). ARM REST
(`.../automationAccounts/<acct>/schedules?api-version=2015-10-31`) plus the
subscription **Activity Log** (90 d) give the definitive picture:

| Gen-0 lifecycle leg | Mechanism | Evidence |
|---|---|---|
| **START** ~05:45 CT (10:45–10:47 UTC) Mon–Fri | Automation account **`automation-k9`**, schedule **`dragon-start-weekday`** (`frequency Week`, `timeZone America/Chicago`, weekDays [everyday-ish], **was enabled**) → runbook `automation-k9/Start-Dragon` (PowerShell 5.1, MSI ARM-REST `.../start`) | Activity Log: every weekday `Start Virtual Machine` `caller = 7738af74…` `appid = 563c2651…` = **`automation-k9` managed identity** |
| **STOP** ~10:15 CT (15:15 UTC) Mon–Fri | guest `copper-k9-smart-shutdown.timer` → `scripts/smart_shutdown.sh` → Gen-0 guest MI `az vm deallocate` | Activity Log: every weekday `Deallocate` `caller = da55ad8d…` `appid = 6d277e79…` = **Gen-0 guest MI** |
| STOP backstop | DevTestLab `shutdown-computevm-dragon` 06:08 UTC | (rarely reached; VM already down) |
| a disabled sibling | `automation-k9/dragon-start-saturday` (Saturday 10:45 CT) — `isEnabled: false` | ARM REST |

`automation-dragon`'s `Start-Dragon` runbook existed but had **no schedule** —
never wired up.

## AZ3.D — Competing-trigger cleanup

- **`automation-k9/dragon-start-weekday`** — `PATCH isEnabled=false` (ARM REST).
  Re-verified: both `automation-k9` dragon schedules now `isEnabled: false`.
- The Gen-0 **guest stop** (`copper-k9-smart-shutdown`) — already gone (fresh
  26.04 OS disk; not installed — 0W-AZ2C / `deploy/k9/PRESERVED.md`).
- The **DevTestLab 06:08 UTC** schedule — already deleted (0W-AZ2C).
- **RBAC declaw:** after the VM delete/recreate the old VM-scoped `Virtual
  Machine Contributor` grants to the Automation SPs did **not** survive — `az
  role assignment list --scope <Gen-1 VM>` = `[]`. So even if a stale k9
  schedule fired, its MI has no permission to start Gen-1 `dragon`. Both
  belt (disabled) and suspenders (no RBAC) are in place.

```
OLD DAILY START TRIGGER: IDENTIFIED (automation-k9/dragon-start-weekday → automation-k9/Start-Dragon) — DISABLED + RBAC-incapable
```

## AZ3.E — Authoritative Automation account

```
automation-dragon : AUTHORITATIVE POWER CONTROLLER for the dragon futures host
automation-k9      : NOT used for dragon futures power (its Start-Dragon + 2 schedules left disabled/unlinked; K9's own account otherwise untouched)
```

- `automation-dragon` MI principal `0c24e4c8…`.
- **New RBAC grant (AZ3):** `Virtual Machine Contributor` scoped **exactly to
  the `dragon` VM resource** (`az role assignment create --assignee-object-id
  <MI> --role "Virtual Machine Contributor" --scope <dragon VM id>`). This is
  the minimum needed for start/stop.
- Its pre-existing `Classic Virtual Machine Contributor` @ RG (deprecated ASM,
  grants nothing on ARM VMs) was **removed** as redundant (least privilege).
- `automation-k9` MI holds **no** role assignment on `dragon` (nothing to
  remove there).
- **Guest MI:** the Generation-1 guest managed identity has **zero** role
  assignments and is granted **none** — power control lives entirely in the
  control plane (no guest self-deallocation).

## AZ3.F — Start-Dragon runbook

`deploy/azure/automation/Start-Dragon.ps1` → published to
`automation-dragon` (PowerShell 7.2, `state: Published`). Replaces the prior
3-line stub. Behaviour: `Connect-AzAccount -Identity` → read `PowerState` → if
`running`, log **no-op success and return**; else `Start-AzVM`, re-read
`PowerState`, **throw** unless `running`, emit `Start-Dragon: OK (before ->
after)`. No secret, no webhook, no guest dependency; idempotent.

## AZ3.G — Stop-Dragon runbook

`deploy/azure/automation/Stop-Dragon.ps1` → newly created + published to
`automation-dragon` (PowerShell 7.2). Symmetric to Start-Dragon: if already
`deallocated`, no-op success; else `Stop-AzVM -Force`, verify
`PowerState/deallocated`, else throw. **Host scheduling only** — it does not
inspect or kill the collector; Friday timing (16:45 CT) is ~35 min after the
collector's expected clean exit (~16:10 CT), which must already have happened.

## AZ3.H — Sunday start schedule

| | |
|---|---|
| name | `dicks-futures-dragon-start` (in `automation-dragon`) |
| frequency / interval | `Week` / 1 |
| weekDays | `["Sunday"]` |
| **timeZone** | **`America/Chicago`** (named tz — DST follows Chicago, **no fixed UTC**) |
| isEnabled | `true` |
| linked runbook | `Start-Dragon` (jobSchedule `0ab59016-…`) |
| nextRun (local) | `2026-09-13T15:30:00-05:00` → **Sun 15:30 CT** |
| nextRun (UTC) | `2026-09-13T20:30:00Z` |

## AZ3.I — Friday stop schedule

| | |
|---|---|
| name | `dicks-futures-dragon-stop` (in `automation-dragon`) |
| frequency / interval | `Week` / 1 |
| weekDays | `["Friday"]` |
| **timeZone** | **`America/Chicago`** |
| isEnabled | `true` |
| linked runbook | `Stop-Dragon` (jobSchedule `78720c51-…`) |
| nextRun (local) | `2026-09-11T16:45:00-05:00` → **Fri 16:45 CT** |
| nextRun (UTC) | `2026-09-11T21:45:00Z` |

**DST proof:** the schedules store `timeZone: America/Chicago` (not a UTC
constant); Azure Automation recomputes the local trigger each week, so after
the 2026-11-02 CDT→CST transition the same schedules fire at 15:30 / 16:45 CST
(21:30 / 22:45 UTC). No daily Azure shutdown; no guest self-deallocation.

## AZ3.J — Runbook / schedule links

`.../jobSchedules` on `automation-dragon`:
```
dicks-futures-dragon-start  -> Start-Dragon   (0ab59016-a1bc-4097-ab1e-d760e912e2dc)
dicks-futures-dragon-stop   -> Stop-Dragon    (78720c51-af4e-4e49-8aee-382941274307)
```

## AZ3.K — Start manual test

Submitted `Start-Dragon` as an on-demand Automation job while the VM was
**running**. Job → `Completed`. Output:
```
Start-Dragon: initial PowerState = PowerState/running
Start-Dragon: already running -- no-op success.
```
VM stayed `PowerState/running`; guest `uptime` unchanged → **no accidental
restart**. (A from-`deallocated` start + timing is exercised in AZ3.N.)

## AZ3.L — Stop manual test

`Stop-Dragon` submitted as an on-demand job while the VM was **running** →
output `Stop-Dragon: OK (PowerState/running -> PowerState/deallocated)`; VM
reached `PowerState/deallocated`. **PASS.**

## AZ3.M — Start / Stop idempotence

- **Start-Dragon while running** → job `Completed`, "already running -- no-op
  success"; VM unchanged, guest `uptime` unchanged (no restart). **PASS.**
- **Stop-Dragon while deallocated** → job `Completed`, "already deallocated --
  no-op success"; VM stays `deallocated`. **PASS.**

## AZ3.N — Data-disk persistence across Automation deallocate/restart

Full sequence executed at phase end (no market connection):

| Step | Result |
|---|---|
| `Stop-Dragon` (VM running) | `running -> deallocated` — **PASS** |
| `Stop-Dragon` again | "already deallocated -- no-op success" — **PASS** (idempotent) |
| `Start-Dragon` (from deallocated) | `deallocated -> running` — **PASS** |
| timing: job submit → `PowerState/running` | **≈ 2 min 16 s** (22:15:17Z → 22:17:33Z) |
| timing: job submit → SSH available over tailnet | **≈ 2 min 21 s** (SSH_UP 22:17:38Z) — the persistent Tailscale node reconnects within seconds of boot |
| post-restart: `/srv/dicks_laboratory` auto-mounted | **yes** — `findmnt` → ext4, **UUID `890b7de2-a7e1-4650-a7c9-464124698b29`** (unchanged), 250.9 G |
| post-restart: `data/ logs/ forensic/ data/sessions/` | intact, owned `temckee8`; write+delete probe as `temckee8` OK |
| post-restart: `systemctl --failed` | none |
| post-restart: collector timer | still `disabled` / `inactive` |
| post-restart: apt automation | still `disabled` / masked (survives reboot) |
| post-restart: time sync / Tailscale | `synchronized: yes`, `NTP: active`; node `100.64.112.117` online |
| `Stop-Dragon` (final) | `running -> deallocated` — **PASS** (phase-end state) |

The UUID-based fstab entry made the data disk reattach correctly despite the
Azure `/dev/sdX` letter shuffling between boots (data disk seen as `/dev/sdc`
at rebuild, `/dev/sda` here). **Persistent-disk behaviour across Azure
deallocate/reallocate: PROVEN.**

*(This margin comfortably fits the schedule: the Sunday `Start` fires 15:30 CT,
~85 min before the collector timer's 16:55 CT launch and ~90 min before the
17:00 CT open.)*

## AZ3.P — Canonical collector command

Audited against `scripts/dicks_lab_collect_es.py` (`--help`) and the accepted
Attempt-3 / Attempt-4 units (`FULL_SESSION_MULTIDAY_SOAK_REPORT.md`
§DD / §HE / §2351):

```
uv run --frozen python scripts/dicks_lab_collect_es.py \
    --duration 83700 \
    --data-dir /srv/dicks_laboratory/data/sessions
```

- `--duration 83700` — canonical (23 h 15 m). `83700 + 900` (horizon-guard
  margin `_QUOTE_TOKEN_HORIZON_MARGIN_SECONDS`) `= 84600`; fresh ~24 h token
  `≈ 86400` → **~1800 s initial headroom** (unchanged 0W-2D design).
- `--symbol` — omitted → default `/ESU6`; the script rejects anything else and
  resolves it against live futures metadata to `/ESU26:XCME`
  (`_ES_STREAMER_SYMBOL`).
- `--max-reconnect-attempts` (5), `--max-events` (1_000_000) — defaults,
  unchanged (disconnect fuse / writer / retry model per 0W-2B / 0W-2D).
- **Dropped:** the robby-era `systemd-inhibit --what=sleep:idle` wrapper —
  dragon is a headless server VM with no sleep/suspend (0W-AZ2C.T).
- **`--data-dir`** overridden from the repo-local default to
  **`/srv/dicks_laboratory/data/sessions`** (persistent managed disk). No
  phase-specific `0w2_attempt4` name in the permanent unit — AZ4 / formal
  Attempt-4 use explicit override dirs.
- **No collector semantics changed** — retry/token/writer/integrity untouched.
  No production Python change in AZ3.

## AZ3.Q — Systemd service — `dicks-lab-es-session.service`

`deploy/dicks_laboratory/systemd/dicks-lab-es-session.service`, installed at
`/etc/systemd/system/` (system-level; **not** `--user`, no linger, no
`systemd-inhibit`, no session/GUI owner).

| Setting | Value | Why |
|---|---|---|
| `Type` | `simple` | matches accepted soak units |
| `User` / `Group` | `temckee8` | AZ2A.23 initial decision (repo owner; service acct is post-0W-4) |
| `WorkingDirectory` | `/home/temckee8/Documents/REPOs/copper` | |
| `Environment=PATH` | includes `/home/temckee8/.local/bin` | locate `uv` |
| `RequiresMountsFor` + `ConditionPathIsMountPoint` | `/srv/dicks_laboratory` | fail-closed |
| `AssertPathExists` | `…/copper/.env` | fail-closed on missing creds |
| `ExecStartPre` (1) | `/usr/bin/mountpoint -q /srv/dicks_laboratory` | runtime mount proof |
| `ExecStartPre` (2) | `.env` is `600` and owned `temckee8` | runtime cred proof (no secret printed) |
| `ExecStart` | `…/uv run --frozen python scripts/dicks_lab_collect_es.py --duration 83700 --data-dir /srv/dicks_laboratory/data/sessions` | canonical (AZ3.P), absolute `uv` |
| `KillSignal` / `TimeoutStopSec` | `SIGINT` / `180` | graceful finalize (accepted pattern) |
| `RuntimeMaxSec` | `84300` | launch 16:55 + 83700 → collector self-exit ~16:10; systemd SIGINT backstop ~16:20, SIGKILL ~16:23 — **≥30 min before the next 16:55 launch**; the unit can never overlap the next trading date |
| `Restart` | `no` | a fatal collector exit stays **failed** — no late relaunch masquerading as a complete session (0W-2 Attempt-4 lesson). Transient DXLink reconnects are handled inside the collector. |
| `MemoryAccounting` | `yes` | metrics |
| `[Install]` | **absent** | started only by the timer |

`systemd-analyze verify` → clean.

## AZ3.R — Systemd timer — `dicks-lab-es-session.timer`

`deploy/dicks_laboratory/systemd/dicks-lab-es-session.timer`, installed at
`/etc/systemd/system/`.

```
OnCalendar=Sun,Mon,Tue,Wed,Thu *-*-* 16:55:00 America/Chicago
AccuracySec=1s
RandomizedDelaySec=0
Persistent=false
Unit=dicks-lab-es-session.service
[Install] WantedBy=timers.target
```

`systemd-analyze calendar` (on the host) → normalized `Mon..Thu,Sun *-*-*
16:55:00 America/Chicago`; next 6 occurrences all **16:55 CT (21:55 UTC CDT)**,
Sun/Mon/Tue/Wed/Thu, **no Fri/Sat**. DST spot check:
`2026-11-16 16:55 America/Chicago` → `22:55 UTC` (CST) — tz-name semantics
follow DST. `RandomizedDelaySec=0`, `AccuracySec=1s` → predictable ~16:55
start (a few seconds of systemd latency accepted).

## AZ3.S — Missed-launch semantics

```
MISSED TIMER: remains missed — operator evidence — NO late launch
```

`Persistent=false` (no catch-up). If `dragon` boots late and 16:55 CT has
already passed, systemd does **not** fire the daily collector hours later. A
missed trading date stays visibly missed rather than producing a truncated
"full-session" dataset (0W-2 Attempt-4 lesson).

## AZ3.T — Fail-closed mount test

| Test | Result |
|---|---|
| data disk mounted → `systemctl start` (harmless `sleep` drop-in, real preconditions) | `active (running)`; `ExecStartPre=mountpoint -q` exit 0 — **PASS** |
| data disk genuinely unavailable (`srv-dicks_laboratory.mount` masked + unmounted) → `systemctl start` | **`ActiveState=inactive`, `ConditionResult=no`** — journal: *"skipped, unmet condition check ConditionPathIsMountPoint=/srv/dicks_laboratory"* — **service refused to run the collector — PASS** |
| mount restored → `systemctl start` | runs again — **PASS** |

(Test performed with a temporary `ExecStart=/bin/sleep` drop-in; **no live
collector, no market connection**. Drop-in removed; real `ExecStart` restored;
`systemd-analyze verify` clean.)

## AZ3.U — Overlap / restart policy

- **Overlap:** a single `.service` unit — `systemctl start` while already
  `active` is a no-op. Tested: `MainPID` unchanged, exactly one process —
  **PASS**. No second lock mechanism added.
- **Restart:** `Restart=no`. A daily full-session collector that exits fatally
  must **stay failed** (truthful dataset evidence, no misleading late partial).
  The collector owns transient DXLink reconnects internally
  (`--max-reconnect-attempts 5`).

## AZ3.V — Collector timer final state

```
dicks-lab-es-session.timer   : enabled=disabled   active=inactive
dicks-lab-es-session.service : (static — timer-only)   ActiveState=inactive
```

Installed + fully validated, **left DISABLED / INACTIVE**. 0W-AZ4 arms it
(enable the timer, or a bounded verification override). AZ3 must not let
Sunday auto-produce an unreviewed live dataset.

## AZ3.W — Automatic-update policy

Disabled on `dragon` (smallest set to stop spontaneous package mutation during
Sun→Fri capture):

| Unit | Action |
|---|---|
| `apt-daily.timer`, `apt-daily-upgrade.timer` | `disable --now` |
| `apt-daily.service`, `apt-daily-upgrade.service` | `mask` |
| `unattended-upgrades.service` | `disable --now` |
| `update-notifier-download.timer`, `motd-news.timer` | `disable --now` |

`systemctl list-timers` → no apt/upgrade timers remain. **Kept working:**
`walinuxagent`, `tailscaled`, time sync, `fstrim.timer`.
`/etc/apt/apt.conf.d/20auto-upgrades` left unmodified (restore = re-enable the
timers). `needrestart` is installed but only acts during an apt run → dormant
while apt automation is off. Security updates move to the **Saturday
Maintenance Procedure** (`deploy/dicks_laboratory/SATURDAY_MAINTENANCE.md`) —
operator-initiated for the reliability-proving period; automation is a
post-0W-4 hardening step.

## AZ3.X — Saturday Maintenance Procedure

New: `deploy/dicks_laboratory/SATURDAY_MAINTENANCE.md` — power on manually,
verify data mount by UUID / disk space / failed units / time sync / Tailscale,
`apt-get update && NEEDRESTART_MODE=a apt-get -y full-upgrade`, reboot if
required, optional explicit Copper `ff-only` + `uv sync --frozen --all-packages`, re-verify,
`az vm deallocate`. Includes the exact restore commands for every unit AZ3
disabled, and the Azure `/dev/sdX`-instability warning.

## AZ3.Y — Tailscale Gen-0 cleanup — **DONE (by Human)**

Human removed the stale Gen-0 `dragon` node and the Generation-1 node is now
the sole `dragon` at **`100.64.112.117`** (rename did not change the IP; robby
`~/.ssh/config` `Host dragon` still resolves correctly and SSH is unaffected —
re-verified during the AZ3.N power-cycle). `100.103.127.127` no longer appears
in the tailnet.

## AZ3.Z — Weasel access

`WEASEL → DRAGON GEN1: NOT YET TESTED`. weasel's pubkey
`SHA256:0OnoIpOb4a9jUH6hm7DDOqc3h1E5+y5G3dEXeZHrEnk` is in `dragon`'s
`authorized_keys` and the `weasel` tailnet node is active; the check must run
**from weasel**. To confirm before AZ4: `ssh -o StrictHostKeyChecking=accept-new
temckee8@100.64.112.117 'hostname'` then `ssh-keygen -lf` the offered host key
vs ED25519 `SHA256:3pirEF7Ey1G79JwcP9X8zY/fSuPv2sbSjHHLN66r4Rk`.

## AZ3.AA — Robyn access (instructions for Human, deferred)

1. Join `robyn` to the existing tailnet (`tailscale up`, browser auth).
2. `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_dragon -C "robyn-to-dragon"` —
   **private key stays on robyn**.
3. Send only `~/.ssh/id_ed25519_dragon.pub` + its `ssh-keygen -lf` fingerprint.
4. Append that public key to `dragon:~/.ssh/authorized_keys` (mode 600).
5. From robyn: `ssh -o StrictHostKeyChecking=accept-new
   temckee8@100.64.112.117 'hostname'`; verify the offered ED25519 host key ==
   `SHA256:3pirEF7Ey1G79JwcP9X8zY/fSuPv2sbSjHHLN66r4Rk` before trusting.

Deferred through AZ3; **must** be completed before unattended
Attempt-4 / 0W-4 work.

## AZ3.AB — Files added / changed

| Path | |
|---|---|
| `deploy/dicks_laboratory/systemd/dicks-lab-es-session.service` | new |
| `deploy/dicks_laboratory/systemd/dicks-lab-es-session.timer` | new |
| `deploy/azure/automation/Start-Dragon.ps1` | new (source of the published runbook) |
| `deploy/azure/automation/Stop-Dragon.ps1` | new |
| `deploy/dicks_laboratory/SATURDAY_MAINTENANCE.md` | new |
| `docs/dicks_laboratory/AZURE_COLLECTION_HOST_MIGRATION.md` | this section |

No production Python / collector code changed.

## AZ3.AG — Old 24.04 OS disk

`dragon_disk1_bb48fd67c68342b4b4596a45879297f9` — **retained, `Unattached`,
unchanged.** Retention continues through 0W-AZ4.

---

```
0W-AZ3: OPERATIONAL FOUNDATION COMPLETE — READY FOR AZ4 LIVE VERIFICATION

AZURE SUN→FRI POWER            : ARMED  (dicks-futures-dragon-start Sun 15:30 CT / dicks-futures-dragon-stop Fri 16:45 CT, America/Chicago, via automation-dragon)
DAILY FUTURES COLLECTOR TIMER  : INSTALLED / VALIDATED / DISABLED
LIVE FUTURES COLLECTION        : NOT STARTED
OLD 24.04 OS DISK              : RETAINED
NEXT                          : 0W-AZ4 — short live Azure collector verification
```

---

# Phase 0W-AZ4 — Short Live Azure Collector Verification

**SHORT LIVE AZURE VERIFICATION — NOT A FULL-SESSION PROOF.** First authorized
live futures/DXLink activity on `dragon` Generation 1. 2-hour bounded run of
the real production `systemd` service (temporary `/run`-only override), on a
partial window of CME trading date **2026-09-10**. Executed 2026-09-09
22:38–00:38 UTC from `robby`.

## AZ4.A — AZ3 acceptance
`0W-AZ3: ACCEPTED / CLOSED`. Foundation as recorded in the AZ3 section.

## AZ4.B — Dragon start / host health
`automation-dragon/Start-Dragon` (on-demand job) → `deallocated → running`,
job `Completed`. Submit `22:34:22Z` → SSH over tailnet `22:36:45Z` ≈ **2 min
23 s**. Guest: Ubuntu 26.04.1, kernel `7.0.0-1012-azure`; `/srv/dicks_laboratory`
auto-mounted (ext4, **UUID `890b7de2-a7e1-4650-a7c9-464124698b29`**, 239 G
free); `systemctl --failed` none; clock synchronized / NTP active; Tailscale
node `100.64.112.117` online; collector timer `disabled/inactive`.

## AZ4.C — Repo / commit
robby + dragon both `master` @ **`f8ef3401bfbbe27e9b3a76d66a8ed05953d977ad`**
== `origin/master`, working trees clean. This is the AZ4 collector commit
(also recorded in the dataset's `collector_git_commit`).

## AZ4.D — Production unit integrity
`/etc/systemd/system/dicks-lab-es-session.{service,timer}` verified
byte-identical to `deploy/dicks_laboratory/systemd/` **before** and **after**
the run:
- service `sha256 b48f39db2a74fc9635e64f87d970e9d76dc20d937bb4da58bb7add2794ffbe08`
- timer `sha256 eebe8a9ce01ed7afe602aea6b044d56704f7ca1cd0e284dd64b8ff3a02cb60e5`

## AZ4.E — Safe preflight
`uv run --frozen python scripts/dicks_lab_preflight.py` →
`rest_reachable=true`, `futures_endpoint_usable=true count=539`,
`symbol_/ESU6_resolves=true`,
`streamer_symbol_matches_/ESU26:XCME=true`, **`quote_token_requested=false`**,
`PREFLIGHT_RESULT=PASS` (exit 0). No DXLink quote token requested.

**Deployment gap found + fixed (not a code defect):** the first preflight
attempt failed `ModuleNotFoundError: No module named 'typer'` — the AZ2C/AZ3
`uv sync --frozen` had installed only the **empty workspace root** + dev group,
not the workspace members (`apps/K9`, `apps/dicks_laboratory`, …) whose
dependencies (`typer`, `python-dotenv`, `websockets`, …) the collector needs.
Corrected with **`uv sync --frozen --all-packages`** (66 packages); preflight
then passed. The deploy docs (`SATURDAY_MAINTENANCE.md`, AZ2A/AZ2C/AZ3 bootstrap
steps) now specify `--all-packages`. No collector source changed; the tracked
`ExecStart` (`uv run --frozen …`) is unchanged and correct once the venv is
synced.

## AZ4.F — AZ4 runtime override
`/run/systemd/system/dicks-lab-es-session.service.d/az4-override.conf`
(RUNTIME ONLY — `/run`, not `/etc`, cleared by reboot / `systemctl revert`):
```
[Service]
ExecStart=
ExecStart=/home/temckee8/.local/bin/uv run --frozen python scripts/dicks_lab_collect_es.py --duration 7200 --data-dir /srv/dicks_laboratory/data/az4_live_verification
RuntimeMaxSec=7800
```
Every other production property **inherited unchanged**: `User=temckee8`,
`WorkingDirectory`, `RequiresMountsFor`, `ConditionPathIsMountPoint`,
`ExecStartPre` mount/`.env` checks, `KillSignal=SIGINT`, `TimeoutStopSec=180`,
`Restart=no`, `MemoryAccounting=yes`. `systemd-analyze verify` clean;
effective `RuntimeMaxUSec=2h 10min`, `KillSignal=2`, `Restart=no`. Tracked
`/etc` unit byte-unchanged (sha256 as AZ4.D). *(An initial override had a
non-parseable empty `RuntimeMaxSec=` reset line — scalar directives can't be
reset that way; corrected to a single `RuntimeMaxSec=7800`.)*

## AZ4.G — Live collector start
`sudo systemctl start dicks-lab-es-session.service` — first authorized live
execution. `ActiveState=active`, `SubState=running`,
`ExecMainStartTimestamp = 2026-09-09 22:38:49 UTC` (17:38:49 CDT). Process
tree: `uv run` supervisor (pid 2299) → **one** `.venv/bin/python3
scripts/dicks_lab_collect_es.py --duration 7200 --data-dir …/az4_live_verification`
(pid 2303), cwd `/home/temckee8/Documents/REPOs/copper`, `User=temckee8`.
Exactly one collector process.

## AZ4.H — Quote-token evidence
From the collector's own safe observability line:
```
fresh_collector: quote_token_requested=true fresh_dxlink_collector=true oauth_refreshed=false
quote_token_issued_at=2026-09-09T13:55:01.439Z  quote_token_expires_at=2026-09-10T13:55:01.439Z
quote_token_remaining_seconds=54971
```
- **Requested by the live collector at its own startup** — the preflight had
  logged `quote_token_requested=false` and does not touch the token endpoint,
  so it was **not inherited from preflight**.
- `remaining ≈ 54,971 s (~15.3 h)`; required horizon = `7200 + 900 = 8100 s`
  → **~46,871 s margin**. The token API returned the Tastytrade account's
  current standing 24 h token (issued earlier the same day) — the documented
  0W-2C account-level lifetime behaviour; for a 2 h run the guard passes with
  vast headroom. Token value never printed.

## AZ4.I — DXLink connection
Quality events: **CAPTURE_STARTED** `2026-09-09T22:38:50.523Z` →
**SOURCE_CONNECTED** `2026-09-09T22:38:51.667Z` (~1.1 s to connect) → first
retained trade `dataset_sequence 1`, `event_timestamp
2026-09-09T22:38:58.292Z`, `received_at 2026-09-09T22:38:58.307Z`, `source_order
1`.

## AZ4.J — Dataset identity
| | |
|---|---|
| `dataset_id` | `f6553efa-30e3-4410-b49d-b659a36b9048` |
| label | `long-horizon-es-2026-09-10` |
| instrument | `FUTURE:CME:ES:2026-09` |
| requested symbol / resolved streamer | `/ESU6` → `/ESU26:XCME` |
| `trading_date` | `2026-09-10` |
| `collector_git_commit` | `f8ef3401bfbbe27e9b3a76d66a8ed05953d977ad` |
| `normalizer_version` | `phase-0v-serious-collection-v1` |
| database | `/srv/dicks_laboratory/data/az4_live_verification/es_20260910_f6553efa.sqlite3` |
| `capture_started_at` / `capture_ended_at` | `2026-09-09T22:38:50.523Z` / `2026-09-10T00:38:50.858Z` |

## AZ4.K — Capture window
`17:38:50 CT → 19:38:50 CT` = **2 h 0 m 0.3 s**. CME Globex reopened
17:00 CT — the run **began ~38 min after the session anchor**, so this is a
**PARTIAL-WINDOW** capture of trading date 2026-09-10, **not full-session
coverage** (17:00 CT→16:00 CT). Not evaluated for completeness.

## AZ4.L — Event counts
accepted **10,914** · deferred **0** · rejected **0** · known_gap **0** ·
suspected_gap **0** · reconnect **0**. `event_classification`: 10,914 × `NEW`.
`aggressor_side`: BUY 5,675 / SELL 5,239. Hourly (UTC): 22 → 541, 23 → 3,284,
00 → 7,089.

## AZ4.M — Lifecycle / quality events
| event | timestamp |
|---|---|
| CAPTURE_STARTED | `2026-09-09T22:38:50.523562Z` |
| SOURCE_CONNECTED | `2026-09-09T22:38:51.666853Z` |
| CAPTURE_STOPPED | `2026-09-10T00:38:50.858831Z` (detail: `writer_flushes=2592; writer_batch_max=73; writer_queue_depth_max=47; writer_max_persist_lag_s=0.322; writer_persisted_events=10914; writer_overloaded=false`) |

**No SOURCE_DISCONNECTED, no SOURCE_RECONNECTED, no KNOWN_GAP, no
SUSPECTED_GAP.** `lifecycle_state = FINALIZED`.

## AZ4.N — Source-order accounting
- `trade_observations` 10,914 = `observation_source_provenance` 10,914 =
  `writer_persisted_events` 10,914.
- `source_order` min 1, max 10,914, **distinct 10,914**;
  `(10914 − 1 + 1) − 10914 − 0 rejections = 0` **unexplained ordinals**.
- **duplicate accepted `source_order` = 0.**
- `dataset_sequence` 1..10,914, distinct 10,914 → **`seq_holes = 0`
  (contiguous)**.
- first accepted: seq 1 / ev `22:38:58.292Z` / so 1 / ra `22:38:58.307Z`.
- last accepted: seq 10,914 / ev `00:38:48.811Z` / so 10,914 / ra
  `00:38:48.826Z`.

## AZ4.O — SQLite integrity
Read-only on the FINALIZED DB: `PRAGMA quick_check` = **ok**,
`PRAGMA integrity_check` = **ok**, `journal_mode` = **delete**. No
`-wal`/`-shm`/`-journal` sidecars. Final size **5,427,200 bytes**.

## AZ4.P — Manifest / checksum
Manifest present (438 B, `state FINALIZED`, `collector_git_commit f8ef340`,
`checksum_scope "file integrity only; not a market-data completeness claim"`).
**Independent verification:**
`sha256(es_20260910_f6553efa.sqlite3)` =
`b5cf4fa530f957660878f7007402e47be781ced8a736f40eff4f52d4c61fa6b4`
= manifest `sha256` = the collector's closing-summary checksum → **PASS**.
`dataset_closing_summaries` (accepted 10914 / deferred 0 / rejected 0 /
known_gap 0 / suspected_gap 0 / first_so 1 / last_so 10914) **exactly matches**
the direct SQL `COUNT(*)/MIN/MAX` — the 0W-2D `COUNT(*)` path; no
full-dataset materialisation into Python.

## AZ4.Q — Writer metrics
`writer_persisted_events` 10,914 · `writer_flush_count` 2,592 ·
`writer_batch_size_max` 73 · **`writer_queue_depth_max` 47** (≪ the ~50,000
robby watermark) · **`writer_max_persist_lag_seconds` 0.322** (sub-second) ·
**`writer_overloaded` false**.

## AZ4.R — Process / memory metrics (5-min sampler, full run)
- service `MemoryCurrent` 41 → 49 MB, `MemoryPeak` **51.1 MB**; collector
  python RSS 50 → 53 MB — flat, **no leak** (rise tracks DB growth).
- `TasksCurrent` 6 throughout.
- total CPU **14.479 s over 2 h 1.5 s wall** ≈ **0.19 % average CPU**;
  guest loadavg 0.09–0.45.
- host memory: ~250–760 MB used of 7.88 GB; data-disk usage 5.2 MB.

## AZ4.S — Azure CPU-credit / disk / network metrics (Azure Monitor, full window)
| metric | min | mean | max |
|---|---|---|---|
| Percentage CPU | 1.15 % | **1.55 %** | 3.99 % |
| CPU Credits Remaining | 63 | 95.6 | **129 (rising ~+66 over the run)** |
| CPU Credits Consumed / 15 min | 0.022 | 0.028 | 0.051 |
| Data Disk IOPS Consumed % | 0 | 0.73 % | 2.13 % |
| OS Disk IOPS Consumed % | 0 | ~0 | 0.13 % |
| Available Memory | 7.12 GB | 7.56 GB | 7.63 GB |
| Network In / Out (per 15 min) | — | ~1 MB / ~0.18 MB | 8.4 MB / 0.31 MB |

**`Standard_B2ms` shows no meaningful capacity concern** — CPU ~1.5 % average,
B-series credits **accruing not draining**, disk ~1 %, ~90 % memory free.
Heavily over-provisioned for the collector workload. No resize.

## AZ4.T — Gap / reconnect result
```
KNOWN_GAP = 0    SUSPECTED_GAP = 0    DISCONNECT = 0    RECONNECT = 0
```
Clean baseline. `HOST/RUNTIME FUNCTION: PASS` **and** `AZ4 DATA COMPLETENESS
(partial window): PASS` (zero gaps within the captured interval).

## AZ4.U — Persistent-disk verification
`findmnt -T <db>` → `/dev/sda /srv/dicks_laboratory ext4 UUID
890b7de2-a7e1-4650-a7c9-464124698b29` = **`dragon-data1`**. Nothing written to
the Copper repo (`apps/dicks_laboratory/data` clean), OS disk, `/mnt`, or
`/tmp` (beyond ordinary process temp). Production `…/data/sessions/` remained
**empty** — no production run occurred.

## AZ4.V — VWAP / volume-profile smoke (read-only, `--anchor session-open`)
| tool | result | runtime |
|---|---|---|
| `dicks_lab_analyze_vwap.py` | 10,914 trades, 0 corrections/cancels, **VWAP 7651.80** | <1 s |
| `dicks_lab_analyze_volume_profile.py` | **POC 7653.50**, **VAL 7651.00**, **VAH 7656.00**, value-area 71.3 % (target 70 %), 21 levels; "NEW-only differs from effective tape: no" | 2 s |
| `dicks_lab_analyze_developing_profile.py` | terminal cumulative: 10,914 trades / 12,317 vol / VWAP 7651.80 / POC 7653.50 / VAL 7651.00 / VAH 7656.00 | 1 s |

Terminal static vs developing profile **agree** (same POC/VAL/VAH/VWAP). All
correctly labelled "developing … not a completed full-session profile". Stored
data is usable.

## AZ4.W — Service exit / finalization
`--duration 7200` expired normally (no manual SIGINT). Collector exited →
writer drained → dataset FINALIZED → CAPTURE_STOPPED written →
manifest/checksum produced → `Deactivated successfully` →
`Result=success`, `ExecMainStatus=0`. Journal:
`Consumed 14.479s CPU time over 2h 1.495s wall clock time, 51.1M memory peak`.

## AZ4.X — Runtime-override removal
`sudo systemctl revert dicks-lab-es-session.service` → removed
`/run/systemd/system/dicks-lab-es-session.service.d/az4-override.conf` + its
directory; `daemon-reload`. No drop-in remains in `/run` or `/etc`.

## AZ4.Y — Production service restoration
`systemctl cat` / `systemctl show` confirm the canonical config is back:
`ExecStart=… --duration 83700 --data-dir /srv/dicks_laboratory/data/sessions`,
`RuntimeMaxSec=84300` (`RuntimeMaxUSec=23h 25min`), `TimeoutStopSec=180`,
`KillSignal=SIGINT`, `Restart=no`. Tracked units byte-identical to Git
(sha256 as AZ4.D). `/tmp/az4_sampler.*` removed; the AZ4 dataset dir is kept
as persistent verification evidence.

## AZ4.Z — Collector timer final state
```
dicks-lab-es-session.timer   : enabled=disabled   active=inactive
dicks-lab-es-session.service : static (timer-only) · inactive · Result=success
```
Not in `systemctl list-timers`. **No automatic collector launch is armed.**
(Not enabled despite the AZ4 pass — daily arming is a separate authorised
step.)

## AZ4.AA — Weasel / robyn state
```
weasel : READY / NOT TESTED   (pubkey authorized on dragon; check must run from weasel)
robyn  : DEFERRED             (not a tailnet member; no key)
```
**Pre-Attempt-4 Human prerequisite:** resolve the desired redundant
administration paths (weasel verification + robyn tailnet/key/authorize)
before formal unattended 0W-2 Attempt 4.

## AZ4.AB — Old OS disk
`dragon_disk1_bb48fd67c68342b4b4596a45879297f9` — **retained, `Unattached`,
unchanged.** Retention policy updated: **retain through formal 0W-2 Attempt 4**
(not deleted immediately after AZ4).

## AZ4.AC — Azure weekly schedule
`dicks-futures-dragon-start` (Sun 15:30 CT) and `dicks-futures-dragon-stop`
(Fri 16:45 CT) **remain armed / enabled** — not disabled. A manually
deallocated `dragon` simply stays off until the next scheduled Sunday start or
an explicit manual start.

## AZ4.AD — AZ4 decision

```
0W-AZ4: PASS / CLOSED — DRAGON LIVE COLLECTOR VERIFIED

FULL TRADING-DATE PROOF : NOT YET PERFORMED
DAILY COLLECTOR TIMER   : DISABLED
OLD 24.04 OS DISK       : RETAINED
NEXT                    : PREPARE 0W-2 ATTEMPT 4 ON DRAGON
```

## AZ5 — 0W-2 ATTEMPT 4 (formal full-session proof) — summary

Full evidentiary write-up lives in
`docs/dicks_laboratory/FULL_SESSION_MULTIDAY_SOAK_REPORT.md` §LB (this is the
canonical Attempt-4 record; this section is a pointer + Azure-specific
detail).

Pinned commit `f27a04373d4fb3aea5ce732455cf24cfb008bd5e`, `uv sync --frozen
--all-packages`. The real, unmodified production timer
(`dicks-lab-es-session.timer`) launched the real, unmodified production
service automatically at 16:55:00 CT Thu 2026-09-10 — no manual rescue.

**Result: `0W-2 ATTEMPT 4 (AZURE): FAIL — PARTIAL-COVERAGE / NON-CLEAN
EXIT`.** The collector ran as one continuous, unattended process for 21h41m,
correctly capturing the trading date's open at 17:00:01 CT with 999,996
contiguous, checksum-verified trades and zero gaps/reconnects — but hit the
CLI's un-overridden default `--max-events=1,000,000` cap at 14:36:11 CT Fri
(~84 min before the true 16:00 CT close), cleanly self-finalized that
dataset, then — because `--duration 83700` had not yet elapsed — the same
process attempted a further dataset-open, hit its own "already FINALIZED"
guard, and exited `status=2` (`Result=exit-code`), not `Result=success`.

**Deployment/config defect identified (not applied in this phase, pending
Human authorization):** the production unit's `ExecStart` must pass an
`--max-events` well above one session's realistic event volume (observed
≥1,000,000 for ES on this trading date), and the collector should exit
cleanly (0/success) rather than attempt a second dataset-open when it
finishes early relative to `--duration`.

Post-run host state (all reconfirmed): timer `disabled`/`inactive`; tracked
unit files byte-identical to repo (`.service` sha256 `b48f39db…`, `.timer`
sha256 `eebe8a9c…`); old 24.04 disk
`dragon_disk1_bb48fd67c68342b4b4596a45879297f9` retained/unattached; weekly
Automation schedules `dicks-futures-dragon-start`/`-stop` enabled. Evidence
(`es_20260911_3716af9f.sqlite3`, its manifest, `att4_samples.csv`, full
`systemctl`/journal capture) copied off `dragon` to `robby:~/secure/att4/`
with independent sha256 verification before the scheduled 16:45 CT
`Stop-Dragon`, which was left to fire naturally (not manually deallocated) to
also prove the production Friday shutdown path.

```
0W-2 ATTEMPT 4 (AZURE): FAIL — PARTIAL-COVERAGE / NON-CLEAN EXIT
FULL TRADING-DATE COVERAGE: FAIL (~14:36–16:00 CT missing)
PRODUCTION TIMER LAUNCH: PASS
DATA INTEGRITY (captured window): PASS
0W-2: OPEN.  0W-4: BLOCKED pending corrected Attempt 5.
```

## AZ6 — 0W-2E — Production Event-Cap & Terminal-Stop Correction

Full write-up: `FULL_SESSION_MULTIDAY_SOAK_REPORT.md` §LC (canonical). This
is a code/config/test-only corrective phase, no live market run. Root cause:
the production unit never overrode the collector's default
`--max-events=1,000,000`, and the outer control-flow loop treated a
max-events fuse trip identically to a genuine session-close, causing it to
attempt a second dataset-open on the same still-open trading date.

Fixed in `long_running_capture.py` (explicit fuse detection, `stop=True`,
durable `stopped_reason` + `KNOWN_GAP` for the lost tail, no second dataset)
and `dicks_lab_collect_es.py` (exit code 3 for a fuse-triggered stop).
Production unit now pins `--max-events 5000000` explicitly. New
`test_production_unit_config.py` deploy-validation check. Full repository
suite: 1,188 passed. Deployed to `dragon`, verified, timer left
disabled/inactive, host deallocated again afterward.

```
0W-2E: PASS / READY FOR PO REVIEW
0W-2: OPEN.  ATTEMPT 5: NOT STARTED.
DAILY COLLECTOR TIMER: DISABLED.  OLD 24.04 OS DISK: RETAINED.
```
