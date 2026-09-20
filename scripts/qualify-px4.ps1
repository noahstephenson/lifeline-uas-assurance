param(
    [ValidateSet("Smoke", "T-01", "T-05")]
    [string]$Scenario = "T-01",
    [ValidateRange(1024,65535)]
    [int]$ApiPort = 8895,
    [ValidateRange(1024,65535)]
    [int]$WebPort = 8896
)

$ErrorActionPreference = "Stop"
$Distro = "Ubuntu-24.04"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EvidenceRoot = Join-Path $ProjectRoot "evidence\runs"
$Started = @{}
$Stamp = Get-Date -Format "yyyyMMddTHHmmssZ"
$Suffix = [guid]::NewGuid().ToString("N").Substring(0, 4).ToUpperInvariant()
$RunId = if ($Scenario -eq "Smoke") { "LFL-SMOKE-PX4-$Stamp-$Suffix" } else { "LFL-$($Scenario.Replace('-', ''))-PX4-$Stamp-$Suffix" }
$LogRoot = Join-Path $ProjectRoot ".qualification-logs\$RunId"
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

function Assert-PortAvailable([int]$Port) {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        throw "Loopback port $Port is already in use."
    }
}

function Stop-RecordedProcesses {
    foreach ($Process in $Started.Values) {
        if ($Process -and -not $Process.HasExited) { Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue }
    }
}

$Distributions = @(& wsl.exe --list --quiet) -replace "`0", ""
if ($Distributions -notcontains $Distro) { throw "$Distro is not installed. Run scripts/setup-px4-wsl.ps1." }
if (-not (Test-Path (Join-Path $ProjectRoot "openmct\node_modules\vite\bin\vite.js"))) {
    throw "Open MCT dependencies are missing. Run npm ci in openmct with Node 20."
}
Assert-PortAvailable $ApiPort
Assert-PortAvailable $WebPort

$WslProject = ((& wsl.exe -d $Distro -- wslpath -a $ProjectRoot) -join "").Trim()
$WslLogRoot = ((& wsl.exe -d $Distro -- wslpath -a $LogRoot) -join "").Trim()
$Px4Out = Join-Path $LogRoot "px4.log"
$Px4Err = Join-Path $LogRoot "px4.err.log"
$ApiOut = Join-Path $LogRoot "api.log"
$ApiErr = Join-Path $LogRoot "api.err.log"
$WebOut = Join-Path $LogRoot "openmct.log"
$WebErr = Join-Path $LogRoot "openmct.err.log"
$Token = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).TrimEnd('=').Replace('+','-').Replace('/','_')
$PriorApiBase = $env:VITE_LIFELINE_API_BASE

try {
    $Started.px4 = Start-Process -FilePath "wsl.exe" -ArgumentList @(
        "-d", $Distro, "--", "bash", "-lc", "cd ~/PX4-Autopilot && make px4_sitl gz_x500"
    ) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $Px4Out -RedirectStandardError $Px4Err -PassThru

    if ($Scenario -eq "Smoke") {
        Start-Sleep -Seconds 8
        $SmokeCommand = "export LIFELINE_UBUNTU_RELEASE=24.04 LIFELINE_PX4_TAG=v1.17.0 LIFELINE_PX4_COMMIT=d6f12ad; ~/.venvs/lifeline/bin/lifeline px4-smoke --config '$WslProject/config/sitl-qualification.yaml' --run-id '$RunId'"
        & wsl.exe -d $Distro -- bash -lc $SmokeCommand
        if ($LASTEXITCODE -ne 0) { throw "PX4 smoke qualification failed. Evidence run: $RunId" }
    } else {

    $LiveCommand = "export LIFELINE_START_TOKEN='$Token'; ~/.venvs/lifeline/bin/lifeline live --scenario '$Scenario' --config '$WslProject/config/sitl-qualification.yaml' --run-id '$RunId' --host 127.0.0.1 --port '$ApiPort'"
    $Started.api = Start-Process -FilePath "wsl.exe" -ArgumentList @(
        "-d", $Distro, "--", "bash", "-lc", $LiveCommand
    ) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $ApiOut -RedirectStandardError $ApiErr -PassThru

    $Node = (Get-Command node.exe -ErrorAction Stop).Source
    $Vite = Join-Path $ProjectRoot "openmct\node_modules\vite\bin\vite.js"
    $env:VITE_LIFELINE_API_BASE = "http://127.0.0.1:$ApiPort"
    $Started.web = Start-Process -FilePath $Node -ArgumentList @($Vite, "--host", "127.0.0.1", "--port", "$WebPort") `
        -WorkingDirectory (Join-Path $ProjectRoot "openmct") -WindowStyle Hidden `
        -RedirectStandardOutput $WebOut -RedirectStandardError $WebErr -PassThru

    $Ready = $false
    foreach ($Attempt in 1..180) {
        try {
            $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/health" -TimeoutSec 1
            $Page = Invoke-WebRequest -Uri "http://127.0.0.1:$WebPort/?run=$RunId" -TimeoutSec 1
            if ($Health.status -eq "READY" -and $Page.StatusCode -eq 200) { $Ready = $true; break }
        } catch {}
        Start-Sleep -Seconds 1
    }
    if (-not $Ready) { throw "PX4/API/Open MCT did not reach the held READY state." }

    Start-Process "http://127.0.0.1:$WebPort/?run=$RunId#/browse/lifeline:mission-assurance"
    $DashboardReady = $false
    foreach ($Attempt in 1..60) {
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/health" -TimeoutSec 1
        if ($Health.dashboard_connected) { $DashboardReady = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $DashboardReady) { throw "The dashboard did not establish its read-only WebSocket before mission release." }

    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$ApiPort/api/v1/control/start" `
        -Headers @{ "X-Lifeline-Start-Token" = $Token } -TimeoutSec 5 | Out-Null

    $Terminal = $null
    foreach ($Attempt in 1..240) {
        $Terminal = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/health" -TimeoutSec 2
        if ($Terminal.status -in @("COMPLETE", "ERROR")) { break }
        Start-Sleep -Seconds 1
    }
    if ($Terminal.status -ne "COMPLETE") { throw "Live qualification ended as $($Terminal.status): $($Terminal.error)" }
    }
} finally {
    $env:VITE_LIFELINE_API_BASE = $PriorApiBase
    Stop-RecordedProcesses
}

$WslPx4Log = "$WslLogRoot/px4.log"
$WslApiLog = "$WslLogRoot/api.log"
& wsl.exe -d $Distro -- bash -lc "~/.venvs/lifeline/bin/lifeline evidence --run '$RunId' --attach-name px4_log --file '$WslPx4Log'"
if ($LASTEXITCODE -ne 0) { throw "Failed to attach PX4 log to evidence." }
if ($Scenario -eq "Smoke") {
    Write-Host "PX4 smoke qualification passed. Evidence run: $RunId"
    return
}
& wsl.exe -d $Distro -- bash -lc "~/.venvs/lifeline/bin/lifeline evidence --run '$RunId' --attach-name api_log --file '$WslApiLog'"
if ($LASTEXITCODE -ne 0) { throw "Failed to attach API log to evidence." }
Write-Host "PX4 qualification completed. Scenario: $Scenario; evidence run: $RunId"
