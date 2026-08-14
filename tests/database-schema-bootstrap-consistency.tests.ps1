Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Invoke-DsbUninstallForTest {
    param(
        [Parameter(Mandatory)]
        [string]$UninstallScriptPath,

        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $UninstallScriptPath -RuntimeRoot $RuntimeRoot @Arguments 2>&1
        return [pscustomobject]@{
            ExitCode = $LASTEXITCODE
            Output = ($output | Out-String)
        }
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).ProviderPath
$modulePath = Join-Path $repoRoot 'tools\database-schema-bootstrap\DbSchemaBootstrap.Common.psm1'
$uninstallScriptPath = Join-Path $repoRoot 'tools\database-schema-bootstrap\uninstall.ps1'
Import-Module $modulePath -Force

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('database-schema-bootstrap-consistency-' + [Guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

    # A stale legacy orphan must not remove a replacement registration that
    # reused the same state path.
    $identityRuntimeRoot = Join-Path $tempRoot 'identity-runtime'
    $identityStateDirectory = Join-Path $identityRuntimeRoot 'state\projects'
    New-Item -ItemType Directory -Path $identityStateDirectory -Force | Out-Null
    $identityProjectRoot = Join-Path $tempRoot 'identity-project'
    New-Item -ItemType Directory -Path $identityProjectRoot -Force | Out-Null
    $identityProjectId = Get-DsbProjectId -ProjectRoot $identityProjectRoot
    $identityStatePath = Get-DsbServiceStatePath -RuntimeRoot $identityRuntimeRoot -ProjectId $identityProjectId
    $replacementServiceState = [ordered]@{
        version = 1
        project_id = $identityProjectId
        project_root = (Get-DsbNormalizedPath -Path $identityProjectRoot)
        endpoint = 'http://127.0.0.1:45101'
        port = 45101
        pid = 2147483647
        instance_token = 'replacement-instance-token'
        started_at = [DateTime]::UtcNow.ToString('o')
    }
    Write-DsbJsonFile -Path $identityStatePath -Value $replacementServiceState
    $identityStateRecord = [pscustomobject]@{
        path = (Get-DsbNormalizedPath -Path $identityStatePath)
        sha256 = Get-DsbSha256File -Path $identityStatePath
        project_root = (Get-DsbNormalizedPath -Path $identityProjectRoot)
        project_id = $identityProjectId
        instance_token = 'replacement-instance-token'
    }
    $identityInstallState = [ordered]@{
        version = 1
        runtime_root = (Get-DsbNormalizedPath -Path $identityRuntimeRoot)
        service_state_files = @($identityStateRecord)
        orphan_service_processes = @([pscustomobject]@{
            pid = 2147483647
            project_root = (Get-DsbNormalizedPath -Path $identityProjectRoot)
            project_id = $identityProjectId
            state_path = (Get-DsbNormalizedPath -Path $identityStatePath)
            service_script = (Get-DsbNormalizedPath -Path (Join-Path $identityRuntimeRoot 'service\server.py'))
            command_line_sha256 = 'legacy-record-hash'
            process_creation_time_utc = [DateTime]::UtcNow.ToString('o')
            observed_at = [DateTime]::UtcNow.ToString('o')
            reason = 'legacy-orphan'
        })
    }
    Save-DsbInstallState -RuntimeRoot $identityRuntimeRoot -State $identityInstallState
    $identityReapResults = @(Reap-DsbOrphanServiceProcesses -RuntimeRoot $identityRuntimeRoot -ProjectId $identityProjectId)
    $identityAfterState = Get-DsbInstallState -RuntimeRoot $identityRuntimeRoot -Required
    Assert-True -Condition (@($identityReapResults | Where-Object { $_.Status -eq 'Stale' }).Count -eq 1) -Message 'Expected the legacy orphan PID to be classified as stale.'
    Assert-True -Condition (@($identityAfterState.orphan_service_processes).Count -eq 0) -Message 'Expected the stale legacy orphan record to be removed.'
    $identityRegistrations = @($identityAfterState.service_state_files | Where-Object {
        $_.path -eq (Get-DsbNormalizedPath -Path $identityStatePath) -and $_.instance_token -eq 'replacement-instance-token'
    })
    Assert-True -Condition ($identityRegistrations.Count -eq 1) -Message 'Expected stale legacy orphan cleanup to preserve the replacement service registration.'

    # A state-only cleanup with no project services still has to remove the
    # global lock, while retaining install-state.json and the runtime.
    $lockRuntimeRoot = Join-Path $tempRoot 'lock-runtime'
    New-Item -ItemType Directory -Path (Join-Path $lockRuntimeRoot 'state') -Force | Out-Null
    $lockInstallState = [ordered]@{
        version = 1
        installation_id = ([Guid]::NewGuid().ToString())
        runtime_root = (Get-DsbNormalizedPath -Path $lockRuntimeRoot)
        config_path = (Get-DsbNormalizedPath -Path (Join-Path $tempRoot 'lock-config.toml'))
        config_block_hash = 'not-used-by-state-only-test'
        managed_files = @()
        managed_profiles = @()
        managed_active_profiles = @()
        credential_targets = @()
        service_state_files = @()
        orphan_service_processes = @()
        log_directory = (Get-DsbNormalizedPath -Path (Join-Path $lockRuntimeRoot 'logs'))
    }
    Save-DsbInstallState -RuntimeRoot $lockRuntimeRoot -State $lockInstallState
    $lockPath = Join-Path $lockRuntimeRoot 'state\install-state.lock'
    Set-Content -LiteralPath $lockPath -Value '' -Encoding UTF8
    $stateOnlyResult = Invoke-DsbUninstallForTest -UninstallScriptPath $uninstallScriptPath -RuntimeRoot $lockRuntimeRoot -Arguments @('-Categories', 'state', '-ConfirmAll')
    Assert-True -Condition ($stateOnlyResult.ExitCode -eq 0) -Message "Expected state-only cleanup to succeed. Output: $($stateOnlyResult.Output)"
    Assert-True -Condition (-not (Test-Path -LiteralPath $lockPath -PathType Leaf)) -Message 'Expected state-only cleanup to remove install-state.lock.'
    Assert-True -Condition (Test-Path -LiteralPath (Get-DsbInstallStatePath -RuntimeRoot $lockRuntimeRoot) -PathType Leaf) -Message 'Expected state-only cleanup to preserve install-state.json.'
    Assert-True -Condition (Test-Path -LiteralPath $lockRuntimeRoot -PathType Container) -Message 'Expected state-only cleanup to preserve the runtime root.'

    # A non-ERROR_NOT_FOUND credential failure must happen before any managed
    # file or service cleanup. A target exceeding the Windows API limit gives a
    # deterministic Win32 failure without storing a plaintext secret.
    $credentialRuntimeRoot = Join-Path $tempRoot 'credential-runtime'
    $credentialStateDirectory = Join-Path $credentialRuntimeRoot 'state'
    $credentialServiceDirectory = Join-Path $credentialRuntimeRoot 'service'
    New-Item -ItemType Directory -Path $credentialStateDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path $credentialServiceDirectory -Force | Out-Null
    $credentialProjectRoot = Join-Path $tempRoot 'credential-project'
    $credentialProfileDirectory = Join-Path $credentialProjectRoot '.agents\database-schema-bootstrap\profiles'
    New-Item -ItemType Directory -Path $credentialProfileDirectory -Force | Out-Null
    $credentialProfilePath = Join-Path $credentialProfileDirectory 'default.json'
    Set-Content -LiteralPath $credentialProfilePath -Value '{"db_type":"postgres"}' -Encoding UTF8
    $credentialRuntimeFile = Join-Path $credentialServiceDirectory 'server.py'
    Set-Content -LiteralPath $credentialRuntimeFile -Value 'managed-runtime-fixture' -Encoding UTF8
    $credentialConfigPath = Join-Path $tempRoot 'config.toml'
    $credentialInstallationId = [Guid]::NewGuid().ToString()
    $credentialBlock = New-DsbManagedConfigBlock -InstallationId $credentialInstallationId -PythonPath 'C:\Python\python.exe' -RuntimeRoot $credentialRuntimeRoot
    $credentialConfigContent = @('model = "credential-test"', $credentialBlock) -join [Environment]::NewLine
    Write-DsbAtomicUtf8File -Path $credentialConfigPath -Content $credentialConfigContent
    $credentialConfigInfo = Get-DsbManagedConfigBlockInfo -ConfigPath $credentialConfigPath
    $credentialProjectId = Get-DsbProjectId -ProjectRoot $credentialProjectRoot
    $invalidCredentialTarget = 'database-schema-bootstrap/' + ('x' * 40000)
    $credentialInstallState = [ordered]@{
        version = 1
        installation_id = $credentialInstallationId
        runtime_root = (Get-DsbNormalizedPath -Path $credentialRuntimeRoot)
        config_path = (Get-DsbNormalizedPath -Path $credentialConfigPath)
        config_block_hash = Get-DsbSha256String -Value $credentialConfigInfo.Block
        managed_files = @([pscustomobject]@{
            path = (Get-DsbNormalizedPath -Path $credentialRuntimeFile)
            sha256 = Get-DsbSha256File -Path $credentialRuntimeFile
        })
        managed_profiles = @([pscustomobject]@{
            path = (Get-DsbNormalizedPath -Path $credentialProfilePath)
            sha256 = Get-DsbSha256File -Path $credentialProfilePath
            project_root = (Get-DsbNormalizedPath -Path $credentialProjectRoot)
            project_id = $credentialProjectId
            name = 'default'
        })
        managed_active_profiles = @()
        credential_targets = @([pscustomobject]@{
            target = $invalidCredentialTarget
            project_root = (Get-DsbNormalizedPath -Path $credentialProjectRoot)
            project_id = $credentialProjectId
            profile = 'default'
            created_at = [DateTime]::UtcNow.ToString('o')
        })
        service_state_files = @()
        orphan_service_processes = @()
        log_directory = (Get-DsbNormalizedPath -Path (Join-Path $credentialRuntimeRoot 'logs'))
    }
    Save-DsbInstallState -RuntimeRoot $credentialRuntimeRoot -State $credentialInstallState
    $credentialFailureResult = Invoke-DsbUninstallForTest -UninstallScriptPath $uninstallScriptPath -RuntimeRoot $credentialRuntimeRoot -Arguments @('-All', '-ConfirmAll', '-ForceManaged', '-ConfirmForceManaged')
    Assert-True -Condition ($credentialFailureResult.ExitCode -ne 0) -Message 'Expected uninstall to stop on a non-ERROR_NOT_FOUND credential deletion failure.'
    Assert-True -Condition (Test-Path -LiteralPath $credentialConfigPath -PathType Leaf) -Message 'Credential failure must preserve the managed configuration.'
    Assert-True -Condition ((Get-Content -LiteralPath $credentialConfigPath -Raw -Encoding UTF8) -eq $credentialConfigContent) -Message 'Credential failure must not modify the configuration.'
    Assert-True -Condition (Test-Path -LiteralPath $credentialRuntimeFile -PathType Leaf) -Message 'Credential failure must preserve runtime files.'
    Assert-True -Condition (Test-Path -LiteralPath $credentialProfilePath -PathType Leaf) -Message 'Credential failure must preserve managed profiles.'
    Assert-True -Condition (Test-Path -LiteralPath (Get-DsbInstallStatePath -RuntimeRoot $credentialRuntimeRoot) -PathType Leaf) -Message 'Credential failure must preserve install-state.json.'

    # ERROR_NOT_FOUND remains an idempotent success for a retry.
    $missingCredentialTarget = 'database-schema-bootstrap/missing-' + [Guid]::NewGuid().ToString('N')
    Remove-DsbWindowsCredential -Target $missingCredentialTarget
    Remove-DsbWindowsCredential -Target $missingCredentialTarget
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
