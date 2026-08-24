[CmdletBinding()]
param(
    [string]$PythonPath,
    [string]$CodexHome,
    [string]$Categories,
    [switch]$All,
    [switch]$Confirm,
    [switch]$ConfirmAll,
    [switch]$InventoryOnly
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

$arguments = @('-B', (Join-Path $PSScriptRoot 'uninstall.py'))
if (-not [string]::IsNullOrWhiteSpace($CodexHome)) {
    $arguments += @('--codex-home', $CodexHome)
}
if (-not [string]::IsNullOrWhiteSpace($Categories)) {
    $arguments += @('--categories', $Categories)
}
if ($All) { $arguments += '--all' }
if ($Confirm) { $arguments += '--confirm' }
if ($ConfirmAll) { $arguments += '--confirm-all' }
if ($InventoryOnly) { $arguments += '--inventory-only' }

& $launcher @arguments
exit $LASTEXITCODE
