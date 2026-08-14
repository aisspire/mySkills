Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Write-DsbTestDiagnostic {
    param([string]$Message)

    if ($env:DSB_TEST_DIAGNOSTICS -eq '1') {
        Write-Host "[database-schema-bootstrap test] $Message"
    }
    if (-not [string]::IsNullOrWhiteSpace($env:DSB_TEST_DIAGNOSTIC_PATH)) {
        [System.IO.File]::AppendAllText(
            $env:DSB_TEST_DIAGNOSTIC_PATH,
            "$(Get-Date -Format 'HH:mm:ss.fff') $Message$([Environment]::NewLine)",
            [System.Text.UTF8Encoding]::new($false)
        )
    }
}

function Get-DsbProjectIdForTest {
    param(
        [Parameter(Mandatory)]
        [string]$ProjectPath
    )

    $normalizedPath = [System.IO.Path]::GetFullPath($ProjectPath).Replace([System.IO.Path]::AltDirectorySeparatorChar, [System.IO.Path]::DirectorySeparatorChar)
    $root = [System.IO.Path]::GetPathRoot($normalizedPath)
    while ($normalizedPath.Length -gt $root.Length -and $normalizedPath.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $normalizedPath = $normalizedPath.Substring(0, $normalizedPath.Length - 1)
    }
    $normalizedPath = $normalizedPath.ToLowerInvariant()
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($normalizedPath))
        return ([System.BitConverter]::ToString($hashBytes)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $hasher.Dispose()
    }
}

function Get-DsbProjectStatePathForTest {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectPath
    )

    return Join-Path $RuntimeRoot ('state\projects\' + (Get-DsbProjectIdForTest -ProjectPath $ProjectPath) + '.json')
}

function Wait-DsbJobsForTest {
    param(
        [Parameter(Mandatory)]
        [object[]]$Jobs
    )

    try {
        Wait-Job -Job $Jobs -Timeout 40 | Out-Null
        $unfinished = @($Jobs | Where-Object { $_.State -ne 'Completed' })
        if ($unfinished.Count -gt 0) {
            foreach ($job in $unfinished) {
                Write-DsbTestDiagnostic ("job id=" + $job.Id + " state=" + $job.State + " status=" + $job.StatusMessage)
                foreach ($childJob in @($job.ChildJobs)) {
                    $reason = $childJob.JobStateInfo.Reason
                    if ($null -ne $reason) {
                        Write-DsbTestDiagnostic ("job id=" + $job.Id + " reason=" + ($reason | Out-String).Trim())
                    }
                }
                $jobOutput = @(Receive-Job -Job $job -Keep -ErrorAction SilentlyContinue *>&1)
                foreach ($output in $jobOutput) {
                    Write-DsbTestDiagnostic ("job id=" + $job.Id + " output=" + ($output | Out-String).Trim())
                }
            }
            throw 'Timed out waiting for concurrent database-schema-bootstrap control operations.'
        }
        foreach ($job in $Jobs) {
            Receive-Job -Job $job -ErrorAction Stop | Out-Null
        }
    }
    finally {
        foreach ($job in $Jobs) {
            if ($job.State -eq 'Running') {
                Stop-Job -Job $job -ErrorAction SilentlyContinue
            }
            Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        }
    }
}

function Start-DsbSessionStartJobForTest {
    param(
        [Parameter(Mandatory)]
        [string]$ControlScriptPath,

        [Parameter(Mandatory)]
        [string]$ProjectPath
    )

    return Start-Job -ScriptBlock {
        param($ScriptPath, $Path)
        $ErrorActionPreference = 'Stop'
        & $ScriptPath session-start -ProjectPath $Path
        if ($LASTEXITCODE -ne 0) {
            throw "session-start failed for $Path with exit code $LASTEXITCODE"
        }
    } -ArgumentList $ControlScriptPath, $ProjectPath
}

function Get-DsbServiceProcessesForStateForTest {
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

function Set-DsbTestProcessArguments {
    param(
        [Parameter(Mandatory)]
        [System.Diagnostics.ProcessStartInfo]$StartInfo,

        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $argumentListProperty = $StartInfo.PSObject.Properties['ArgumentList']
    if ($null -ne $argumentListProperty) {
        foreach ($argument in $Arguments) {
            $StartInfo.ArgumentList.Add($argument)
        }
        return
    }

    $StartInfo.Arguments = @($Arguments | ForEach-Object {
        if ($_ -match '[\s"]') {
            '"' + $_.Replace('"', '\"') + '"'
        }
        else {
            $_
        }
    }) -join ' '
}

function Invoke-DsbHookSessionStartForTest {
    param(
        [Parameter(Mandatory)]
        [string]$ControlScriptPath,

        [Parameter(Mandatory)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory)]
        [string]$HookEventJson,

        [string]$ExplicitProjectPath
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = (Get-Command -Name powershell.exe -ErrorAction Stop).Source
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.WorkingDirectory = $WorkingDirectory
    $processArguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ControlScriptPath)
    if (-not [string]::IsNullOrWhiteSpace($ExplicitProjectPath)) {
        $processArguments += @('session-start', '-ProjectPath', $ExplicitProjectPath)
    }
    else {
        $processArguments += 'session-start'
    }
    Set-DsbTestProcessArguments -StartInfo $startInfo -Arguments $processArguments
    $process = [System.Diagnostics.Process]::Start($startInfo)
    try {
        $process.StandardInput.Write($HookEventJson)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(35000)) {
            $process.Kill($true)
            throw 'SessionStart hook process did not exit within 35 seconds.'
        }
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            StdOut = ''
            StdErr = ''
        }
    }
    finally {
        $process.Dispose()
    }
}

function Invoke-DsbControlCommandForTest {
    param(
        [Parameter(Mandatory)]
        [string]$ControlScriptPath,

        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = (Get-Command -Name powershell.exe -ErrorAction Stop).Source
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    Set-DsbTestProcessArguments -StartInfo $startInfo -Arguments (@('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ControlScriptPath) + $Arguments)
    Write-DsbTestDiagnostic ("starting isolated control command: " + ($Arguments -join ' '))
    $process = [System.Diagnostics.Process]::Start($startInfo)
    try {
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(35000)) {
            $process.Kill($true)
            throw 'Control command did not exit within 35 seconds.'
        }
        Write-DsbTestDiagnostic ("isolated control command exited: " + $process.ExitCode)
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

function Stop-DsbOrphanedServicesForTest {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [int[]]$ProcessIds
    )

    foreach ($serviceProcessId in $ProcessIds) {
        $serviceProcess = Get-Process -Id $serviceProcessId -ErrorAction SilentlyContinue
        if ($null -ne $serviceProcess) {
            Stop-Process -Id $serviceProcessId -Force -ErrorAction Stop
            Wait-Process -Id $serviceProcessId -Timeout 10 -ErrorAction SilentlyContinue
        }
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).ProviderPath
$toolRoot = Join-Path $repoRoot "tools\database-schema-bootstrap"
$installScriptPath = Join-Path $toolRoot "install.ps1"

Assert-True -Condition (Test-Path -LiteralPath $installScriptPath -PathType Leaf) -Message "Expected the global database-schema-bootstrap installer source."

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("database-schema-bootstrap-global-" + [Guid]::NewGuid().ToString("N"))
$controlScriptPath = $null
$projectA = $null
$projectB = $null
$orphanedServicePids = @()

try {
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    $codexHome = Join-Path $tempRoot ".codex"
    New-Item -ItemType Directory -Path $codexHome | Out-Null
    $configPath = Join-Path $codexHome "config.toml"
    $unmanagedConfig = @(
        'model = "gpt-test"'
        ''
        '[mcp_servers.unmanaged]'
        'command = "unmanaged.exe"'
    ) -join [Environment]::NewLine
    Set-Content -LiteralPath $configPath -Value $unmanagedConfig -Encoding UTF8

    & $installScriptPath -CodexHome $codexHome -SkipDependencyInstall
    if ($LASTEXITCODE -ne 0) {
        throw "Global installer exited with code $LASTEXITCODE"
    }
    Write-DsbTestDiagnostic 'initial installation completed'

    $runtimeRoot = Join-Path $codexHome "database-schema-bootstrap"
    $installedConfig = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8
    $statePath = Join-Path $runtimeRoot "install-state.json"
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-True -Condition (Test-Path -LiteralPath (Join-Path $runtimeRoot "adapter\mcp_server.py") -PathType Leaf) -Message "Expected adapter to be copied into the user-level runtime."
    Assert-True -Condition (Test-Path -LiteralPath (Join-Path $runtimeRoot "service\server.py") -PathType Leaf) -Message "Expected service to be copied into the user-level runtime."
    Assert-True -Condition (Test-Path -LiteralPath (Join-Path $runtimeRoot "control\db-schema-bootstrap.ps1") -PathType Leaf) -Message "Expected control script to be copied into the user-level runtime."
    Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $runtimeRoot "service\service\__pycache__"))) -Message "Expected runtime installation to exclude Python bytecode cache directories."
    Assert-True -Condition ($installedConfig -match [regex]::Escape('model = "gpt-test"')) -Message "Expected installer to preserve unmanaged Codex configuration."
    Assert-True -Condition ($installedConfig -match '\[mcp_servers\.database-schema-bootstrap\]') -Message "Expected installer to register the global MCP adapter."
    Assert-True -Condition ($installedConfig -match 'enabled_tools = \["list_databases", "list_tables", "describe_table"\]') -Message "Expected MCP configuration to whitelist exactly three tools."
    Assert-True -Condition ($installedConfig -match 'args = \["-B", .*"--timeout", "25"\]') -Message "Expected managed MCP configuration to pass the 25 second adapter deadline."
    Assert-True -Condition ($installedConfig -match 'tool_timeout_sec = 30') -Message "Expected managed MCP tool timeout to allow the 25 second adapter deadline."
    Assert-True -Condition ($installedConfig -match '\[\[hooks\.SessionStart\]\]') -Message "Expected installer to register the inline SessionStart hook."
    Assert-True -Condition ($installedConfig -match '(?m)^timeout = 30\r?$') -Message "Expected SessionStart hook timeout to allow lifecycle recovery."
    Assert-True -Condition ($installedConfig -notmatch [regex]::Escape($repoRoot)) -Message "Expected managed config to use the installed runtime instead of the source repository."
    & $env:CODEX_PYTHON -c "import pathlib, tomllib; tomllib.loads(pathlib.Path(r'$configPath').read_text(encoding='utf-8'))"
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Message "Expected generated config.toml to be valid TOML."

    & $installScriptPath -PythonPath $env:CODEX_PYTHON -CodexHome $codexHome -SkipDependencyInstall
    if ($LASTEXITCODE -ne 0) {
        throw "Idempotent global installer exited with code $LASTEXITCODE"
    }
    Write-DsbTestDiagnostic 'idempotent installation completed'
    $reinstalledConfig = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8
    $startMarkerCount = ([regex]::Matches($reinstalledConfig, '(?m)^# >>> database-schema-bootstrap managed id=')).Count
    Assert-True -Condition ($startMarkerCount -eq 1) -Message "Expected idempotent installation to keep exactly one managed configuration block."
    $reinstalledState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-True -Condition ($state.installation_id -eq $reinstalledState.installation_id) -Message "Expected idempotent installation to keep its installation ID."

    $controlScriptPath = Join-Path $runtimeRoot "control\db-schema-bootstrap.ps1"
    $projectA = Join-Path $tempRoot "project-a"
    $projectB = Join-Path $tempRoot "project-b"
    foreach ($projectPath in @($projectA, $projectB)) {
        New-Item -ItemType Directory -Path $projectPath | Out-Null
        & git -C $projectPath init --quiet
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to initialize temporary Git project: $projectPath"
        }
        $profileDirectory = Join-Path $projectPath '.agents\database-schema-bootstrap\profiles'
        foreach ($reservedName in @('active-profile', 'ACTIVE-PROFILE')) {
            $reservedResult = Invoke-DsbControlCommandForTest -ControlScriptPath $controlScriptPath -Arguments @('profile', 'add', '-ProjectPath', $projectPath, '-Name', $reservedName, '-DatabaseHost', '127.0.0.1', '-Database', 'app', '-ConnectionDatabase', 'postgres', '-DatabaseUser', 'metadata_user')
            $reservedOutput = $reservedResult.StdOut + $reservedResult.StdErr
            $reservedExitCode = $reservedResult.ExitCode
            Assert-True -Condition ($reservedExitCode -ne 0) -Message "Expected reserved profile name to fail before writing: $reservedName"
            Assert-True -Condition ($reservedOutput -match "reserved for active-profile\.json") -Message "Expected reserved profile error for $reservedName. Output: $reservedOutput"
            Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $profileDirectory ($reservedName + '.json')) -PathType Leaf)) -Message "Reserved profile name must not create a profile file: $reservedName"
        }
        Assert-True -Condition (-not (Test-Path -LiteralPath $profileDirectory -PathType Container)) -Message "Reserved profile validation must run before creating the profile directory."
        & $controlScriptPath profile add -ProjectPath $projectPath -Name default -DatabaseHost "127.0.0.1" -Database app -ConnectionDatabase postgres -DatabaseUser metadata_user -CredentialTarget ("database-schema-bootstrap/test/" + [System.IO.Path]::GetFileName($projectPath)) | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to add default project profile: $projectPath"
        }
    }

    Wait-DsbJobsForTest -Jobs @(
        (Start-DsbSessionStartJobForTest -ControlScriptPath $controlScriptPath -ProjectPath $projectA),
        (Start-DsbSessionStartJobForTest -ControlScriptPath $controlScriptPath -ProjectPath $projectB)
    )
    Write-DsbTestDiagnostic 'cross-project concurrent session-start completed'
    $statusA = & $controlScriptPath status -ProjectPath $projectA
    $statusB = & $controlScriptPath status -ProjectPath $projectB
    Assert-True -Condition ($statusA.ServiceState -eq 'running') -Message "Expected the default profile to start project A service."
    Assert-True -Condition ($statusA.ProfileSource -eq 'default') -Message "Expected project A to use default.json when no active profile exists."
    Assert-True -Condition ($statusB.ServiceState -eq 'running') -Message "Expected project B service to run independently."
    Assert-True -Condition ($statusA.Endpoint -ne $statusB.Endpoint) -Message "Expected two projects to receive independent loopback service instances."
    $projectBPid = $statusB.Pid
    $statePathA = Get-DsbProjectStatePathForTest -RuntimeRoot $runtimeRoot -ProjectPath $projectA
    $statePathB = Get-DsbProjectStatePathForTest -RuntimeRoot $runtimeRoot -ProjectPath $projectB
    $installedServiceScript = [System.IO.Path]::GetFullPath((Join-Path $runtimeRoot 'service\server.py'))
    $projectAProcesses = Get-DsbServiceProcessesForStateForTest -StatePath $statePathA
    Assert-True -Condition ($projectAProcesses.Count -eq 1) -Message "Expected one running project A service process after startup."
    Assert-True -Condition ($projectAProcesses[0].CommandLine.IndexOf($installedServiceScript, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) -Message "Expected the installed service process to launch the copied server.py path."
    Assert-True -Condition ($projectAProcesses[0].CommandLine.IndexOf('-m service.server', [System.StringComparison]::OrdinalIgnoreCase) -lt 0) -Message "Expected the installed service process not to use the incompatible service.server module launch."
    $parallelInstallState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $registeredStatePaths = @($parallelInstallState.service_state_files | ForEach-Object { $_.path })
    Assert-True -Condition ($registeredStatePaths -contains ([System.IO.Path]::GetFullPath($statePathA).ToLowerInvariant())) -Message "Expected concurrent project A start to remain recorded in install-state.json."
    Assert-True -Condition ($registeredStatePaths -contains ([System.IO.Path]::GetFullPath($statePathB).ToLowerInvariant())) -Message "Expected concurrent project B start to remain recorded in install-state.json."

    & $controlScriptPath session-stop -ProjectPath $projectA
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to stop project A before same-project concurrency test"
    }
    Wait-DsbJobsForTest -Jobs @(
        (Start-DsbSessionStartJobForTest -ControlScriptPath $controlScriptPath -ProjectPath $projectA),
        (Start-DsbSessionStartJobForTest -ControlScriptPath $controlScriptPath -ProjectPath $projectA)
    )
    Write-DsbTestDiagnostic 'same-project concurrent session-start completed'
    $sameProjectStatusA = & $controlScriptPath status -ProjectPath $projectA
    $sameProjectStateA = Get-Content -LiteralPath $statePathA -Raw -Encoding UTF8 | ConvertFrom-Json
    $sameProjectProcesses = Get-DsbServiceProcessesForStateForTest -StatePath $statePathA
    Assert-True -Condition ($sameProjectStatusA.ServiceState -eq 'running') -Message "Expected concurrent session-start calls to leave one healthy project A service."
    Assert-True -Condition ($sameProjectProcesses.Count -eq 1) -Message "Expected concurrent session-start calls to leave exactly one project A service process."
    Assert-True -Condition ($sameProjectProcesses[0].ProcessId -eq $sameProjectStateA.pid) -Message "Expected the ready-state PID to identify the only verified project A service process."

    & $controlScriptPath profile add -ProjectPath $projectA -Name reporting -DatabaseHost "127.0.0.1" -Database reporting -ConnectionDatabase postgres -DatabaseUser metadata_user -CredentialTarget "database-schema-bootstrap/test/project-a-reporting" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to add alternate project profile"
    }
    $profileUseJob = Start-Job -ScriptBlock {
        param($ScriptPath, $Path)
        $ErrorActionPreference = 'Stop'
        & $ScriptPath profile use -ProjectPath $Path -Name reporting
        if ($LASTEXITCODE -ne 0) {
            throw "profile use failed for $Path with exit code $LASTEXITCODE"
        }
    } -ArgumentList $controlScriptPath, $projectA
    Wait-DsbJobsForTest -Jobs @(
        $profileUseJob,
        (Start-DsbSessionStartJobForTest -ControlScriptPath $controlScriptPath -ProjectPath $projectA)
    )
    Write-DsbTestDiagnostic 'profile use plus session-start completed'
    $switchedStatusA = & $controlScriptPath status -ProjectPath $projectA
    $afterSwitchStatusB = & $controlScriptPath status -ProjectPath $projectB
    Assert-True -Condition ($switchedStatusA.ActiveProfile -eq 'reporting') -Message "Expected profile use to activate the requested project profile."
    Assert-True -Condition ($switchedStatusA.ServiceState -eq 'running') -Message "Expected profile use to restart only project A service."
    Assert-True -Condition ($afterSwitchStatusB.Pid -eq $projectBPid) -Message "Expected profile use to leave project B service untouched."
    $profileSwitchProcesses = Get-DsbServiceProcessesForStateForTest -StatePath $statePathA
    $reportingProfilePath = Join-Path $projectA '.agents\database-schema-bootstrap\profiles\reporting.json'
    $defaultProfilePath = Join-Path $projectA '.agents\database-schema-bootstrap\profiles\default.json'
    Assert-True -Condition ($profileSwitchProcesses.Count -eq 1) -Message "Expected profile use and session-start to leave one project A service instance."
    Assert-True -Condition ($profileSwitchProcesses[0].CommandLine.IndexOf($reportingProfilePath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) -Message "Expected the surviving project A service to use the reporting profile."
    Assert-True -Condition ($profileSwitchProcesses[0].CommandLine.IndexOf($defaultProfilePath, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) -Message "Expected no default-profile service to remain after profile use."
    Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $runtimeRoot "service\service\__pycache__"))) -Message "Expected managed service instances to avoid generating untracked bytecode in the runtime."

    & $controlScriptPath session-stop -ProjectPath $projectA
    $projectAId = Get-DsbProjectIdForTest -ProjectPath $projectA
    $missingPidState = [ordered]@{
        version = 1
        project_id = $projectAId
        project_root = (Resolve-Path -LiteralPath $projectA).ProviderPath
        endpoint = 'http://127.0.0.1:45123'
        port = 45123
        pid = 2147483647
        instance_token = 'missing-pid-token'
        started_at = [DateTime]::UtcNow.ToString('o')
    }
    Set-Content -LiteralPath $statePathA -Value ($missingPidState | ConvertTo-Json -Compress) -Encoding UTF8
    & $controlScriptPath session-start -ProjectPath $projectA
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Message "Expected session-start to recover a missing managed PID."
    $missingPidRecoveryStatus = & $controlScriptPath status -ProjectPath $projectA
    Write-DsbTestDiagnostic 'missing PID recovery completed'
    Assert-True -Condition ($missingPidRecoveryStatus.ServiceState -eq 'running') -Message "Expected missing PID recovery to start a verified replacement service."

    & $controlScriptPath session-stop -ProjectPath $projectA
    Set-Content -LiteralPath $statePathA -Value '{not-json' -Encoding UTF8
    & $controlScriptPath session-start -ProjectPath $projectA
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Message "Expected session-start to recover an invalid managed state file."
    $invalidStateRecoveryStatus = & $controlScriptPath status -ProjectPath $projectA
    Write-DsbTestDiagnostic 'invalid state recovery completed'
    Assert-True -Condition ($invalidStateRecoveryStatus.ServiceState -eq 'running') -Message "Expected invalid state recovery to start a verified replacement service."

    $safeOrphanPid = $invalidStateRecoveryStatus.Pid
    $safeOrphanState = Get-Content -LiteralPath $statePathA -Raw -Encoding UTF8 | ConvertFrom-Json
    $safeOrphanState.instance_token = 'different-state-token'
    Set-Content -LiteralPath $statePathA -Value ($safeOrphanState | ConvertTo-Json -Compress) -Encoding UTF8
    & $controlScriptPath session-stop -ProjectPath $projectA
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Message "Expected session-stop to record an ownership-mismatch orphan without terminating it."
    Assert-True -Condition ($null -ne (Get-Process -Id $safeOrphanPid -ErrorAction SilentlyContinue)) -Message "Expected automatic recovery not to terminate an unverifiable process."
    $safeReapResult = Invoke-DsbControlCommandForTest -ControlScriptPath $controlScriptPath -Arguments @('session-reap', '-ProjectPath', $projectA)
    $safeReapOutput = $safeReapResult.StdOut + $safeReapResult.StdErr
    Assert-True -Condition ($safeReapResult.ExitCode -eq 0) -Message "Expected session-reap to terminate an orphan with a fully matching identity. Output: $safeReapOutput"
    Assert-True -Condition ($safeReapOutput -match 'Reaped') -Message "Expected session-reap to report a verified orphan as Reaped. Output: $safeReapOutput"
    Assert-True -Condition ($null -eq (Get-Process -Id $safeOrphanPid -ErrorAction SilentlyContinue)) -Message "Expected verified session-reap to terminate only the matching orphan process."
    $afterSafeReapState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-True -Condition (@($afterSafeReapState.orphan_service_processes | Where-Object { $_.pid -eq $safeOrphanPid }).Count -eq 0) -Message "Expected a reaped orphan record to be removed."
    & $controlScriptPath session-start -ProjectPath $projectA
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Message "Expected session-start to start a replacement after a verified orphan reap."
    $oldUnverifiedPid = (& $controlScriptPath status -ProjectPath $projectA).Pid
    $unverifiedState = Get-Content -LiteralPath $statePathA -Raw -Encoding UTF8 | ConvertFrom-Json
    $unverifiedState.instance_token = 'different-state-token'
    Set-Content -LiteralPath $statePathA -Value ($unverifiedState | ConvertTo-Json -Compress) -Encoding UTF8
    & $controlScriptPath session-stop -ProjectPath $projectA
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Message "Expected session-stop to record an ownership-mismatch orphan without terminating it."
    Assert-True -Condition ($null -ne (Get-Process -Id $oldUnverifiedPid -ErrorAction SilentlyContinue)) -Message "Expected automatic recovery not to terminate an unverifiable process."
    $installStateAfterOrphan = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $orphanRecord = @($installStateAfterOrphan.orphan_service_processes | Where-Object { $_.pid -eq $oldUnverifiedPid })[0]
    Assert-True -Condition ($null -ne $orphanRecord) -Message "Expected ownership mismatch recovery to record the orphan process."
    foreach ($fieldName in @('pid', 'project_root', 'project_id', 'state_path', 'instance_token', 'service_script', 'command_line_sha256', 'process_creation_time_utc', 'observed_at', 'reason')) {
        Assert-True -Condition ($null -ne $orphanRecord.PSObject.Properties[$fieldName]) -Message "Expected orphan record field: $fieldName"
    }
    Assert-True -Condition ($orphanRecord.reason -eq 'ownership-mismatch') -Message "Expected orphan reason to identify the ownership mismatch."
    Write-DsbTestDiagnostic ("orphan record captured pid=" + $oldUnverifiedPid + " hash=" + $orphanRecord.command_line_sha256)
    $originalOrphanCommandLineHash = [string]$orphanRecord.command_line_sha256
    $orphanRecord.command_line_sha256 = 'tampered-command-line-hash'
    Set-Content -LiteralPath $statePath -Value ($installStateAfterOrphan | ConvertTo-Json -Depth 12) -Encoding UTF8
    $tamperedInstallState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-DsbTestDiagnostic ("orphan record tampered hash=" + (@($tamperedInstallState.orphan_service_processes | Where-Object { $_.pid -eq $oldUnverifiedPid })[0].command_line_sha256))
    $reapResult = Invoke-DsbControlCommandForTest -ControlScriptPath $controlScriptPath -Arguments @('session-reap', '-ProjectPath', $projectA)
    $reapOutput = $reapResult.StdOut + $reapResult.StdErr
    $reapExitCode = $reapResult.ExitCode
    Assert-True -Condition ($reapExitCode -ne 0) -Message "Expected session-reap to fail closed for an unverifiable orphan. Output: $reapOutput"
    Assert-True -Condition ($null -ne (Get-Process -Id $oldUnverifiedPid -ErrorAction SilentlyContinue)) -Message "Expected session-reap not to terminate an unverifiable process."
    $retainedOrphanState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-True -Condition (@($retainedOrphanState.orphan_service_processes | Where-Object { $_.pid -eq $oldUnverifiedPid }).Count -eq 1) -Message "Expected unverifiable orphan record to remain in install-state.json."
    $orphanedServicePids += $oldUnverifiedPid
    try {
        & $controlScriptPath session-start -ProjectPath $projectA
    }
    catch {
        Write-DsbTestDiagnostic ("session-start after retained orphan failed: " + $_.Exception.Message)
        foreach ($stderrPath in @(Get-ChildItem -LiteralPath (Join-Path $runtimeRoot 'logs') -Filter '*.stderr.log' -File -ErrorAction SilentlyContinue)) {
            Write-DsbTestDiagnostic ("stderr " + $stderrPath.Name + ': ' + (Get-Content -Raw -LiteralPath $stderrPath.FullName))
        }
        throw
    }
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Message "Expected session-start to continue after an unverifiable orphan reap."
    $unverifiedRecoveryStatus = & $controlScriptPath status -ProjectPath $projectA
    Assert-True -Condition ($unverifiedRecoveryStatus.ServiceState -eq 'running') -Message "Expected unverifiable orphan recovery to start a verified replacement service."
    Assert-True -Condition ($unverifiedRecoveryStatus.Pid -ne $oldUnverifiedPid) -Message "Expected unverifiable orphan recovery to leave the old PID behind and start a new instance."
    Assert-True -Condition ($null -ne (Get-Process -Id $oldUnverifiedPid -ErrorAction SilentlyContinue)) -Message "Expected session-start not to terminate an unverifiable orphan."
    $retainedAfterStart = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-True -Condition (@($retainedAfterStart.orphan_service_processes | Where-Object { $_.pid -eq $oldUnverifiedPid }).Count -eq 1) -Message "Expected session-start to retain an unverifiable orphan record."
    Write-DsbTestDiagnostic 'unverifiable process recovery completed'

    # Exercise the legacy-record compatibility path: an orphan record from
    # before instance_token existed must not remove the replacement instance's
    # service registration when both instances reused the same state path.
    $replacementState = Get-Content -LiteralPath $statePathA -Raw -Encoding UTF8 | ConvertFrom-Json
    $legacyInstallState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $legacyOrphanRecord = @($legacyInstallState.orphan_service_processes | Where-Object { $_.pid -eq $oldUnverifiedPid })[0]
    Assert-True -Condition ($null -ne $legacyOrphanRecord) -Message "Expected the retained orphan record before legacy identity cleanup."
    $legacyOrphanRecord.command_line_sha256 = $originalOrphanCommandLineHash
    if ($null -ne $legacyOrphanRecord.PSObject.Properties['instance_token']) {
        $legacyOrphanRecord.PSObject.Properties.Remove('instance_token')
    }
    Set-Content -LiteralPath $statePath -Value ($legacyInstallState | ConvertTo-Json -Depth 12) -Encoding UTF8
    Stop-DsbOrphanedServicesForTest -ProcessIds @($oldUnverifiedPid)
    $orphanedServicePids = @()
    $legacyReapResult = Invoke-DsbControlCommandForTest -ControlScriptPath $controlScriptPath -Arguments @('session-reap', '-ProjectPath', $projectA)
    $legacyReapOutput = $legacyReapResult.StdOut + $legacyReapResult.StdErr
    Assert-True -Condition ($legacyReapResult.ExitCode -eq 0) -Message "Expected legacy orphan cleanup to succeed after the old process exited. Output: $legacyReapOutput"
    $legacyReapedState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $replacementStatePath = [System.IO.Path]::GetFullPath($statePathA).ToLowerInvariant()
    $replacementRegistrations = @($legacyReapedState.service_state_files | Where-Object {
        $_.path -eq $replacementStatePath -and $_.instance_token -eq $replacementState.instance_token
    })
    Assert-True -Condition ($replacementRegistrations.Count -eq 1) -Message "Expected stale legacy orphan cleanup to preserve the replacement service registration."
    Assert-True -Condition ($null -ne (Get-Process -Id $replacementState.pid -ErrorAction SilentlyContinue)) -Message "Expected stale legacy orphan cleanup to leave the replacement service running."

    & $controlScriptPath session-stop -ProjectPath $projectA
    $coreUninstallResult = Invoke-DsbControlCommandForTest -ControlScriptPath (Join-Path $toolRoot "uninstall.ps1") -Arguments @('-CodexHome', $codexHome, '-Categories', 'state', '-ConfirmAll')
    $coreUninstallOutput = $coreUninstallResult.StdOut + $coreUninstallResult.StdErr
    $coreUninstallExitCode = $coreUninstallResult.ExitCode
    Assert-True -Condition ($coreUninstallExitCode -ne 0) -Message "Expected destructive core uninstall to stop on an unverifiable orphan. Output: $coreUninstallOutput"
    Assert-True -Condition (Test-Path -LiteralPath $statePath -PathType Leaf) -Message "Expected blocked orphan cleanup to preserve installation state."
    Stop-DsbOrphanedServicesForTest -ProcessIds @($oldUnverifiedPid)
    & $controlScriptPath session-reap -ProjectPath $projectA
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Message "Expected session-reap to remove a stale orphan record after its PID disappeared."
    $staleReapedState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-True -Condition (@($staleReapedState.orphan_service_processes | Where-Object { $_.pid -eq $oldUnverifiedPid }).Count -eq 0) -Message "Expected stale orphan record to be removed."
    $orphanedServicePids = @()
    & $controlScriptPath session-stop -ProjectPath $projectB
    $hookCwdResult = Invoke-DsbHookSessionStartForTest -ControlScriptPath $controlScriptPath -WorkingDirectory $projectA -HookEventJson (@{ cwd = $projectB } | ConvertTo-Json -Compress)
    Write-DsbTestDiagnostic 'hook cwd child process returned'
    Assert-True -Condition ($hookCwdResult.ExitCode -eq 0) -Message "Expected hook stdin cwd to start the selected project service. $($hookCwdResult.StdErr)"
    $hookCwdStatusA = & $controlScriptPath status -ProjectPath $projectA
    $hookCwdStatusB = & $controlScriptPath status -ProjectPath $projectB
    Assert-True -Condition ($hookCwdStatusA.ServiceState -eq 'stopped') -Message "Expected hook cwd routing not to start the caller's current project."
    Assert-True -Condition ($hookCwdStatusB.ServiceState -eq 'running') -Message "Expected hook cwd routing to start the event project."

    & $controlScriptPath session-stop -ProjectPath $projectA
    & $controlScriptPath session-stop -ProjectPath $projectB
    $explicitPathResult = Invoke-DsbHookSessionStartForTest -ControlScriptPath $controlScriptPath -WorkingDirectory $projectA -HookEventJson (@{ cwd = $projectA } | ConvertTo-Json -Compress) -ExplicitProjectPath $projectB
    Write-DsbTestDiagnostic 'explicit ProjectPath hook child process returned'
    Assert-True -Condition ($explicitPathResult.ExitCode -eq 0) -Message "Expected explicit ProjectPath to override hook cwd. $($explicitPathResult.StdErr)"
    $explicitPathStatusA = & $controlScriptPath status -ProjectPath $projectA
    $explicitPathStatusB = & $controlScriptPath status -ProjectPath $projectB
    Assert-True -Condition ($explicitPathStatusA.ServiceState -eq 'stopped') -Message "Expected explicit ProjectPath to take priority over hook cwd."
    Assert-True -Condition ($explicitPathStatusB.ServiceState -eq 'running') -Message "Expected explicit ProjectPath to start project B."

    & $controlScriptPath session-stop -ProjectPath $projectA
    & $controlScriptPath session-stop -ProjectPath $projectB
    $invalidHookResult = Invoke-DsbHookSessionStartForTest -ControlScriptPath $controlScriptPath -WorkingDirectory $projectA -HookEventJson (@{ cwd = (Join-Path $tempRoot 'missing-project') } | ConvertTo-Json -Compress)
    Write-DsbTestDiagnostic 'invalid hook cwd child process returned'
    Assert-True -Condition ($invalidHookResult.ExitCode -ne 0) -Message "Expected nonempty invalid hook cwd to fail closed."
    $invalidHookStatusA = & $controlScriptPath status -ProjectPath $projectA
    Assert-True -Condition ($invalidHookStatusA.ServiceState -eq 'stopped') -Message "Expected invalid hook cwd not to fall back to the caller project."

    Push-Location -LiteralPath $projectB
    try {
        & $controlScriptPath session-start
        Assert-True -Condition ($LASTEXITCODE -eq 0) -Message "Expected manual session-start without stdin to use the current directory."
    }
    finally {
        Pop-Location
    }
    $manualCwdStatusB = & $controlScriptPath status -ProjectPath $projectB
    Write-DsbTestDiagnostic 'manual current-directory session-start completed'
    Assert-True -Condition ($manualCwdStatusB.ServiceState -eq 'running') -Message "Expected manual session-start to remain compatible with the current directory."
    Stop-DsbOrphanedServicesForTest -ProcessIds $orphanedServicePids
    $orphanedServicePids = @()
    $unrecordedProfilePath = Join-Path $projectA ".agents\database-schema-bootstrap\profiles\manual.json"
    Set-Content -LiteralPath $unrecordedProfilePath -Value '{"db_type":"postgres"}' -Encoding UTF8

    & $controlScriptPath session-stop -ProjectPath $projectA
    & $controlScriptPath session-stop -ProjectPath $projectB

    $stateOnlyResult = Invoke-DsbControlCommandForTest -ControlScriptPath (Join-Path $toolRoot "uninstall.ps1") -Arguments @('-CodexHome', $codexHome, '-Categories', 'state', '-ConfirmAll')
    $stateOnlyOutput = $stateOnlyResult.StdOut + $stateOnlyResult.StdErr
    Assert-True -Condition ($stateOnlyResult.ExitCode -eq 0) -Message "Expected state-only cleanup to succeed without orphan records. Output: $stateOnlyOutput"
    Assert-True -Condition (Test-Path -LiteralPath $runtimeRoot -PathType Container) -Message "Expected state-only cleanup to preserve the runtime."
    Assert-True -Condition (Test-Path -LiteralPath $statePath -PathType Leaf) -Message "Expected state-only cleanup to preserve install-state.json."
    Assert-True -Condition (Test-Path -LiteralPath $configPath -PathType Leaf) -Message "Expected state-only cleanup to preserve Codex configuration."
    Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $runtimeRoot 'state\install-state.lock') -PathType Leaf)) -Message "Expected state-only cleanup to remove the global install-state lock."

    $repairCodexHome = Join-Path $tempRoot 'repair\.codex'
    New-Item -ItemType Directory -Path $repairCodexHome -Force | Out-Null
    $repairConfigPath = Join-Path $repairCodexHome 'config.toml'
    Set-Content -LiteralPath $repairConfigPath -Value 'model = "repair-test"' -Encoding UTF8
    & $installScriptPath -PythonPath $env:CODEX_PYTHON -CodexHome $repairCodexHome -SkipDependencyInstall | Out-Null
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Message "Expected isolated Repair fixture installation to succeed."
    $repairRuntimeRoot = Join-Path $repairCodexHome 'database-schema-bootstrap'
    $repairStatePath = Join-Path $repairRuntimeRoot 'install-state.json'
    Remove-Item -LiteralPath $repairStatePath -Force
    $repairBlockedResult = Invoke-DsbControlCommandForTest -ControlScriptPath (Join-Path $toolRoot "uninstall.ps1") -Arguments @('-CodexHome', $repairCodexHome, '-Repair', '-ConfirmAll')
    $repairBlockedOutput = $repairBlockedResult.StdOut + $repairBlockedResult.StdErr
    Assert-True -Condition ($repairBlockedResult.ExitCode -ne 0) -Message "Expected Repair to stop when runtime artifacts remain without state. Output: $repairBlockedOutput"
    Assert-True -Condition (Test-Path -LiteralPath $repairRuntimeRoot -PathType Container) -Message "Expected blocked Repair to preserve runtime artifacts."
    Assert-True -Condition ((Get-Content -LiteralPath $repairConfigPath -Raw -Encoding UTF8) -match '\[mcp_servers\.database-schema-bootstrap\]') -Message "Expected blocked Repair to preserve the managed configuration block."
    Remove-Item -LiteralPath $repairRuntimeRoot -Recurse -Force
    $repairResult = Invoke-DsbControlCommandForTest -ControlScriptPath (Join-Path $toolRoot "uninstall.ps1") -Arguments @('-CodexHome', $repairCodexHome, '-Repair', '-ConfirmAll')
    $repairOutput = $repairResult.StdOut + $repairResult.StdErr
    Assert-True -Condition ($repairResult.ExitCode -eq 0) -Message "Expected Repair to remove only the orphaned managed configuration block. Output: $repairOutput"
    $repairedConfig = Get-Content -LiteralPath $repairConfigPath -Raw -Encoding UTF8
    Assert-True -Condition ($repairedConfig -notmatch '\[mcp_servers\.database-schema-bootstrap\]') -Message "Expected Repair to remove the managed configuration block."
    Assert-True -Condition ($repairedConfig -match [regex]::Escape('model = "repair-test"')) -Message "Expected Repair to preserve unrelated configuration."

    $tamperedConfig = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8
    $tamperedConfig = $tamperedConfig.Replace('tool_timeout_sec = 30', 'tool_timeout_sec = 77')
    Set-Content -LiteralPath $configPath -Value $tamperedConfig -Encoding UTF8
    $uninstallScriptPath = Join-Path $toolRoot "uninstall.ps1"
    $stateOnlyAfterTamperResult = Invoke-DsbControlCommandForTest -ControlScriptPath $uninstallScriptPath -Arguments @('-CodexHome', $codexHome, '-Categories', 'state', '-ConfirmAll')
    $stateOnlyAfterTamperOutput = $stateOnlyAfterTamperResult.StdOut + $stateOnlyAfterTamperResult.StdErr
    Assert-True -Condition ($stateOnlyAfterTamperResult.ExitCode -eq 0) -Message "State-only cleanup must not be blocked by an edited config it does not delete. Output: $stateOnlyAfterTamperOutput"
    Assert-True -Condition ((Get-Content -LiteralPath $configPath -Raw -Encoding UTF8) -match 'tool_timeout_sec = 77') -Message "State-only cleanup must preserve an edited managed configuration."
    Assert-True -Condition (Test-Path -LiteralPath $runtimeRoot -PathType Container) -Message "State-only cleanup after config tampering must preserve the runtime."
    Assert-True -Condition (Test-Path -LiteralPath $statePath -PathType Leaf) -Message "State-only cleanup after config tampering must preserve install-state.json."
    $ordinaryUninstallResult = Invoke-DsbControlCommandForTest -ControlScriptPath $uninstallScriptPath -Arguments @('-CodexHome', $codexHome, '-Categories', 'config', '-ConfirmAll')
    $ordinaryUninstallOutput = $ordinaryUninstallResult.StdOut + $ordinaryUninstallResult.StdErr
    $ordinaryUninstallExitCode = $ordinaryUninstallResult.ExitCode
    Assert-True -Condition ($ordinaryUninstallExitCode -ne 0) -Message "Ordinary core uninstall must abort when the managed configuration was modified. Output: $ordinaryUninstallOutput"
    Assert-True -Condition ($ordinaryUninstallOutput -match 'expanded to: config,runtime,state') -Message "Expected config-only core uninstall to report its automatic category expansion."
    $preservedConfig = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8
    Assert-True -Condition ($preservedConfig -match 'tool_timeout_sec = 77') -Message "Expected blocked core uninstall to preserve edited managed configuration."
    Assert-True -Condition (Test-Path -LiteralPath $runtimeRoot -PathType Container) -Message "Expected blocked core uninstall to preserve the runtime."
    Assert-True -Condition (Test-Path -LiteralPath $statePath -PathType Leaf) -Message "Expected blocked core uninstall to preserve installation state."

    & $controlScriptPath session-start -ProjectPath $projectA
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Message "Expected credential failure fixture to start a managed service."
    $credentialFailureStatus = & $controlScriptPath status -ProjectPath $projectA
    $credentialFailurePid = [int]$credentialFailureStatus.Pid
    $credentialFailureConfig = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8
    $credentialFailureProfilePath = Join-Path $projectA '.agents\database-schema-bootstrap\profiles\reporting.json'
    $credentialFailureRuntimePath = Join-Path $runtimeRoot 'service\server.py'
    $credentialFailureState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $invalidCredentialTarget = 'database-schema-bootstrap/' + ('x' * 40000)
    $credentialFailureState.credential_targets = @($credentialFailureState.credential_targets) + @([pscustomobject]@{
        target = $invalidCredentialTarget
        project_root = (Resolve-Path -LiteralPath $projectA).ProviderPath
        project_id = $projectAId
        profile = 'reporting'
        created_at = [DateTime]::UtcNow.ToString('o')
    })
    Set-Content -LiteralPath $statePath -Value ($credentialFailureState | ConvertTo-Json -Depth 12) -Encoding UTF8
    $credentialFailureResult = Invoke-DsbControlCommandForTest -ControlScriptPath $uninstallScriptPath -Arguments @('-CodexHome', $codexHome, '-All', '-ConfirmAll', '-ForceManaged', '-ConfirmForceManaged')
    $credentialFailureOutput = $credentialFailureResult.StdOut + $credentialFailureResult.StdErr
    Assert-True -Condition ($credentialFailureResult.ExitCode -ne 0) -Message "Expected uninstall to stop on a credential deletion failure. Output: $credentialFailureOutput"
    Assert-True -Condition (Test-Path -LiteralPath $configPath -PathType Leaf) -Message "Credential deletion failure must preserve the managed configuration file."
    Assert-True -Condition ((Get-Content -LiteralPath $configPath -Raw -Encoding UTF8) -eq $credentialFailureConfig) -Message "Credential deletion failure must not modify the configuration."
    Assert-True -Condition (Test-Path -LiteralPath $credentialFailureRuntimePath -PathType Leaf) -Message "Credential deletion failure must preserve runtime files."
    Assert-True -Condition (Test-Path -LiteralPath $credentialFailureProfilePath -PathType Leaf) -Message "Credential deletion failure must preserve managed profiles."
    Assert-True -Condition (Test-Path -LiteralPath $statePath -PathType Leaf) -Message "Credential deletion failure must preserve install-state.json."
    Assert-True -Condition ($null -ne (Get-Process -Id $credentialFailurePid -ErrorAction SilentlyContinue)) -Message "Credential deletion failure must not stop managed services."
    $credentialFailureStateAfter = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-True -Condition (@($credentialFailureStateAfter.credential_targets | Where-Object { $_.target -eq $invalidCredentialTarget }).Count -eq 1) -Message "Credential deletion failure must retain the credential record for retry."
    & $controlScriptPath session-stop -ProjectPath $projectA
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Message "Expected credential failure fixture cleanup to stop the managed service."
    $credentialFailureStateAfter.credential_targets = @($credentialFailureStateAfter.credential_targets | Where-Object { $_.target -ne $invalidCredentialTarget })
    Set-Content -LiteralPath $statePath -Value ($credentialFailureStateAfter | ConvertTo-Json -Depth 12) -Encoding UTF8

    & $uninstallScriptPath -CodexHome $codexHome -All -ConfirmAll -ForceManaged -ConfirmForceManaged
    if ($LASTEXITCODE -ne 0) {
        throw "Forced full uninstall exited with code $LASTEXITCODE"
    }
    if (Test-Path -LiteralPath $runtimeRoot) {
        $remainingRuntimeItems = @(Get-ChildItem -LiteralPath $runtimeRoot -Force -Recurse -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }) -join '; '
        Write-DsbTestDiagnostic ("runtime remained after forced uninstall: " + $remainingRuntimeItems)
    }
    Assert-True -Condition (-not (Test-Path -LiteralPath $runtimeRoot)) -Message "Expected full uninstall to remove the verified runtime."
    Assert-True -Condition (Test-Path -LiteralPath $unrecordedProfilePath -PathType Leaf) -Message "Expected full uninstall to preserve an unrecorded project profile."
    $uninstalledConfig = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8
    Assert-True -Condition ($uninstalledConfig -notmatch '\[mcp_servers\.database-schema-bootstrap\]') -Message "Expected forced full uninstall to remove only the managed configuration block."
    Assert-True -Condition ($uninstalledConfig -match [regex]::Escape('model = "gpt-test"')) -Message "Expected uninstall to preserve unrelated Codex configuration."
}
finally {
    if ($null -ne $controlScriptPath -and (Test-Path -LiteralPath $controlScriptPath -PathType Leaf)) {
        foreach ($projectPath in @($projectA, $projectB)) {
            if ($null -ne $projectPath -and (Test-Path -LiteralPath $projectPath -PathType Container)) {
                & $controlScriptPath session-stop -ProjectPath $projectPath 2>$null
            }
        }
    }
    Stop-DsbOrphanedServicesForTest -ProcessIds $orphanedServicePids
    if (Test-Path -LiteralPath $tempRoot) {
        try {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force
        }
        catch {
            Write-Warning "Temporary test cleanup deferred: $($_.Exception.Message)"
        }
    }
}
