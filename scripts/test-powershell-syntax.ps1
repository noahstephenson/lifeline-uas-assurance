$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Failures = @()

foreach ($Script in Get-ChildItem -LiteralPath $PSScriptRoot -Filter "*.ps1" -File) {
    $Tokens = $null
    $Errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $Script.FullName,
        [ref]$Tokens,
        [ref]$Errors
    ) | Out-Null
    foreach ($ParseError in $Errors) {
        $Failures += "$($Script.Name):$($ParseError.Extent.StartLineNumber): $($ParseError.Message)"
    }
}

if ($Failures.Count -gt 0) {
    $Failures | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host "PowerShell syntax gate passed for $((Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1' -File).Count) scripts under $ProjectRoot."
