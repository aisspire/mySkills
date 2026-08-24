[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ControlArguments
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$runtimeRoot = [System.IO.Directory]::GetParent($PSScriptRoot).FullName
$python = Join-Path $runtimeRoot '.venv\Scripts\python.exe'
$control = Join-Path $PSScriptRoot 'control.py'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'The dedicated database-schema-bootstrap venv is unavailable.'
}

& $python -B $control --runtime-root $runtimeRoot @ControlArguments
exit $LASTEXITCODE
