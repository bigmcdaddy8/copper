# Dick's Laboratory — Project Suspension (2026-11-10)

**Status: SUSPENDED — NO COLLECTION — NO AUTOMATIC VM START — DRAGON DEALLOCATED — DATA PRESERVED**

## Decision

The Human placed Dick's Laboratory **ON HOLD** effective 2026-11-10 to prioritize a
separate NinjaScript automated-trading effort. This is a **suspension, not a
cancellation**. No deletion of data, infrastructure or repository history was
authorized. Tutor development, trading analysis and the analytical seal are unchanged
(no analysis performed; no market-event queries run). Historical plans, including
`AI_TUTOR_UX_POC_PLAN.md`, are intentionally left untouched.

## Policies while suspended

- **No-collection:** no market data is collected; no collector runs.
- **Retention:** all datasets, manifests, summaries, logs, checksums, repo and docs are retained unaltered.
- **Nothing resumes automatically.** Reactivation needs explicit Human authorization (see below).
- The Nov 2–6 campaign week was **not reviewed** by the Product Owner; its status is not inferred here.

## Observed Azure state (2026-11-10, management plane only)

Subscription "Pay-as-you-go" (`e391572c-cb6c-4a94-9ce3-79bc3835112a`), resource group `rg-dev-environment`, eastus.

| Item | Value |
|---|---|
| VM | `dragon`, `Standard_B2ms` — `/subscriptions/e391572c-cb6c-4a94-9ce3-79bc3835112a/resourceGroups/rg-dev-environment/providers/Microsoft.Compute/virtualMachines/dragon` |
| Power state | **VM deallocated** at first inspection and at final check (never started in this task) |
| OS disk | `dragon-osdisk-gen1`, StandardSSD_LRS; size not returned by API while Reserved (earlier docs: 32 GiB) |
| Data disk | `dragon-data1`, StandardSSD_LRS, 500 IOPS; size not returned by API while Reserved (**size unverified**) |
| Network | `dragon-nic`, `dragon-vnet`, `dragon-nsg`; **no public IP** |
| Data path (guest) | `/srv/dicks_laboratory/data/sessions` — **not inspected** |

## Schedules disabled

Automation account `automation-dragon` (runbooks `Start-Dragon`, `Stop-Dragon` retained and linked):

| Schedule | Before | After |
|---|---|---|
| es-corpus-2026-10-start-1018 / -1025 / -1101 | Enabled (one-time, expired) | **Disabled** (changed today) |
| es-corpus-2026-10-stop-1016 / -1023 / -1030 / -1106 | Enabled (one-time, expired) | **Disabled** (changed today) |
| dicks-futures-dragon-start (weekly, next 2026-11-15 15:30 CT) | Disabled | Disabled (unchanged) |
| dicks-futures-dragon-stop (weekly) | Disabled | Disabled (unchanged) |
| dicks-0w5c-dragon-start / -stop (one-time) | Disabled | Disabled (unchanged) |

Automation account `automation-k9` (runbook `Start-Dragon`):
`dragon-start-weekday` and `dragon-start-saturday` (weekly) were already **Disabled**; unchanged.

Other checks: no webhooks on either account; no non-completed automation jobs; no Logic Apps /
Function Apps; no DevTest auto-shutdown for dragon (the only one, `shutdown-computevm-weasel_den`,
belongs to the unrelated `weasel_den` VM, untouched). Schedule/job links were left in place;
only `isEnabled` was changed.

## Guest-level state — DEFERRED

Dragon was deallocated, so it was **not powered on**. Guest systemd units (preflight/launch gate
timers, collector service, campaign-end disarm timer, legacy timers) were **not inspected or disabled**
and are presumed still enabled. They cannot fire while the VM is off. Collector inactivity is established
by VM power state only, not live guest inspection. Dataset counts, manifests and checksums were **not
re-verified**; the last verification is the 2026-10-25 audit. A future authorized maintenance session
should disable the guest units on first boot, before any market hours.

## Residual recurring costs (configuration verified; amounts are NOT measured)

| Resource | Class |
|---|---|
| VM compute (`dragon`) | STOPPED / NO ACTIVE COMPUTE |
| `dragon-osdisk-gen1`, `dragon-data1` (StandardSSD_LRS) | RETAINED / BILLABLE (billed while deallocated) |
| `dragon-vnet`, `dragon-nic`, `dragon-nsg` | RETAINED (no meaningful charge expected) |
| Public IP | None for dragon |
| Automation accounts `automation-dragon`, `automation-k9` | RETAINED; schedules DISABLED; basic-tier charges only for job minutes (none running) |
| Snapshots / Backup vaults / Log Analytics | None found |
| `weasel_den` VM stack (separate, deallocated, has public IP and OS disk) | REQUIRES REVIEW — out of scope, not touched |

Check Cost Management for actual figures.

## Future archival options (none executed)

| Option | Recurring cost | Restore complexity | Risk |
|---|---|---|---|
| Keep VM + disks deallocated (current) | Disk cost only | Lowest; `az vm start` | Low; schedules disabled |
| Keep disks, delete VM after exporting its definition | Same disk cost | Medium; recreate from the Bicep | Misconfiguration on rebuild |
| Verified archival copy to cool/archive Blob | Lower than SSD | Medium; checksum plan needed | Metadata/permission fidelity if not tarred |
| Snapshot of data disk | Adds a cost | Low | Not a backup against region loss |

Any archive needs a separately defined verification, checksum and recovery plan. No irreversible
option is selected.

## Resumption procedure (manual, explicitly authorized)

1. Human authorization.
2. Review preserved data and infrastructure; review Azure costs and credentials.
3. Review contract-roll status — the `/ESZ6` pin and Oct–Nov 2026 window are **not** assumed valid.
4. Review collector code, dependencies and the pinned commit (`0765418`).
5. Start dragon manually outside market hours; disable or inspect the guest timers first.
6. Verify data integrity (manifests/checksums) and systemd configuration.
7. Choose a new collection period explicitly.
8. Run a controlled collector startup test.
9. Re-enable only the required Automation schedules; do not restore the old es-corpus-2026-10 schedules.
