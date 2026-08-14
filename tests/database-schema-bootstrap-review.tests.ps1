[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-ReviewTrue {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Write-ReviewUtf8NoBom {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string]$Content
    )

    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Get-ReviewProjectId {
    param(
        [Parameter(Mandatory)]
        [string]$ProjectPath
    )

    $normalizedPath = [System.IO.Path]::GetFullPath($ProjectPath)
    $root = [System.IO.Path]::GetPathRoot($normalizedPath)
    while ($normalizedPath.Length -gt $root.Length -and $normalizedPath.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $normalizedPath = $normalizedPath.Substring(0, $normalizedPath.Length - 1)
    }
    $normalizedPath = $normalizedPath.ToLowerInvariant()
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($normalizedPath))
        return ([System.BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $hasher.Dispose()
    }
}

function Invoke-ReviewControlCommand {
    param(
        [Parameter(Mandatory)]
        [string]$ControlScriptPath,

        [Parameter(Mandatory)]
        [string[]]$Arguments,

        [int]$TimeoutMilliseconds = 45000
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = (Get-Command -Name powershell.exe -ErrorAction Stop).Source
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $argumentList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ControlScriptPath) + $Arguments
    $startInfo.Arguments = ($argumentList | ForEach-Object {
        '"' + ([string]$_).Replace('"', '\"') + '"'
    }) -join ' '
    $process = [System.Diagnostics.Process]::Start($startInfo)
    try {
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutMilliseconds)) {
            $process.Kill($true)
            throw "Review control command timed out: $($Arguments -join ' ')"
        }
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            StdOut = $stdoutTask.GetAwaiter().GetResult()
            StdErr = $stderrTask.GetAwaiter().GetResult()
        }
    }
    finally {
        $process.Dispose()
    }
}

function Start-ReviewControlCommand {
    param(
        [Parameter(Mandatory)]
        [string]$ControlScriptPath,

        [Parameter(Mandatory)]
        [string[]]$Arguments,

        [Parameter(Mandatory)]
        [string]$OutputDirectory
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = (Get-Command -Name powershell.exe -ErrorAction Stop).Source
    $startInfo.WorkingDirectory = $OutputDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $argumentList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ControlScriptPath) + $Arguments
    $startInfo.Arguments = ($argumentList | ForEach-Object {
        '"' + ([string]$_).Replace('"', '\"') + '"'
    }) -join ' '
    $process = [System.Diagnostics.Process]::Start($startInfo)
    return [pscustomobject]@{
        Process = $process
        StdOutTask = $process.StandardOutput.ReadToEndAsync()
        StdErrTask = $process.StandardError.ReadToEndAsync()
    }
}

function Get-ReviewServiceProcesses {
    param(
        [Parameter(Mandatory)]
        [string]$StatePath
    )

    return @(
        Get-CimInstance -ClassName Win32_Process |
            Where-Object {
                $_.CommandLine -is [string] -and $_.CommandLine.IndexOf(
                    $StatePath,
                    [System.StringComparison]::OrdinalIgnoreCase
                ) -ge 0
            }
    )
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).ProviderPath
$toolRoot = Join-Path $repoRoot 'tools\database-schema-bootstrap'
$installScriptPath = Join-Path $toolRoot 'install.ps1'
$controlScriptName = 'db-schema-bootstrap.ps1'
$pythonPath = $env:CODEX_PYTHON
if ([string]::IsNullOrWhiteSpace($pythonPath) -or -not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'CODEX_PYTHON must point to an existing Python executable for this test.'
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('database-schema-bootstrap-review-' + [Guid]::NewGuid().ToString('N'))
$codexHome = Join-Path $tempRoot '.codex'
$projectRoot = Join-Path $tempRoot 'project'
$serviceStatePath = $null
$orphanProcessIds = [System.Collections.Generic.List[int]]::new()

try {
    New-Item -ItemType Directory -Path $codexHome -Force | Out-Null
    New-Item -ItemType Directory -Path $projectRoot -Force | Out-Null
    Write-ReviewUtf8NoBom -Path (Join-Path $codexHome 'config.toml') -Content 'model = "review-test"'

    & git -C $projectRoot init --quiet
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to initialize the review Git project.'
    }

    & $installScriptPath -PythonPath $pythonPath -CodexHome $codexHome -SkipDependencyInstall
    Assert-ReviewTrue -Condition ($LASTEXITCODE -eq 0) -Message 'Initial review fixture installation failed.'

    $runtimeRoot = Join-Path $codexHome 'database-schema-bootstrap'
    $controlScriptPath = Join-Path $runtimeRoot "control\$controlScriptName"
    $installStatePath = Join-Path $runtimeRoot 'install-state.json'
    $projectId = Get-ReviewProjectId -ProjectPath $projectRoot
    $serviceStatePath = Join-Path $runtimeRoot "state\projects\$projectId.json"

    & $controlScriptPath profile add -ProjectPath $projectRoot -Name default -DatabaseHost '127.0.0.1' -Database app -ConnectionDatabase postgres -DatabaseUser metadata_user | Out-Null
    Assert-ReviewTrue -Condition ($LASTEXITCODE -eq 0) -Message 'Failed to create the review project profile.'

    # RED: the old uninstall path treats a missing recorded service state as
    # harmless and proceeds with state cleanup.
    $installState = Get-Content -LiteralPath $installStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $installState.service_state_files = @([ordered]@{
        path = [System.IO.Path]::GetFullPath($serviceStatePath).ToLowerInvariant()
        sha256 = 'missing-state-fixture'
        project_root = [System.IO.Path]::GetFullPath($projectRoot)
        project_id = $projectId
    })
    Write-ReviewUtf8NoBom -Path $installStatePath -Content ($installState | ConvertTo-Json -Depth 12)
    if (Test-Path -LiteralPath $serviceStatePath -PathType Leaf) {
        Remove-Item -LiteralPath $serviceStatePath -Force
    }
    $missingStateResult = Invoke-ReviewControlCommand -ControlScriptPath (Join-Path $toolRoot 'uninstall.ps1') -Arguments @('-CodexHome', $codexHome, '-Categories', 'state', '-ConfirmAll')
    Assert-ReviewTrue -Condition ($missingStateResult.ExitCode -ne 0) -Message "Core cleanup must block a missing recorded service state. Output: $($missingStateResult.StdOut)$($missingStateResult.StdErr)"
    Assert-ReviewTrue -Condition (Test-Path -LiteralPath $runtimeRoot -PathType Container) -Message 'Blocked missing-state cleanup must preserve the runtime.'

    & $controlScriptPath session-start -ProjectPath $projectRoot | Out-Null
    Assert-ReviewTrue -Condition ($LASTEXITCODE -eq 0) -Message 'Failed to start the review service after the missing-state check.'
    $beforeUpgradeStatus = & $controlScriptPath status -ProjectPath $projectRoot
    Assert-ReviewTrue -Condition ($beforeUpgradeStatus.ServiceState -eq 'running') -Message 'Expected a healthy service before the upgrade check.'
    $beforeUpgradePid = [int]$beforeUpgradeStatus.Pid

    # RED: the old installer replaces runtime directories while retaining the
    # running service and its state record, so the PID does not change.
    & $installScriptPath -PythonPath $pythonPath -CodexHome $codexHome -SkipDependencyInstall
    Assert-ReviewTrue -Condition ($LASTEXITCODE -eq 0) -Message 'Runtime upgrade fixture failed.'
    $afterUpgradeStatus = & (Join-Path $runtimeRoot "control\$controlScriptName") status -ProjectPath $projectRoot
    Assert-ReviewTrue -Condition ($afterUpgradeStatus.ServiceState -eq 'running') -Message 'Expected the upgraded service to be healthy.'
    Assert-ReviewTrue -Condition ([int]$afterUpgradeStatus.Pid -ne $beforeUpgradePid) -Message 'Runtime upgrade must restart the recorded project service.'

    & $controlScriptPath session-stop -ProjectPath $projectRoot | Out-Null
    Assert-ReviewTrue -Condition ($LASTEXITCODE -eq 0) -Message 'Failed to stop the service before the startup cleanup check.'

    $badServiceScript = @'
import argparse
import json
import os
import time

parser = argparse.ArgumentParser()
parser.add_argument("--ready-state", required=True)
parser.add_argument("--project-id", required=True)
parser.add_argument("--project-root", required=True)
parser.add_argument("--instance-token", required=True)
parser.add_argument("--port", required=True)
args, _ = parser.parse_known_args()
payload = {
    "version": 1,
    "project_id": args.project_id,
    "project_root": args.project_root,
    "endpoint": "http://127.0.0.1:65500",
    "port": 65500,
    "pid": os.getpid(),
    "instance_token": args.instance_token,
}
with open(args.ready_state, "w", encoding="utf-8") as handle:
    json.dump(payload, handle)
time.sleep(60)
'@
    Write-ReviewUtf8NoBom -Path (Join-Path $runtimeRoot 'service\server.py') -Content $badServiceScript

    # RED: the old startup failure path leaves this long-running process and
    # its ready-state file behind after the lifecycle deadline expires.
    $startupResult = Invoke-ReviewControlCommand -ControlScriptPath $controlScriptPath -Arguments @('session-start', '-ProjectPath', $projectRoot) -TimeoutMilliseconds 40000
    Assert-ReviewTrue -Condition ($startupResult.ExitCode -ne 0) -Message 'The deliberately unhealthy service must fail startup.'
    Assert-ReviewTrue -Condition (-not (Test-Path -LiteralPath $serviceStatePath -PathType Leaf)) -Message 'Failed service startup must remove its owned ready-state file.'
    $remainingServiceProcesses = @(Get-ReviewServiceProcesses -StatePath $serviceStatePath)
    Assert-ReviewTrue -Condition ($remainingServiceProcesses.Count -eq 0) -Message 'Failed service startup must not leave an unregistered service process.'

    Copy-Item -LiteralPath (Join-Path $repoRoot 'mcp\database-schema-bootstrap\server.py') -Destination (Join-Path $runtimeRoot 'service\server.py') -Force
    & $installScriptPath -PythonPath $pythonPath -CodexHome $codexHome -SkipDependencyInstall
    Assert-ReviewTrue -Condition ($LASTEXITCODE -eq 0) -Message 'Failed to restore the runtime before the uninstall concurrency check.'
    $controlScriptPath = Join-Path $runtimeRoot "control\$controlScriptName"
    & $controlScriptPath session-start -ProjectPath $projectRoot | Out-Null
    Assert-ReviewTrue -Condition ($LASTEXITCODE -eq 0) -Message 'Failed to start the service before the uninstall concurrency check.'

    $uninstallProcess = Start-ReviewControlCommand -ControlScriptPath (Join-Path $toolRoot 'uninstall.ps1') -Arguments @('-CodexHome', $codexHome, '-All', '-ConfirmAll') -OutputDirectory $tempRoot
    Start-Sleep -Milliseconds 250
    $sessionStartProcess = Start-ReviewControlCommand -ControlScriptPath $controlScriptPath -Arguments @('session-start', '-ProjectPath', $projectRoot) -OutputDirectory $tempRoot
    if (-not $uninstallProcess.Process.WaitForExit(70000)) {
        $uninstallProcess.Process.Kill($true)
        throw 'Concurrent uninstall did not exit within the lifecycle test budget.'
    }
    if (-not $sessionStartProcess.Process.WaitForExit(70000)) {
        $sessionStartProcess.Process.Kill($true)
        throw 'Concurrent session-start did not exit within the lifecycle test budget.'
    }
    $uninstallProcess.Process.Refresh()
    $sessionStartProcess.Process.Refresh()
    $uninstallOutput = $uninstallProcess.StdOutTask.GetAwaiter().GetResult() + $uninstallProcess.StdErrTask.GetAwaiter().GetResult()
    $sessionStartOutput = $sessionStartProcess.StdOutTask.GetAwaiter().GetResult() + $sessionStartProcess.StdErrTask.GetAwaiter().GetResult()
    Assert-ReviewTrue -Condition ($uninstallProcess.Process.ExitCode -eq 0) -Message "Concurrent uninstall must complete safely (uninstall exit=$($uninstallProcess.Process.ExitCode), session-start exit=$($sessionStartProcess.Process.ExitCode)). Uninstall output: $uninstallOutput. Session-start output: $sessionStartOutput"
    Assert-ReviewTrue -Condition (-not (Test-Path -LiteralPath $runtimeRoot)) -Message 'Concurrent uninstall must remove the runtime after serializing service operations.'
    Assert-ReviewTrue -Condition ((@(Get-ReviewServiceProcesses -StatePath $serviceStatePath)).Count -eq 0) -Message 'Concurrent uninstall must not leave a service process after runtime cleanup.'

    Write-Output 'database-schema-bootstrap review regression tests passed.'
}
finally {
    if ($null -ne $serviceStatePath) {
        foreach ($process in @(Get-ReviewServiceProcesses -StatePath $serviceStatePath -ErrorAction SilentlyContinue)) {
            $orphanProcessIds.Add([int]$process.ProcessId)
        }
    }
    foreach ($processId in $orphanProcessIds) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
