[CmdletBinding()]
param(
    [string]$PythonPath,

    [string]$CodexHome,

    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Import-Module (Join-Path $PSScriptRoot 'DbSchemaBootstrap.Common.psm1') -Force

function Copy-DsbRuntimePart {
    param(
        [Parameter(Mandatory)]
        [string]$DestinationRoot,

        [Parameter(Mandatory)]
        [string]$PartName,

        [Parameter(Mandatory)]
        [string[]]$SourceFiles,

        [Parameter(Mandatory)]
        [string]$SourceBase
    )

    $destination = Join-Path $DestinationRoot $PartName
    $staging = Join-Path $DestinationRoot ('.{0}.{1}.staging' -f $PartName, [Guid]::NewGuid().ToString('N'))
    $backup = Join-Path $DestinationRoot ('.{0}.{1}.backup' -f $PartName, [Guid]::NewGuid().ToString('N'))
    [System.IO.Directory]::CreateDirectory($staging) | Out-Null
    try {
        foreach ($relativePath in $SourceFiles) {
            $sourcePath = Join-Path $SourceBase $relativePath
            if (-not (Test-Path -LiteralPath $sourcePath)) {
                throw "Required source file is missing: $sourcePath"
            }
            $targetPath = Join-Path $staging $relativePath
            if (Test-Path -LiteralPath $sourcePath -PathType Container) {
                foreach ($sourceFile in @(Get-ChildItem -LiteralPath $sourcePath -File -Recurse | Where-Object {
                    $_.Extension -ne '.pyc' -and $_.DirectoryName -notmatch '(?i)(^|\\)__pycache__(\\|$)'
                })) {
                    $relativeChildPath = $sourceFile.FullName.Substring($sourcePath.Length).TrimStart([char[]]@('\', '/'))
                    $targetFilePath = Join-Path $targetPath $relativeChildPath
                    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($targetFilePath)) | Out-Null
                    Copy-Item -LiteralPath $sourceFile.FullName -Destination $targetFilePath -Force
                }
            }
            else {
                [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($targetPath)) | Out-Null
                Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force
            }
        }
        if (Test-Path -LiteralPath $destination) {
            Move-Item -LiteralPath $destination -Destination $backup -Force
        }
        Move-Item -LiteralPath $staging -Destination $destination -Force
        if (Test-Path -LiteralPath $backup) {
            Remove-Item -LiteralPath $backup -Recurse -Force
        }
    }
    catch {
        if (-not (Test-Path -LiteralPath $destination) -and (Test-Path -LiteralPath $backup)) {
            Move-Item -LiteralPath $backup -Destination $destination -Force
        }
        throw
    }
    finally {
        if (Test-Path -LiteralPath $staging) {
            Remove-Item -LiteralPath $staging -Recurse -Force
        }
        if (Test-Path -LiteralPath $backup) {
            Remove-Item -LiteralPath $backup -Recurse -Force
        }
    }
}

function Get-DsbRuntimeFileManifest {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot
    )

    $parts = @('adapter', 'service', 'control')
    $files = foreach ($part in $parts) {
        $partPath = Join-Path $RuntimeRoot $part
        if (Test-Path -LiteralPath $partPath -PathType Container) {
            Get-ChildItem -LiteralPath $partPath -File -Recurse | ForEach-Object {
                [pscustomobject]@{
                    path = (Get-DsbNormalizedPath -Path $_.FullName)
                    sha256 = (Get-DsbSha256File -Path $_.FullName)
                }
            }
        }
    }
    return @($files | Sort-Object path)
}

function Assert-DsbExistingInstallation {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ConfigPath
    )

    $state = Get-DsbInstallState -RuntimeRoot $RuntimeRoot
    $configInfo = Get-DsbManagedConfigBlockInfo -ConfigPath $ConfigPath
    if ($null -eq $state) {
        if ($configInfo.Present) {
            throw 'A managed Codex configuration block exists without installation state; refusing to take ownership.'
        }
        foreach ($part in @('adapter', 'service', 'control')) {
            if (Test-Path -LiteralPath (Join-Path $RuntimeRoot $part)) {
                throw 'Runtime files exist without installation state; refusing to overwrite them.'
            }
        }
        return $null
    }

    $installationId = Get-DsbObjectProperty -Object $state -Name 'installation_id'
    $recordedRoot = Get-DsbObjectProperty -Object $state -Name 'runtime_root'
    $recordedHash = Get-DsbObjectProperty -Object $state -Name 'config_block_hash'
    if ($installationId -isnot [string] -or $installationId -notmatch '^[0-9a-fA-F-]{36}$' -or $recordedRoot -isnot [string] -or $recordedHash -isnot [string]) {
        throw 'Installation state is invalid; refusing to overwrite managed files.'
    }
    if ((Get-DsbNormalizedPath -Path $recordedRoot) -ne (Get-DsbNormalizedPath -Path $RuntimeRoot)) {
        throw 'Installation state points to a different runtime root; refusing to overwrite files.'
    }
    if (-not $configInfo.Present -or $configInfo.InstallationId -ne $installationId.ToLowerInvariant()) {
        throw 'Installation state and managed Codex configuration block do not match.'
    }
    if ((Get-DsbSha256String -Value $configInfo.Block) -ne $recordedHash) {
        throw 'The managed Codex configuration block was edited; refusing to overwrite it.'
    }
    foreach ($record in @((Get-DsbObjectProperty -Object $state -Name 'managed_files' -Default @()))) {
        $path = Get-DsbObjectProperty -Object $record -Name 'path'
        $hash = Get-DsbObjectProperty -Object $record -Name 'sha256'
        if ($path -is [string] -and $hash -is [string] -and (Test-Path -LiteralPath $path -PathType Leaf) -and (Get-DsbSha256File -Path $path) -ne $hash) {
            throw "A managed runtime file was edited: $path"
        }
    }
    return $state
}

function Get-DsbUpgradeServiceProjects {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [AllowNull()]
        [object]$State
    )

    $stateDirectory = Join-Path $RuntimeRoot 'state'
    $projects = @{}
    foreach ($record in @((Get-DsbObjectProperty -Object $State -Name 'service_state_files' -Default @()))) {
        $statePath = Get-DsbObjectProperty -Object $record -Name 'path'
        $projectRoot = Get-DsbObjectProperty -Object $record -Name 'project_root'
        $projectId = Get-DsbObjectProperty -Object $record -Name 'project_id'
        if ($statePath -isnot [string] -or $projectRoot -isnot [string] -or $projectId -isnot [string]) {
            throw 'Installation state contains an invalid service ownership record; refusing to replace the runtime.'
        }
        try {
            $validStatePath = Test-DsbPathWithin -Path $statePath -ParentPath $stateDirectory
            $expectedProjectId = Get-DsbProjectId -ProjectRoot $projectRoot
            $expectedStatePath = Get-DsbServiceStatePath -RuntimeRoot $RuntimeRoot -ProjectId $expectedProjectId
        }
        catch {
            throw "Installation state contains an invalid service ownership record for project: $projectRoot"
        }
        if (-not $validStatePath -or $expectedProjectId -ne $projectId -or (Get-DsbNormalizedPath -Path $expectedStatePath) -ne (Get-DsbNormalizedPath -Path $statePath)) {
            throw "Installation state contains an invalid service ownership record for project: $projectRoot"
        }
        $projectKey = (Get-DsbNormalizedPath -Path $projectRoot).ToLowerInvariant()
        if (-not $projects.ContainsKey($projectKey) -and (Test-Path -LiteralPath $statePath -PathType Leaf)) {
            $projects[$projectKey] = [pscustomobject]@{
                ProjectRoot = $projectRoot
                ProjectId = $projectId
            }
        }
    }
    return @($projects.Values)
}

function Reap-DsbUpgradeOrphanServices {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [AllowNull()]
        [object]$State
    )

    $projectIds = @(
        @((Get-DsbObjectProperty -Object $State -Name 'orphan_service_processes' -Default @())) |
            ForEach-Object { Get-DsbObjectProperty -Object $_ -Name 'project_id' } |
            Where-Object { $_ -is [string] -and -not [string]::IsNullOrWhiteSpace($_) } |
            Sort-Object -Unique
    )
    foreach ($projectId in $projectIds) {
        $results = @(Reap-DsbOrphanServiceProcesses -RuntimeRoot $RuntimeRoot -ProjectId $projectId)
        if (@($results | Where-Object { $_.Status -eq 'Unverified' }).Count -gt 0) {
            throw "Cannot safely replace the runtime while an orphan service process is unverifiable for project: $projectId"
        }
    }
}

function Invoke-DsbDependencyInstall {
    param(
        [Parameter(Mandatory)]
        [string]$PythonExecutable,

        [Parameter(Mandatory)]
        [string]$RuntimeRoot
    )

    foreach ($requirementsPath in @(
        (Join-Path $RuntimeRoot 'service\requirements.txt'),
        (Join-Path $RuntimeRoot 'adapter\requirements-mcp.txt')
    )) {
        & $PythonExecutable -m pip install --disable-pip-version-check -r $requirementsPath
        if ($LASTEXITCODE -ne 0) {
            throw "Dependency installation failed for: $requirementsPath"
        }
    }
}

try {
    $resolvedPython = Resolve-DsbPython -PythonPath $PythonPath
    $resolvedCodexHome = Get-DsbCodexHome -CodexHome $CodexHome
    $runtimeRoot = Join-Path $resolvedCodexHome 'database-schema-bootstrap'
    $configPath = Join-Path $resolvedCodexHome 'config.toml'
    [System.IO.Directory]::CreateDirectory($runtimeRoot) | Out-Null
    [System.IO.Directory]::CreateDirectory((Join-Path $runtimeRoot 'state\projects')) | Out-Null
    [System.IO.Directory]::CreateDirectory((Join-Path $runtimeRoot 'logs')) | Out-Null

    $initialState = Get-DsbInstallState -RuntimeRoot $runtimeRoot
    $initialProjects = @(Get-DsbUpgradeServiceProjects -RuntimeRoot $runtimeRoot -State $initialState)
    $initialProjectKeys = @($initialProjects | ForEach-Object { (Get-DsbNormalizedPath -Path $_.ProjectRoot).ToLowerInvariant() })
    Invoke-DsbProjectLocksThenInstallState -RuntimeRoot $runtimeRoot -ProjectRoots @($initialProjects | ForEach-Object { $_.ProjectRoot }) -Action {
        param($lifecycleDeadline)
        $existingState = Assert-DsbExistingInstallation -RuntimeRoot $runtimeRoot -ConfigPath $configPath
        $projectsToRestart = @(Get-DsbUpgradeServiceProjects -RuntimeRoot $runtimeRoot -State $existingState)
        foreach ($project in $projectsToRestart) {
            $projectKey = (Get-DsbNormalizedPath -Path $project.ProjectRoot).ToLowerInvariant()
            if ($initialProjectKeys -notcontains $projectKey) {
                throw "Installation state changed while preparing the runtime upgrade; retry after active project services settle: $($project.ProjectRoot)"
            }
        }
        Reap-DsbUpgradeOrphanServices -RuntimeRoot $runtimeRoot -State $existingState
        foreach ($project in $projectsToRestart) {
            Stop-DsbProjectService -RuntimeRoot $runtimeRoot -ProjectRoot $project.ProjectRoot | Out-Null
        }
        $activeProcesses = @(Get-DsbRuntimeServiceProcesses -RuntimeRoot $runtimeRoot)
        if ($activeProcesses.Count -gt 0) {
            $processIds = @($activeProcesses | ForEach-Object { $_.ProcessId }) -join ', '
            throw "Cannot safely replace the runtime while metadata service process(es) remain active: $processIds"
        }

        $installationId = if ($null -eq $existingState) { [Guid]::NewGuid().ToString() } else { [string](Get-DsbObjectProperty -Object $existingState -Name 'installation_id') }
        $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).ProviderPath

        Copy-DsbRuntimePart -DestinationRoot $runtimeRoot -PartName 'adapter' -SourceBase (Join-Path $repoRoot '.agents\skills\database-schema-bootstrap') -SourceFiles @(
            'mcp_server.py',
            'rpc_client.py',
            'project_routing.py',
            'requirements-mcp.txt'
        )
        Copy-DsbRuntimePart -DestinationRoot $runtimeRoot -PartName 'service' -SourceBase (Join-Path $repoRoot 'mcp\database-schema-bootstrap') -SourceFiles @(
            'server.py',
            'requirements.txt',
            'service'
        )
        Copy-DsbRuntimePart -DestinationRoot $runtimeRoot -PartName 'control' -SourceBase $PSScriptRoot -SourceFiles @(
            'DbSchemaBootstrap.Common.psm1',
            'db-schema-bootstrap.ps1',
            'uninstall.ps1'
        )

        $managedBlock = New-DsbManagedConfigBlock -InstallationId $installationId -PythonPath $resolvedPython -RuntimeRoot $runtimeRoot
        $oldBlockHash = if ($null -eq $existingState) { $null } else { [string](Get-DsbObjectProperty -Object $existingState -Name 'config_block_hash') }
        $configInfo = Set-DsbManagedConfigBlock -ConfigPath $configPath -InstallationId $installationId -Block $managedBlock -ExpectedHash $oldBlockHash
        $newState = [ordered]@{
            version = 1
            installation_id = $installationId
            runtime_root = (Get-DsbNormalizedPath -Path $runtimeRoot)
            config_path = (Get-DsbNormalizedPath -Path $configPath)
            config_block_hash = (Get-DsbSha256String -Value $configInfo.Block)
            python_path = $resolvedPython
            managed_files = @(Get-DsbRuntimeFileManifest -RuntimeRoot $runtimeRoot)
            managed_profiles = @((Get-DsbObjectProperty -Object $existingState -Name 'managed_profiles' -Default @()))
            managed_active_profiles = @((Get-DsbObjectProperty -Object $existingState -Name 'managed_active_profiles' -Default @()))
            credential_targets = @((Get-DsbObjectProperty -Object $existingState -Name 'credential_targets' -Default @()))
            service_state_files = @((Get-DsbObjectProperty -Object $existingState -Name 'service_state_files' -Default @()))
            orphan_service_processes = @((Get-DsbObjectProperty -Object $existingState -Name 'orphan_service_processes' -Default @()))
            log_directory = (Get-DsbNormalizedPath -Path (Join-Path $runtimeRoot 'logs'))
            installed_at = [DateTime]::UtcNow.ToString('o')
            dependency_installation = if ($SkipDependencyInstall) { 'skipped' } else { 'pending' }
        }
        Save-DsbInstallState -RuntimeRoot $runtimeRoot -State $newState
        if (-not $SkipDependencyInstall) {
            Invoke-DsbDependencyInstall -PythonExecutable $resolvedPython -RuntimeRoot $runtimeRoot
            $writtenState = Get-DsbInstallState -RuntimeRoot $runtimeRoot -Required
            Set-DsbObjectProperty -Object $writtenState -Name 'dependency_installation' -Value 'completed'
            Save-DsbInstallState -RuntimeRoot $runtimeRoot -State $writtenState
        }
        foreach ($project in $projectsToRestart) {
            if (Test-Path -LiteralPath $project.ProjectRoot -PathType Container) {
                Start-DsbProjectService -RuntimeRoot $runtimeRoot -ProjectRoot $project.ProjectRoot | Out-Null
            }
        }
    } | Out-Null

    Write-Output "Installed database-schema-bootstrap runtime: $runtimeRoot"
    Write-Output "Managed Codex configuration: $configPath"
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
