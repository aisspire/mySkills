[CmdletBinding()]
param(
    [string]$PythonPath,
    [string]$CodexHome,
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$launcher = if (-not [string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath
}
elseif (-not [string]::IsNullOrWhiteSpace($env:CODEX_PYTHON)) {
    $env:CODEX_PYTHON
}
else {
    (Get-Command python -ErrorAction Stop).Source
}

$arguments = @('-B', (Join-Path $PSScriptRoot 'install.py'))
if (-not [string]::IsNullOrWhiteSpace($PythonPath)) {
    $arguments += @('--python', $PythonPath)
}
if (-not [string]::IsNullOrWhiteSpace($CodexHome)) {
    $arguments += @('--codex-home', $CodexHome)
}
if ($SkipDependencyInstall) {
    $arguments += '--skip-dependency-install'
}

& $launcher @arguments
exit $LASTEXITCODE
