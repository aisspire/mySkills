[CmdletBinding()]
param(
    [string]$CodexHome,
    [string]$RuntimeRoot,
    [string]$PythonPath,
    [switch]$AutoClose
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$effectiveCodexHome = if ([string]::IsNullOrWhiteSpace($CodexHome)) {
    if ([string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        Join-Path $env:USERPROFILE '.codex'
    }
    else { $env:CODEX_HOME }
}
else { $CodexHome }
$effectiveRuntime = if ([string]::IsNullOrWhiteSpace($RuntimeRoot)) {
    Join-Path $effectiveCodexHome 'database-schema-bootstrap'
}
else { $RuntimeRoot }
$python = if (-not [string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath
}
else {
    Join-Path $effectiveRuntime '.venv\Scripts\python.exe'
}
$arguments = @(
    '-B',
    (Join-Path $PSScriptRoot 'database_schema_bootstrap_cwd_smoke.py'),
    '--runtime-root',
    $effectiveRuntime
)
if ($AutoClose) { $arguments += '--auto-close' }
& $python @arguments
exit $LASTEXITCODE
