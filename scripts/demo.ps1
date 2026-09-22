param(
    [ValidateSet("T-01","T-02","T-03","T-04","T-05","T-06","T-07","T-08","T-09","T-10","T-11","T-12","T-13","T-14","T-15")]
    [string]$Scenario = "T-05",
    [ValidateSet("Fake","Replay","Live")]
    [string]$Mode = "Fake",
    [switch]$AllowSitlActions,
    [string]$RunId,
    [ValidateRange(1024,65535)]
    [int]$ApiPort = 8765,
    [ValidateRange(1024,65535)]
    [int]$WebPort = 8766
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Lifeline = Join-Path $ProjectRoot ".venv\Scripts\lifeline.exe"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PidFile = Join-Path $ProjectRoot ".demo-pids.json"
$Started = @{}
$Completed = $false
$PriorApiBase = $env:VITE_LIFELINE_API_BASE

function Assert-PortAvailable([int]$Port) {
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($Listener) { throw "Loopback port $Port is already in use. Stop the conflicting service or change the Lifeline demo ports." }
}

function Stop-StartedProcesses {
    foreach ($Process in $Started.Values) {
        if ($Process -and -not $Process.HasExited) { Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue }
    }
}

if (-not (Test-Path -LiteralPath $Lifeline)) {
    throw "Missing .venv. Run scripts/bootstrap.ps1 first."
}
if (Test-Path -LiteralPath $PidFile) {
    throw "A recorded Lifeline demo already exists. Run scripts/stop-demo.ps1 before starting another."
}

Push-Location $ProjectRoot
try {
    if ($Mode -eq "Live") {
        throw "Live qualification is held and concurrent. Use scripts/qualify-px4.ps1 -Scenario $Scenario instead."
    }
    Assert-PortAvailable $ApiPort
    Assert-PortAvailable $WebPort
    $Doctor = (& $Lifeline --json doctor | ConvertFrom-Json).data
    & $Lifeline validate
    if ($LASTEXITCODE -ne 0) { throw "Project validation failed." }

    if ($Mode -eq "Live") {
        if (-not $AllowSitlActions) { throw "Live mode requires the explicit -AllowSitlActions switch." }
        if (-not $Doctor.modules.mavsdk) { throw "Live mode requires the optional MAVSDK dependency: pip install -e '.[px4]'" }
        if (-not $Doctor.px4.actions_enabled_by_default) {
            throw "Live mode also requires sitl.actions_enabled: true in config/baseline.yaml."
        }
        $Distributions = @(& wsl.exe -l -q) -replace "`0", ""
        if ($Distributions -notcontains "Ubuntu-24.04") { throw "Ubuntu-24.04 WSL2 is not installed." }
        $Stamp = Get-Date -Format "yyyyMMddTHHmmss"
        $Px4Out = Join-Path $ProjectRoot ".px4-$Stamp.out.log"
        $Px4Err = Join-Path $ProjectRoot ".px4-$Stamp.err.log"
        $Started.px4 = Start-Process -FilePath "wsl.exe" -ArgumentList @(
            "-d", "Ubuntu-24.04", "--", "bash", "-lc", "cd ~/PX4-Autopilot && make px4_sitl gz_x500"
        ) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $Px4Out -RedirectStandardError $Px4Err -PassThru
        Write-Host "PX4/Gazebo started. The controlled run will begin when MAVSDK reports readiness."
        $RunJson = & $Lifeline --json run --scenario $Scenario --source px4 --allow-sitl-actions
        if ($LASTEXITCODE -ne 0) { throw "PX4 scenario execution failed: $RunJson" }
        $RunId = ($RunJson | ConvertFrom-Json).data.run_id
    } elseif ($Mode -eq "Fake") {
        $RunArgs = @("--json", "run", "--scenario", $Scenario, "--source", "fake")
        if ($RunId) { $RunArgs += @("--run-id", $RunId) }
        $RunJson = & $Lifeline @RunArgs
        if ($LASTEXITCODE -ne 0) { throw "Scenario execution failed: $RunJson" }
        $RunId = ($RunJson | ConvertFrom-Json).data.run_id
    } else {
        if ($RunId) {
            $RunJson = & $Lifeline --json runs show $RunId
            if ($LASTEXITCODE -ne 0) { throw "Requested replay run does not exist: $RunId" }
            $Runs = @(($RunJson | ConvertFrom-Json).data.manifest)
        } else {
            $Runs = @((& $Lifeline --json runs list --scenario $Scenario --status PASS | ConvertFrom-Json).data)
        }
        if (-not $Runs) {
            Write-Host "No evidence exists; generating a deterministic $Scenario reference run for replay."
            $RunJson = & $Lifeline --json run --scenario $Scenario --source fake
            if ($LASTEXITCODE -ne 0) { throw "Reference scenario execution failed: $RunJson" }
            $RunId = ($RunJson | ConvertFrom-Json).data.run_id
        } else {
            $RunId = $Runs[0].run_id
        }
    }

    $RunDirectory = Join-Path $ProjectRoot "evidence\runs\$RunId"
    $ApiOut = Join-Path $RunDirectory "api.out.log"
    $ApiErr = Join-Path $RunDirectory "api.err.log"
    $WebOut = Join-Path $RunDirectory "openmct.out.log"
    $WebErr = Join-Path $RunDirectory "openmct.err.log"
    $Started.api = Start-Process -FilePath $Python -ArgumentList @(
        "-m", "lifeline.cli", "replay", "--run", $RunId, "--host", "127.0.0.1", "--port", "$ApiPort"
    ) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $ApiOut -RedirectStandardError $ApiErr -PassThru
    $Node = (Get-Command node.exe -ErrorAction Stop).Source
    $Vite = Join-Path $ProjectRoot "openmct\node_modules\vite\bin\vite.js"
    $env:VITE_LIFELINE_API_BASE = "http://127.0.0.1:$ApiPort"
    $Started.web = Start-Process -FilePath $Node -ArgumentList @(
        $Vite, "--host", "127.0.0.1", "--port", "$WebPort"
    ) -WorkingDirectory (Join-Path $ProjectRoot "openmct") -WindowStyle Hidden -RedirectStandardOutput $WebOut -RedirectStandardError $WebErr -PassThru

    $Ready = $false
    foreach ($Attempt in 1..40) {
        try {
            $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/health" -TimeoutSec 1
            $Page = Invoke-WebRequest -Uri "http://127.0.0.1:$WebPort/" -TimeoutSec 1
            if ($Health.status -eq "ok" -and $Health.selected_run -eq $RunId -and $Page.StatusCode -eq 200) {
                $Ready = $true
                break
            }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $Ready) { throw "The Lifeline replay API and dashboard did not become ready." }

    $ProcessManifest = [ordered]@{}
    foreach ($Name in $Started.Keys) {
        $Process = $Started[$Name]
        $Process.Refresh()
        $ProcessManifest[$Name] = [ordered]@{ id = $Process.Id; start_ticks = $Process.StartTime.ToUniversalTime().Ticks }
    }
    [ordered]@{
        run_id = $RunId
        api_port = $ApiPort
        web_port = $WebPort
        processes = $ProcessManifest
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $PidFile

    Start-Process "http://127.0.0.1:$WebPort/"
    $Completed = $true
    Write-Host "Project Lifeline is running. Run ID: $RunId"
    Write-Host "Use scripts/stop-demo.ps1 to stop only the recorded demo processes."
} finally {
    $env:VITE_LIFELINE_API_BASE = $PriorApiBase
    if (-not $Completed) { Stop-StartedProcesses }
    Pop-Location
}
