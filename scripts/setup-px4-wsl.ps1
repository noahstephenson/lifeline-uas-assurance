param(
    [switch]$Finalize
)

$ErrorActionPreference = "Stop"
$Distro = "Ubuntu-24.04"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$MinimumFreeBytes = 25GB
$NodeVersion = "20.20.2"
$NodeArchiveName = "node-v$NodeVersion-win-x64.zip"
$NodeDirectory = Join-Path $ProjectRoot ".tools\node-v$NodeVersion-win-x64"

function Install-PortableNode20 {
    $NodeExecutable = Join-Path $NodeDirectory "node.exe"
    if (Test-Path -LiteralPath $NodeExecutable) {
        $InstalledVersion = (& $NodeExecutable --version).Trim()
        if ($InstalledVersion -ne "v$NodeVersion") { throw "Portable Node version mismatch: $InstalledVersion." }
        return $NodeExecutable
    }

    $ToolsDirectory = Join-Path $ProjectRoot ".tools"
    $DownloadDirectory = Join-Path $ToolsDirectory "downloads"
    New-Item -ItemType Directory -Path $DownloadDirectory -Force | Out-Null
    $ArchivePath = Join-Path $DownloadDirectory $NodeArchiveName
    $ChecksumsPath = Join-Path $DownloadDirectory "node-v$NodeVersion-SHASUMS256.txt"
    $ReleaseBase = "https://nodejs.org/download/release/v$NodeVersion"
    Invoke-WebRequest -Uri "$ReleaseBase/$NodeArchiveName" -OutFile $ArchivePath
    Invoke-WebRequest -Uri "$ReleaseBase/SHASUMS256.txt" -OutFile $ChecksumsPath
    $ChecksumRecord = Get-Content -LiteralPath $ChecksumsPath | Where-Object { $_ -match "  $([regex]::Escape($NodeArchiveName))$" }
    if (-not $ChecksumRecord) { throw "The official Node checksum file does not list $NodeArchiveName." }
    $ExpectedHash = ($ChecksumRecord -split '\s+')[0].ToUpperInvariant()
    $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath).Hash.ToUpperInvariant()
    if ($ActualHash -ne $ExpectedHash) { throw "Node archive checksum mismatch." }
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $ToolsDirectory
    if (-not (Test-Path -LiteralPath $NodeExecutable)) { throw "Portable Node extraction did not produce $NodeExecutable." }
    return $NodeExecutable
}

function Invoke-WslBash([string]$Command) {
    & wsl.exe -d $Distro -- bash -lc $Command
    if ($LASTEXITCODE -ne 0) { throw "WSL command failed with exit code $LASTEXITCODE." }
}

$Drive = Get-PSDrive -Name ([System.IO.Path]::GetPathRoot($ProjectRoot).TrimEnd('\').TrimEnd(':'))
if ($Drive.Free -lt $MinimumFreeBytes) {
    throw "PX4 setup requires at least 25 GB free; found $([math]::Round($Drive.Free / 1GB, 1)) GB."
}

$Distributions = @(& wsl.exe --list --quiet) -replace "`0", ""
if ($Distributions -notcontains $Distro) {
    Write-Host "Installing $Distro side-by-side. Existing WSL distributions are not modified."
    & wsl.exe --install --distribution $Distro --no-launch
    if ($LASTEXITCODE -ne 0) { throw "Ubuntu 24.04 installation failed." }
    Write-Host "PAUSED: launch Ubuntu 24.04 once from the Start menu and create its local Linux account."
    Write-Host "Then rerun this script. This is the only required manual account-setup checkpoint."
    exit 10
}

$UbuntuRelease = (& wsl.exe -d $Distro -- bash -lc ". /etc/os-release && printf '%s' \"`$VERSION_ID\"") -join ""
if ($UbuntuRelease.Trim() -ne "24.04") { throw "Expected Ubuntu 24.04, found '$UbuntuRelease'." }
$DefaultUid = (& wsl.exe -d $Distro -- bash -lc "id -u") -join ""
if ($DefaultUid.Trim() -eq "0") {
    throw "Ubuntu first-launch account setup is incomplete: the default WSL user is still root."
}

$PortableNode = Install-PortableNode20
$PortableNpm = Join-Path (Split-Path -Parent $PortableNode) "npm.cmd"
& $PortableNpm ci --prefix (Join-Path $ProjectRoot "openmct")
if ($LASTEXITCODE -ne 0) { throw "Open MCT dependency installation under portable Node $NodeVersion failed." }

if (-not $Finalize) {
    Invoke-WslBash "test -d ~/PX4-Autopilot || git clone --branch v1.17.0 --recursive https://github.com/PX4/PX4-Autopilot.git ~/PX4-Autopilot"
    Invoke-WslBash "cd ~/PX4-Autopilot && git fetch --tags && git checkout --detach v1.17.0 && git submodule update --init --recursive"
    $Commit = (& wsl.exe -d $Distro -- bash -lc "cd ~/PX4-Autopilot && git rev-parse --short=7 HEAD") -join ""
    if ($Commit.Trim() -ne "d6f12ad") { throw "PX4 v1.17.0 commit mismatch: expected d6f12ad, found $Commit." }
    Write-Host "The upstream PX4 installer may request the Ubuntu local-account password."
    Invoke-WslBash "cd ~/PX4-Autopilot && bash Tools/setup/ubuntu.sh --no-nuttx && touch ~/.lifeline-px4-installer-complete"
    & wsl.exe --shutdown
    Write-Host "WSL shutdown checkpoint completed. Rerun: .\scripts\setup-px4-wsl.ps1 -Finalize"
    exit 11
}

Invoke-WslBash "test -f ~/.lifeline-px4-installer-complete"
$WslProject = (& wsl.exe -d $Distro -- wslpath -a $ProjectRoot) -join ""
$QuotedProject = $WslProject.Trim().Replace("'", "'`"'`"'")
Invoke-WslBash "python3 --version | grep -E '^Python 3\.12\.'"
Invoke-WslBash "python3 -m venv ~/.venvs/lifeline && ~/.venvs/lifeline/bin/python -m pip install --upgrade pip && ~/.venvs/lifeline/bin/pip install -e '$QuotedProject[px4]'"
Invoke-WslBash "~/.venvs/lifeline/bin/lifeline validate && ~/.venvs/lifeline/bin/lifeline doctor"
Write-Host "Ubuntu 24.04 PX4 environment is ready. Run scripts/qualify-px4.ps1 -Scenario Smoke next."
