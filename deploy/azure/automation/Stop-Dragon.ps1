<#
  Stop-Dragon.ps1  --  authoritative power-OFF (deallocate) for the Dick's
  Laboratory futures collection host (Azure VM 'dragon').

  Owner        : Automation account 'automation-dragon' (system-assigned MI,
                 'Virtual Machine Contributor' scoped to the dragon VM).
  Auth         : Automation account managed identity (no secret, no webhook).
  Idempotent   : if already deallocated -> logs a no-op success and exits 0.
  Scheduled by : 'dicks-futures-dragon-stop' (weekly Friday 16:45 America/Chicago),
                 ~35 min after the daily collector's expected clean exit (~16:10 CT).
  Runtime      : PowerShell 7.2 (Az module).

  HOST scheduling only. The daily collector must already have finalized its
  dataset and exited before this runs; this does not inspect or kill it.
#>
$ErrorActionPreference = 'Stop'
$rg = 'rg-dev-environment'
$vm = 'dragon'

function Get-PowerState {
    (Get-AzVM -ResourceGroupName $rg -Name $vm -Status).Statuses |
        Where-Object { $_.Code -like 'PowerState/*' } |
        Select-Object -First 1 -ExpandProperty Code
}

Connect-AzAccount -Identity | Out-Null

$before = Get-PowerState
Write-Output "Stop-Dragon: initial PowerState = $before"

if ($before -eq 'PowerState/deallocated') {
    Write-Output "Stop-Dragon: already deallocated -- no-op success."
    return
}

Stop-AzVM -ResourceGroupName $rg -Name $vm -Force | Out-Null

$after = Get-PowerState
Write-Output "Stop-Dragon: final PowerState = $after"
if ($after -ne 'PowerState/deallocated') {
    throw "Stop-Dragon: VM did not reach PowerState/deallocated (observed '$after')."
}
Write-Output "Stop-Dragon: OK ($before -> $after)"
