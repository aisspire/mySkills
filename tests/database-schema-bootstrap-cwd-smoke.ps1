[CmdletBinding()]
param(
    [string]$CodexHome,

    [string]$RuntimeRoot,

    [string]$PythonPath,

    [switch]$AutoClose
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).ProviderPath
$modulePath = Join-Path $repoRoot 'tools\database-schema-bootstrap\DbSchemaBootstrap.Common.psm1'
$fakeServicePath = Join-Path $PSScriptRoot 'database_schema_bootstrap_fake_service.py'
Import-Module $modulePath -Force

function ConvertTo-DsbSmokeProcessArgument {
    param([Parameter(Mandatory)][string]$Value)

    if ($Value -notmatch '[\s"]') {
        return $Value
    }
    $escaped = $Value -replace '(\\*)"', '$1$1\\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Remove-DsbSmokeStateIfOwned {
    param(
        [Parameter(Mandatory)][string]$StatePath,
        [Parameter(Mandatory)][string]$InstanceToken
    )

    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
        return
    }
    try {
        $state = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        return
    }
    if ((Get-DsbObjectProperty -Object $state -Name 'instance_token') -ceq $InstanceToken) {
        Remove-Item -LiteralPath $StatePath -Force
    }
}

function Wait-DsbSmokeState {
    param(
        [Parameter(Mandatory)][string]$StatePath,
        [Parameter(Mandatory)][string]$InstanceToken,
        [Parameter(Mandatory)][System.Diagnostics.Process]$Process
    )

    for ($attempt = 0; $attempt -lt 100; $attempt++) {
        if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
            try {
                $state = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
                if ((Get-DsbObjectProperty -Object $state -Name 'instance_token') -ceq $InstanceToken) {
                    return $state
                }
            }
            catch {
            }
        }
        if ($Process.HasExited) {
            throw "FakeService exited before writing state: $StatePath"
        }
        Start-Sleep -Milliseconds 100
    }
    throw "FakeService did not write its token-bound state: $StatePath"
}

function Start-DsbSmokeService {
    param(
        [Parameter(Mandatory)][string]$PythonExecutable,
        [Parameter(Mandatory)][string]$ProjectRoot,
        [Parameter(Mandatory)][string]$ProjectId,
        [Parameter(Mandatory)][string]$StatePath,
        [Parameter(Mandatory)][string]$Marker,
        [Parameter(Mandatory)][string]$LogDirectory
    )

    $token = [Guid]::NewGuid().ToString('N')
    $arguments = @(
        '-B', $fakeServicePath,
        '--ready-state', $StatePath,
        '--project-id', $ProjectId,
        '--project-root', (Get-DsbNormalizedPath -Path $ProjectRoot),
        '--instance-token', $token,
        '--marker', $Marker
    )
    $argumentLine = (@($arguments | ForEach-Object { ConvertTo-DsbSmokeProcessArgument -Value $_ })) -join ' '
    $process = Start-Process -FilePath $PythonExecutable -ArgumentList $argumentLine -WorkingDirectory $PSScriptRoot -RedirectStandardOutput (Join-Path $LogDirectory ($Marker + '.stdout.log')) -RedirectStandardError (Join-Path $LogDirectory ($Marker + '.stderr.log')) -WindowStyle Hidden -PassThru
    $state = Wait-DsbSmokeState -StatePath $StatePath -InstanceToken $token -Process $process
    return [pscustomobject]@{
        Process = $process
        StatePath = $StatePath
        InstanceToken = $token
        Marker = $Marker
        State = $state
    }
}

$temporaryRoot = $null
$services = @()
try {
    if (-not (Test-Path -LiteralPath $fakeServicePath -PathType Leaf)) {
        throw "FakeService fixture is missing: $fakeServicePath"
    }
    $effectiveRuntimeRoot = Get-DsbRuntimeRoot -CodexHome $CodexHome -RuntimeRoot $RuntimeRoot
    $installState = Get-DsbInstallState -RuntimeRoot $effectiveRuntimeRoot -Required
    $effectivePythonPath = if ([string]::IsNullOrWhiteSpace($PythonPath)) {
        Get-DsbObjectProperty -Object $installState -Name 'python_path'
    }
    else {
        Resolve-DsbPython -PythonPath $PythonPath
    }
    if ($effectivePythonPath -isnot [string] -or -not (Test-Path -LiteralPath $effectivePythonPath -PathType Leaf)) {
        throw 'The installed Python path is unavailable. Re-run install.ps1 with -PythonPath.'
    }

    $temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('database-schema-bootstrap-cwd-smoke-' + [Guid]::NewGuid().ToString('N'))
    $projectA = Join-Path $temporaryRoot 'project-a'
    $projectB = Join-Path $temporaryRoot 'project-b'
    $logDirectory = Join-Path $temporaryRoot 'logs'
    New-Item -ItemType Directory -Path $projectA, $projectB, $logDirectory -Force | Out-Null
    foreach ($projectRoot in @($projectA, $projectB)) {
        & git -C $projectRoot init --quiet
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to initialize smoke-test Git project: $projectRoot"
        }
    }

    $projectAId = Get-DsbProjectId -ProjectRoot $projectA
    $projectBId = Get-DsbProjectId -ProjectRoot $projectB
    $statePathA = Get-DsbServiceStatePath -RuntimeRoot $effectiveRuntimeRoot -ProjectId $projectAId
    $statePathB = Get-DsbServiceStatePath -RuntimeRoot $effectiveRuntimeRoot -ProjectId $projectBId
    foreach ($statePath in @($statePathA, $statePathB)) {
        if (Test-Path -LiteralPath $statePath -PathType Leaf) {
            throw "Refusing to overwrite an existing project state: $statePath"
        }
    }

    $services += Start-DsbSmokeService -PythonExecutable $effectivePythonPath -ProjectRoot $projectA -ProjectId $projectAId -StatePath $statePathA -Marker 'cwd_smoke_project_a_table' -LogDirectory $logDirectory
    $services += Start-DsbSmokeService -PythonExecutable $effectivePythonPath -ProjectRoot $projectB -ProjectId $projectBId -StatePath $statePathB -Marker 'cwd_smoke_project_b_table' -LogDirectory $logDirectory

    Write-Output 'FakeService cwd smoke fixture is ready. It creates no profiles and does not connect to PostgreSQL.'
    Write-Output ''
    Write-Output 'Run these commands in separate terminals while this script remains open:'
    Write-Output ('codex exec -C "{0}" "Use only the database-schema-bootstrap MCP list_tables tool. Return only the table name."' -f $projectA)
    Write-Output ('Expected table: {0}' -f $services[0].Marker)
    Write-Output ('codex exec -C "{0}" "Use only the database-schema-bootstrap MCP list_tables tool. Return only the table name."' -f $projectB)
    Write-Output ('Expected table: {0}' -f $services[1].Marker)
    if ($AutoClose) {
        Write-Output 'AutoClose was requested; cleaning up the fixture now.'
    }
    else {
        Read-Host 'Press Enter after recording both results; cleanup removes only states whose fixture token still matches'
    }
}
finally {
    foreach ($service in @($services)) {
        if ($null -ne $service.Process -and -not $service.Process.HasExited) {
            Stop-Process -Id $service.Process.Id -Force -ErrorAction SilentlyContinue
            Wait-Process -Id $service.Process.Id -Timeout 10 -ErrorAction SilentlyContinue
        }
        Remove-DsbSmokeStateIfOwned -StatePath $service.StatePath -InstanceToken $service.InstanceToken
    }
    if ($null -ne $temporaryRoot -and (Test-Path -LiteralPath $temporaryRoot)) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
