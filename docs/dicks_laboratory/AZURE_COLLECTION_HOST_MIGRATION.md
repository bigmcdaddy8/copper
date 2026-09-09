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
