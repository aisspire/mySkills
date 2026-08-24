[CmdletBinding()]
param([string]$PythonPath)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).ProviderPath
$python = if (-not [string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath
}
elseif (-not [string]::IsNullOrWhiteSpace($env:CODEX_PYTHON)) {
    $env:CODEX_PYTHON
}
else { (Get-Command python -ErrorAction Stop).Source }
Push-Location $repoRoot
try {
    & $python -B -m unittest `
        tests.test_database_schema_bootstrap.ConfigTests `
        tests.test_database_schema_bootstrap.AdapterRoutingTests `
        tests.test_database_schema_bootstrap.GatewayTests -v
    exit $LASTEXITCODE
}
finally { Pop-Location }
