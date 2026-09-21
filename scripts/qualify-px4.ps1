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
$PortableNode = Join-Path $ProjectRoot ".tools\node-v20.20.2-win-x64\node.exe"
$EvidenceRoot = Join-Path $ProjectRoot "evidence\runs"
$Started = @{}
$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
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

function ConvertTo-WslMountPath([string]$WindowsPath) {
    $FullPath = [System.IO.Path]::GetFullPath($WindowsPath)
    if ($FullPath -notmatch '^(?<Drive>[A-Za-z]):\\(?<Rest>.*)$') {
        throw "Expected a drive-qualified Windows path, found '$FullPath'."
    }
    $DriveName = $Matches.Drive.ToLowerInvariant()
    $RelativePath = $Matches.Rest.Replace('\', '/')
    return "/mnt/$DriveName/$RelativePath"
}

function Merge-ProcessLogs([string]$StandardOutput, [string]$StandardError, [string]$Destination) {
    $Inputs = @($StandardOutput, $StandardError) | Where-Object { Test-Path -LiteralPath $_ }
    if ($Inputs.Count -eq 0) { return }
    $Content = foreach ($InputPath in $Inputs) {
        "===== $([System.IO.Path]::GetFileName($InputPath)) ====="
        Get-Content -LiteralPath $InputPath -ErrorAction SilentlyContinue
    }
    Set-Content -LiteralPath $Destination -Value $Content -Encoding utf8
}

function Attach-EvidenceLog([string]$LogicalName, [string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $WslPath = ConvertTo-WslMountPath $Path
    & wsl.exe -d $Distro -- $WslLifeline evidence --run $RunId --attach-name $LogicalName --file $WslPath
    if ($LASTEXITCODE -ne 0) { throw "Failed to attach $LogicalName to evidence." }
}

$Distributions = @(& wsl.exe --list --quiet) -replace "`0", ""
if ($Distributions -notcontains $Distro) { throw "$Distro is not installed. Run scripts/setup-px4-wsl.ps1." }
$WslHome = ((& wsl.exe -d $Distro -- sh -c 'printf %s "$HOME"') -join "").Trim()
if (-not $WslHome.StartsWith("/home/") -or $WslHome -match '\s') { throw "Unexpected WSL home path '$WslHome'." }
$WslLifeline = "$WslHome/.venvs/lifeline/bin/lifeline"
& wsl.exe -d $Distro -- test -f "$WslHome/.lifeline-px4-installer-complete"
if ($LASTEXITCODE -eq 0) { & wsl.exe -d $Distro -- test -x $WslLifeline }
if ($LASTEXITCODE -ne 0) { throw "The Ubuntu PX4 environment is incomplete. Run scripts/setup-px4-wsl.ps1 -Finalize." }
$Px4Commit = ((& wsl.exe -d $Distro -- git -C "$WslHome/PX4-Autopilot" rev-parse --short=7 HEAD) -join "").Trim()
if ($Px4Commit -ne "d6f12ad") { throw "PX4 commit mismatch: expected d6f12ad, found '$Px4Commit'." }
if ($Scenario -ne "Smoke") {
    if (-not (Test-Path (Join-Path $ProjectRoot "openmct\node_modules\vite\bin\vite.js"))) {
        throw "Open MCT dependencies are missing. Run npm ci in openmct with Node 20."
    }
    $Node = if (Test-Path -LiteralPath $PortableNode) { $PortableNode } else { (Get-Command node.exe -ErrorAction Stop).Source }
    $NodeVersion = (& $Node --version).Trim()
    if ($NodeVersion -notmatch '^v20\.') { throw "Open MCT qualification requires Node 20; found $NodeVersion." }
}
Assert-PortAvailable $ApiPort
Assert-PortAvailable $WebPort

$WslProject = ConvertTo-WslMountPath $ProjectRoot
$WslLogRoot = ConvertTo-WslMountPath $LogRoot
$Px4Out = Join-Path $LogRoot "px4.stdout.log"
$Px4Err = Join-Path $LogRoot "px4.stderr.log"
$Px4Log = Join-Path $LogRoot "px4.log"
$ApiOut = Join-Path $LogRoot "api.stdout.log"
$ApiErr = Join-Path $LogRoot "api.stderr.log"
$ApiLog = Join-Path $LogRoot "api.log"
$WebOut = Join-Path $LogRoot "openmct.log"
$WebErr = Join-Path $LogRoot "openmct.err.log"
$Token = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).TrimEnd('=').Replace('+','-').Replace('/','_')
$PriorApiBase = $env:VITE_LIFELINE_API_BASE
$Failure = $null

try {
    $Started.px4 = Start-Process -FilePath "wsl.exe" -ArgumentList @(
        "-d", $Distro, "--cd", "$WslHome/PX4-Autopilot", "--", "make", "px4_sitl_default", "gz_x500"
    ) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $Px4Out -RedirectStandardError $Px4Err -PassThru

    if ($Scenario -eq "Smoke") {
        Start-Sleep -Seconds 8
        if ($Started.px4.HasExited) {
            $LaunchError = "PX4/Gazebo exited before MAVSDK connection with code $($Started.px4.ExitCode)"
            & wsl.exe -d $Distro -- $WslLifeline px4-smoke --config "$WslProject/config/sitl-qualification.yaml" --run-id $RunId --setup-error $LaunchError
            throw $LaunchError
        }
        & wsl.exe -d $Distro -- env LIFELINE_UBUNTU_RELEASE=24.04 LIFELINE_PX4_TAG=v1.17.0 LIFELINE_PX4_COMMIT=d6f12ad $WslLifeline px4-smoke --config "$WslProject/config/sitl-qualification.yaml" --run-id $RunId
        if ($LASTEXITCODE -ne 0) { throw "PX4 smoke qualification failed. Evidence run: $RunId" }
    } else {

    $Started.api = Start-Process -FilePath "wsl.exe" -ArgumentList @(
        "-d", $Distro, "--", "env", "LIFELINE_START_TOKEN=$Token", $WslLifeline,
        "live", "--scenario", $Scenario, "--config", "$WslProject/config/sitl-qualification.yaml",
        "--run-id", $RunId, "--host", "127.0.0.1", "--port", "$ApiPort"
    ) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $ApiOut -RedirectStandardError $ApiErr -PassThru

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
} catch {
    $Failure = $_
} finally {
    $env:VITE_LIFELINE_API_BASE = $PriorApiBase
    Stop-RecordedProcesses
}

Merge-ProcessLogs $Px4Out $Px4Err $Px4Log
Merge-ProcessLogs $ApiOut $ApiErr $ApiLog
$ManifestPath = Join-Path (Join-Path $EvidenceRoot $RunId) "manifest.json"
$AttachmentFailure = $null
if (Test-Path -LiteralPath $ManifestPath) {
    try {
        Attach-EvidenceLog "px4_log" $Px4Log
        if ($Scenario -ne "Smoke") { Attach-EvidenceLog "api_log" $ApiLog }
    } catch {
        $AttachmentFailure = $_
    }
}

if ($Failure) {
    if ($AttachmentFailure) { Write-Warning $AttachmentFailure.Exception.Message }
    throw $Failure
}
if ($AttachmentFailure) { throw $AttachmentFailure }
if (-not (Test-Path -LiteralPath $ManifestPath)) { throw "Qualification produced no evidence manifest for $RunId." }
if ($Scenario -eq "Smoke") {
    Write-Host "PX4 smoke qualification passed. Evidence run: $RunId"
    return
}
Write-Host "PX4 qualification completed. Scenario: $Scenario; evidence run: $RunId"
