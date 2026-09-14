$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $ProjectRoot ".demo-pids.json"
if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host "No recorded Project Lifeline demo processes."
    exit 0
}

$Recorded = Get-Content -LiteralPath $PidFile -Raw | ConvertFrom-Json
foreach ($Name in @("api", "web", "px4")) {
    $Entry = $Recorded.processes.$Name
    if (-not $Entry) { continue }
    $Process = Get-Process -Id $Entry.id -ErrorAction SilentlyContinue
    if (-not $Process) { continue }
    $ActualTicks = $Process.StartTime.ToUniversalTime().Ticks
    if ($ActualTicks -ne $Entry.start_ticks) {
        Write-Warning "PID $($Entry.id) was reused; refusing to stop the unrelated process."
        continue
    }
    Stop-Process -Id $Entry.id -Force
}
Remove-Item -LiteralPath $PidFile
Write-Host "Stopped the recorded Project Lifeline demo processes."
