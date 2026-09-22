param(
    [ValidateSet("T-01","T-02","T-03","T-04","T-05","T-06","T-07","T-08","T-09","T-10","T-11","T-12","T-13","T-14","T-15")]
    [string]$Scenario,
    [ValidateSet("Synthetic","Replay","SITL")]
    [string]$Mode,
    [string]$RunId
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Lifeline = Join-Path $ProjectRoot ".venv\Scripts\lifeline.exe"

if (-not (Test-Path -LiteralPath $Lifeline)) {
    throw "Missing .venv. Run scripts/bootstrap.ps1 first."
}

if (-not $Scenario) {
    $Catalogue = @((& $Lifeline --json scenarios list | ConvertFrom-Json).data)
    Write-Host ""
    Write-Host "Project Lifeline - Medical Resupply Mission Lab"
    Write-Host "Select a controlled mission:"
    for ($Index = 0; $Index -lt $Catalogue.Count; $Index++) {
        $Item = $Catalogue[$Index]
        Write-Host ("[{0,2}] {1}  {2}  delivery:{3}" -f ($Index + 1), $Item.id, $Item.name, $Item.expected_delivery_outcome)
    }
    $Selection = [int](Read-Host "Mission number")
    if ($Selection -lt 1 -or $Selection -gt $Catalogue.Count) { throw "Invalid mission selection." }
    $Scenario = $Catalogue[$Selection - 1].id
}

if (-not $Mode) {
    $Mode = Read-Host "Mode (Synthetic, Replay, or SITL)"
    if ($Mode -notin @("Synthetic", "Replay", "SITL")) { throw "Invalid mode." }
}

if (Test-Path -LiteralPath (Join-Path $ProjectRoot ".demo-pids.json")) {
    throw "A Lifeline demo is already running. Use scripts/stop-demo.ps1 first."
}

if ($Mode -eq "SITL") {
    if ($Scenario -notin @("T-01", "T-05")) {
        throw "Supported SITL qualification scenarios are T-01 and T-05. Use Synthetic for the delivery-receipt scenarios."
    }
    & (Join-Path $PSScriptRoot "qualify-px4.ps1") -Scenario $Scenario
    exit $LASTEXITCODE
}

$DemoMode = if ($Mode -eq "Synthetic") { "Fake" } else { "Replay" }
$Arguments = @("-Scenario", $Scenario, "-Mode", $DemoMode)
if ($RunId) { $Arguments += @("-RunId", $RunId) }
& (Join-Path $PSScriptRoot "demo.ps1") @Arguments
exit $LASTEXITCODE
