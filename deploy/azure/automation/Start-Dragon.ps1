<#
  Start-Dragon.ps1  --  authoritative power-ON for the Dick's Laboratory
  futures collection host (Azure VM 'dragon').

  Owner        : Automation account 'automation-dragon' (system-assigned MI,
                 granted 'Virtual Machine Contributor' scoped to the dragon VM).
  Auth         : Automation account managed identity (no secret, no webhook).
  Idempotent   : if already running -> logs a no-op success and exits 0.
  Scheduled by : 'dicks-futures-dragon-start' (weekly Sunday 15:30 America/Chicago).
  Runtime      : PowerShell 7.2 (Az module).

  This controls HOST power only. It does not touch the collector.
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
Write-Output "Start-Dragon: initial PowerState = $before"

if ($before -eq 'PowerState/running') {
    Write-Output "Start-Dragon: already running -- no-op success."
    return
}

Start-AzVM -ResourceGroupName $rg -Name $vm | Out-Null

$after = Get-PowerState
Write-Output "Start-Dragon: final PowerState = $after"
if ($after -ne 'PowerState/running') {
    throw "Start-Dragon: VM did not reach PowerState/running (observed '$after')."
}
Write-Output "Start-Dragon: OK ($before -> $after)"
