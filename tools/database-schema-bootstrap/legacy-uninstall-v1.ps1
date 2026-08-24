[CmdletBinding()]
param(
    [string]$CodexHome,

    [string]$RuntimeRoot,

    [string[]]$Categories,

    [switch]$All,

    [switch]$ConfirmAll,

    [switch]$ForceManaged,

    [switch]$ConfirmForceManaged,

    [switch]$Repair
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Import-Module (Join-Path $PSScriptRoot 'DbSchemaBootstrap.Common.psm1') -Force

function Get-DsbUninstallRuntimeRoot {
    if (-not [string]::IsNullOrWhiteSpace($RuntimeRoot)) {
        return Get-DsbRuntimeRoot -RuntimeRoot $RuntimeRoot
    }
    if (-not [string]::IsNullOrWhiteSpace($CodexHome)) {
        return Get-DsbRuntimeRoot -CodexHome $CodexHome
    }
    $installedRuntimeRoot = [System.IO.Directory]::GetParent($PSScriptRoot).FullName
    if (Test-Path -LiteralPath (Get-DsbInstallStatePath -RuntimeRoot $installedRuntimeRoot) -PathType Leaf) {
        return $installedRuntimeRoot
    }
    return Get-DsbRuntimeRoot
}

function New-DsbInventoryItem {
    param(
        [string]$Category,
        [string]$Target,
        [string]$ManagedStatus,
        [string]$Verification,
        [object]$Record
    )

    return [pscustomobject]@{
        Category = $Category
        Target = $Target
        ManagedStatus = $ManagedStatus
        Verification = $Verification
        Record = $Record
    }
}

function Get-DsbRecordedFileInventory {
    param(
        [object[]]$Records,
        [string]$Category,
        [string]$RuntimeRoot
    )

    $items = @()
    foreach ($record in @($Records)) {
        $path = Get-DsbObjectProperty -Object $record -Name 'path'
        $expectedHash = Get-DsbObjectProperty -Object $record -Name 'sha256'
        if ($path -isnot [string] -or [string]::IsNullOrWhiteSpace($path)) {
            $items += New-DsbInventoryItem -Category $Category -Target '<invalid record>' -ManagedStatus 'invalid' -Verification 'record-invalid' -Record $record
            continue
        }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            $items += New-DsbInventoryItem -Category $Category -Target $path -ManagedStatus 'recorded' -Verification 'missing' -Record $record
            continue
        }
        try {
            $withinRuntime = Test-DsbPathWithin -Path $path -ParentPath $RuntimeRoot
        }
        catch {
            $withinRuntime = $false
        }
        if (-not $withinRuntime) {
            $items += New-DsbInventoryItem -Category $Category -Target $path -ManagedStatus 'invalid' -Verification 'outside-runtime' -Record $record
            continue
        }
        if ($expectedHash -is [string] -and (Get-DsbSha256File -Path $path) -eq $expectedHash) {
            $items += New-DsbInventoryItem -Category $Category -Target $path -ManagedStatus 'managed' -Verification 'verified' -Record $record
        }
        else {
            $items += New-DsbInventoryItem -Category $Category -Target $path -ManagedStatus 'managed' -Verification 'modified' -Record $record
        }
    }
    return @($items)
}

function Get-DsbCleanupInventory {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [object]$State,

        [Parameter(Mandatory)]
        [string]$ExpectedConfigPath
    )

    $items = @()
    $configPath = Get-DsbObjectProperty -Object $State -Name 'config_path'
    $installationId = Get-DsbObjectProperty -Object $State -Name 'installation_id'
    $expectedBlockHash = Get-DsbObjectProperty -Object $State -Name 'config_block_hash'
    if ($configPath -isnot [string]) {
        $items += New-DsbInventoryItem -Category 'config' -Target '<invalid record>' -ManagedStatus 'invalid' -Verification 'record-invalid' -Record $null
    }
    elseif ((Get-DsbNormalizedPath -Path $configPath) -ne (Get-DsbNormalizedPath -Path $ExpectedConfigPath)) {
        $items += New-DsbInventoryItem -Category 'config' -Target $configPath -ManagedStatus 'invalid' -Verification 'outside-runtime' -Record $null
    }
    else {
        $configInfo = Get-DsbManagedConfigBlockInfo -ConfigPath $configPath
        if (-not $configInfo.Present) {
            $items += New-DsbInventoryItem -Category 'config' -Target $configPath -ManagedStatus 'recorded' -Verification 'missing' -Record $configInfo
        }
        elseif ($configInfo.InstallationId -eq $installationId -and (Get-DsbSha256String -Value $configInfo.Block) -eq $expectedBlockHash) {
            $items += New-DsbInventoryItem -Category 'config' -Target $configPath -ManagedStatus 'managed' -Verification 'verified' -Record $configInfo
        }
        else {
            $items += New-DsbInventoryItem -Category 'config' -Target $configPath -ManagedStatus 'managed' -Verification 'modified' -Record $configInfo
        }
    }

    $items += Get-DsbRecordedFileInventory -Records @((Get-DsbObjectProperty -Object $State -Name 'managed_files' -Default @())) -Category 'runtime' -RuntimeRoot $RuntimeRoot
    $statePath = Get-DsbInstallStatePath -RuntimeRoot $RuntimeRoot
    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        $items += New-DsbInventoryItem -Category 'runtime' -Target $statePath -ManagedStatus 'managed' -Verification 'verified' -Record $null
    }

    foreach ($record in @((Get-DsbObjectProperty -Object $State -Name 'service_state_files' -Default @()))) {
        $path = Get-DsbObjectProperty -Object $record -Name 'path'
        if ($path -isnot [string] -or [string]::IsNullOrWhiteSpace($path)) {
            $items += New-DsbInventoryItem -Category 'state' -Target '<invalid record>' -ManagedStatus 'invalid' -Verification 'record-invalid' -Record $record
        }
        elseif (Test-Path -LiteralPath $path -PathType Leaf) {
            try { $validPath = Test-DsbPathWithin -Path $path -ParentPath (Join-Path $RuntimeRoot 'state') } catch { $validPath = $false }
            $stateVerification = if (-not $validPath) {
                'outside-runtime'
            }
            else {
                $expectedStateHash = Get-DsbObjectProperty -Object $record -Name 'sha256'
                if ($expectedStateHash -is [string]) {
                    if ((Get-DsbSha256File -Path $path) -eq $expectedStateHash) { 'verified' } else { 'modified' }
                }
                else {
                    # Legacy records do not carry a file hash.  Semantic state
                    # validation cannot prove that the managed file was not
                    # edited, so require an explicit force confirmation.
                    'modified'
                }
            }
            $items += New-DsbInventoryItem -Category 'state' -Target $path -ManagedStatus 'managed' -Verification $stateVerification -Record $record
        }
        else {
            $items += New-DsbInventoryItem -Category 'state' -Target $path -ManagedStatus 'recorded' -Verification 'missing' -Record $record
        }
    }

    $installLockPath = Join-Path $RuntimeRoot 'state\install-state.lock'
    if (Test-Path -LiteralPath $installLockPath -PathType Leaf) {
        $items += New-DsbInventoryItem -Category 'state' -Target $installLockPath -ManagedStatus 'managed' -Verification 'verified' -Record $null
    }
    $projectLockDirectory = Join-Path $RuntimeRoot 'state\locks'
    if (Test-Path -LiteralPath $projectLockDirectory -PathType Container) {
        foreach ($lockFile in @(Get-ChildItem -LiteralPath $projectLockDirectory -File -Filter '*.lock')) {
            if ($lockFile.Name -match '^[0-9a-f]{64}\.lock$') {
                $items += New-DsbInventoryItem -Category 'state' -Target $lockFile.FullName -ManagedStatus 'managed' -Verification 'verified' -Record $null
            }
        }
    }

    foreach ($collection in @('managed_profiles', 'managed_active_profiles')) {
        foreach ($record in @((Get-DsbObjectProperty -Object $State -Name $collection -Default @()))) {
            $path = Get-DsbObjectProperty -Object $record -Name 'path'
            $expectedHash = Get-DsbObjectProperty -Object $record -Name 'sha256'
            if ($path -isnot [string] -or -not (Test-Path -LiteralPath $path -PathType Leaf)) {
                $items += New-DsbInventoryItem -Category 'profiles' -Target $path -ManagedStatus 'recorded' -Verification 'missing' -Record $record
            }
            elseif ($expectedHash -is [string] -and (Get-DsbSha256File -Path $path) -eq $expectedHash) {
                $items += New-DsbInventoryItem -Category 'profiles' -Target $path -ManagedStatus 'managed' -Verification 'verified' -Record $record
            }
            else {
                $items += New-DsbInventoryItem -Category 'profiles' -Target $path -ManagedStatus 'managed' -Verification 'modified' -Record $record
            }
        }
    }

    $logDirectory = Get-DsbObjectProperty -Object $State -Name 'log_directory'
    if ($logDirectory -is [string]) {
        if (Test-Path -LiteralPath $logDirectory -PathType Container) {
            try { $validLogDirectory = Test-DsbPathWithin -Path $logDirectory -ParentPath $RuntimeRoot } catch { $validLogDirectory = $false }
            $items += New-DsbInventoryItem -Category 'logs' -Target $logDirectory -ManagedStatus 'managed' -Verification $(if ($validLogDirectory) { 'verified' } else { 'outside-runtime' }) -Record $null
        }
        else {
            $items += New-DsbInventoryItem -Category 'logs' -Target $logDirectory -ManagedStatus 'recorded' -Verification 'missing' -Record $null
        }
    }

    foreach ($record in @((Get-DsbObjectProperty -Object $State -Name 'credential_targets' -Default @()))) {
        $target = Get-DsbObjectProperty -Object $record -Name 'target'
        if ($target -is [string] -and -not [string]::IsNullOrWhiteSpace($target)) {
            $items += New-DsbInventoryItem -Category 'credentials' -Target $target -ManagedStatus 'recorded-by-tool' -Verification 'manifest-verified' -Record $record
        }
        else {
            $items += New-DsbInventoryItem -Category 'credentials' -Target '<invalid record>' -ManagedStatus 'invalid' -Verification 'record-invalid' -Record $record
        }
    }
    return @($items)
}

function Get-DsbExpectedConfigPath {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot
    )

    return Join-Path ([System.IO.Directory]::GetParent($RuntimeRoot).FullName) 'config.toml'
}

function Get-DsbRuntimeArtifactPaths {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot
    )

    return @(
        (Join-Path $RuntimeRoot 'adapter'),
        (Join-Path $RuntimeRoot 'service'),
        (Join-Path $RuntimeRoot 'control'),
        (Join-Path $RuntimeRoot 'state'),
        (Get-DsbInstallStatePath -RuntimeRoot $RuntimeRoot)
    )
}

function Get-DsbCoreBlockingItems {
    param(
        [Parameter(Mandatory)]
        [object[]]$Inventory
    )

    return @($Inventory | Where-Object {
        $_.Category -in @('config', 'runtime', 'state') -and
        $_.Verification -in @('missing', 'modified', 'outside-runtime', 'invalid', 'record-invalid')
    })
}

function Stop-DsbRecordedProjectServices {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [object]$State
    )

    foreach ($record in @((Get-DsbObjectProperty -Object $State -Name 'service_state_files' -Default @()))) {
        $projectRoot = Get-DsbObjectProperty -Object $record -Name 'project_root'
        if ($projectRoot -is [string] -and (Test-Path -LiteralPath $projectRoot -PathType Container)) {
            Stop-DsbProjectService -RuntimeRoot $RuntimeRoot -ProjectRoot $projectRoot | Out-Null
        }
    }
}

function Reap-DsbAllOrphanServiceProcesses {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [object]$State
    )

    $projectIds = @(
        @((Get-DsbObjectProperty -Object $State -Name 'orphan_service_processes' -Default @())) |
            ForEach-Object { Get-DsbObjectProperty -Object $_ -Name 'project_id' } |
            Where-Object { $_ -is [string] -and -not [string]::IsNullOrWhiteSpace($_) } |
            Sort-Object -Unique
    )
    $results = @()
    foreach ($projectId in $projectIds) {
        $results += @(Reap-DsbOrphanServiceProcesses -RuntimeRoot $RuntimeRoot -ProjectId $projectId)
    }
    $unverified = @($results | Where-Object { $_.Status -eq 'Unverified' })
    if ($unverified.Count -gt 0) {
        $pids = @($unverified | ForEach-Object { $_.Pid }) -join ', '
        throw "Core uninstall blocked: orphan service process ownership could not be verified for PID(s): $pids"
    }
    return @($results)
}

function Confirm-DsbRemoval {
    param(
        [switch]$Accepted,
        [string]$Prompt,
        [string]$Expected
    )

    if ($Accepted) {
        return $true
    }
    return (Read-Host $Prompt) -ceq $Expected
}

function Remove-DsbEmptyDirectoryTree {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        return
    }
    foreach ($child in @(Get-ChildItem -LiteralPath $Path -Directory -Force | Sort-Object { $_.FullName.Length } -Descending)) {
        Remove-DsbEmptyDirectoryTree -Path $child.FullName
    }
    if ($null -eq (Get-ChildItem -LiteralPath $Path -Force | Select-Object -First 1)) {
        Remove-Item -LiteralPath $Path -Force
    }
}

function Remove-DsbProjectLockFiles {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot
    )

    $lockDirectory = Join-Path $RuntimeRoot 'state\locks'
    $deadline = [System.Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        $remainingFiles = @()
        if (Test-Path -LiteralPath $lockDirectory -PathType Container) {
            foreach ($lockFile in @(Get-ChildItem -LiteralPath $lockDirectory -File -Filter '*.lock' | Where-Object { $_.Name -match '^[0-9a-f]{64}\.lock$' })) {
                try {
                    Remove-Item -LiteralPath $lockFile.FullName -Force -ErrorAction Stop
                }
                catch {
                    $remainingFiles += $lockFile.FullName
                }
            }
        }
        if ($remainingFiles.Count -eq 0) {
            return
        }
        if ($deadline.Elapsed.TotalMilliseconds -ge 30000) {
            throw "Unable to remove project lifecycle lock file(s) after waiting for concurrent controls: $($remainingFiles -join ', ')"
        }
        Start-Sleep -Milliseconds 100
    }
}

function Test-DsbProjectLockFile {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$Target
    )

    try {
        return Test-DsbPathWithin -Path $Target -ParentPath (Join-Path $RuntimeRoot 'state\locks')
    }
    catch {
        return $false
    }
}

try {
    $effectiveRuntimeRoot = Get-DsbUninstallRuntimeRoot
    $expectedConfigPath = Get-DsbExpectedConfigPath -RuntimeRoot $effectiveRuntimeRoot
    $state = Get-DsbInstallState -RuntimeRoot $effectiveRuntimeRoot
    if ($null -eq $state) {
        $configInfo = Get-DsbManagedConfigBlockInfo -ConfigPath $expectedConfigPath
        $runtimeArtifacts = @(Get-DsbRuntimeArtifactPaths -RuntimeRoot $effectiveRuntimeRoot | Where-Object { Test-Path -LiteralPath $_ })
        if (-not $Repair) {
            throw "Global database-schema-bootstrap installation state was not found: $(Get-DsbInstallStatePath -RuntimeRoot $effectiveRuntimeRoot)"
        }
        if ($runtimeArtifacts.Count -gt 0) {
            $artifactList = $runtimeArtifacts -join ', '
            throw "Repair stopped: installation state is missing while managed runtime artifacts still exist ($artifactList). No files were deleted."
        }
        if (-not $configInfo.Present) {
            throw "Repair found no complete managed Codex configuration block: $expectedConfigPath"
        }
        Write-Output "Repair inventory: managed configuration block at $expectedConfigPath"
        if (-not (Confirm-DsbRemoval -Accepted:$ConfirmAll -Prompt 'Type REMOVE to delete the boundary-validated managed configuration block' -Expected 'REMOVE')) {
            throw 'Repair cancelled.'
        }
        $updatedContent = $configInfo.Content.Remove($configInfo.Index, $configInfo.Length)
        Write-DsbAtomicUtf8File -Path $expectedConfigPath -Content $updatedContent
        Write-Output 'Repair removed only the boundary-validated managed configuration block; credentials and runtime files were not inspected or rebuilt.'
        exit 0
    }
    if ((Get-DsbObjectProperty -Object $state -Name 'runtime_root') -isnot [string] -or (Get-DsbNormalizedPath -Path (Get-DsbObjectProperty -Object $state -Name 'runtime_root')) -ne (Get-DsbNormalizedPath -Path $effectiveRuntimeRoot)) {
        throw 'Installation state points to a different runtime root; refusing to uninstall.'
    }

    $inventory = Get-DsbCleanupInventory -RuntimeRoot $effectiveRuntimeRoot -State $state -ExpectedConfigPath $expectedConfigPath
    Write-Output 'Cleanup inventory:'
    $inventory | Select-Object Category, Target, ManagedStatus, Verification | Format-Table -AutoSize | Out-Host

    $knownCategories = @('config', 'runtime', 'state', 'logs', 'profiles', 'credentials')
    if ($All) {
        $selectedCategories = $knownCategories
    }
    elseif ($null -ne $Categories -and $Categories.Count -gt 0) {
        $selectedCategories = @($Categories | ForEach-Object { $_.Trim().ToLowerInvariant() })
    }
    else {
        $selection = Read-Host 'Select cleanup categories (config,runtime,state,logs,profiles,credentials)'
        $selectedCategories = @($selection -split ',' | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    }
    foreach ($category in $selectedCategories) {
        if ($knownCategories -notcontains $category) {
            throw "Unknown cleanup category: $category"
        }
    }
    $selectedCategories = @($selectedCategories | Select-Object -Unique)
    $coreRequested = @($selectedCategories | Where-Object { $_ -in @('config', 'runtime') }).Count -gt 0
    if ($coreRequested -and -not ($selectedCategories -contains 'state')) {
        $selectedCategories = @('config', 'runtime', 'state') + @($selectedCategories | Where-Object { $_ -notin @('config', 'runtime', 'state') })
        Write-Output 'Core cleanup selection expanded to: config,runtime,state'
    }
    $coreSelected = @($selectedCategories | Where-Object { $_ -in @('config', 'runtime', 'state') }).Count -gt 0
    $blockingCoreItems = @(
        if ($coreRequested) {
            Get-DsbCoreBlockingItems -Inventory $inventory
        }
        else {
            $inventory | Where-Object {
                $_.Category -eq 'state' -and
                $_.Verification -in @('missing', 'modified', 'outside-runtime', 'invalid', 'record-invalid')
            }
        }
    )
    if ($coreSelected -and $blockingCoreItems.Count -gt 0) {
        $unsafeItems = @($blockingCoreItems | Where-Object { $_.Verification -ne 'modified' })
        if ($unsafeItems.Count -gt 0) {
            $targets = @($unsafeItems | ForEach-Object { $_.Target }) -join ', '
            throw "Core uninstall blocked by unverified managed items: $targets"
        }
        if (-not $ForceManaged) {
            $targets = @($blockingCoreItems | ForEach-Object { $_.Target }) -join ', '
            throw "Core uninstall blocked because managed items were modified: $targets. Use -ForceManaged -ConfirmForceManaged to override."
        }
    }
    $candidateItems = @($inventory | Where-Object {
        $selectedCategories -contains $_.Category -and ($_.Verification -eq 'verified' -or $_.Verification -eq 'manifest-verified' -or ($ForceManaged -and $_.Verification -eq 'modified'))
    })
    $orphanRecordCount = @((Get-DsbObjectProperty -Object $state -Name 'orphan_service_processes' -Default @())).Count
    $initialNoOp = $candidateItems.Count -eq 0 -and (-not $coreSelected -or $orphanRecordCount -eq 0)
    $forceManagedConfirmed = $false
    if (-not $initialNoOp -and -not (Confirm-DsbRemoval -Accepted:$ConfirmAll -Prompt 'Type REMOVE to delete the selected verified managed items' -Expected 'REMOVE')) {
        throw 'Uninstall cancelled.'
    }
    if ($ForceManaged -and @($candidateItems | Where-Object { $_.Verification -eq 'modified' }).Count -gt 0) {
        if (-not (Confirm-DsbRemoval -Accepted:$ConfirmForceManaged -Prompt 'Type FORCE DELETE to remove edited managed items' -Expected 'FORCE DELETE')) {
            throw 'Force-managed uninstall cancelled.'
        }
        $forceManagedConfirmed = $true
    }
    $initialProjectRoots = @(
        @((Get-DsbObjectProperty -Object $state -Name 'service_state_files' -Default @())) |
            ForEach-Object { Get-DsbObjectProperty -Object $_ -Name 'project_root' } |
            Where-Object { $_ -is [string] -and -not [string]::IsNullOrWhiteSpace($_) } |
            Sort-Object -Unique
    )
    $cleanupResult = Invoke-DsbProjectLocksThenInstallState -RuntimeRoot $effectiveRuntimeRoot -ProjectRoots $initialProjectRoots -Action {
        param($lifecycleDeadline)
        $lockedState = Get-DsbInstallState -RuntimeRoot $effectiveRuntimeRoot -Required
        if ((Get-DsbObjectProperty -Object $lockedState -Name 'runtime_root') -isnot [string] -or (Get-DsbNormalizedPath -Path (Get-DsbObjectProperty -Object $lockedState -Name 'runtime_root')) -ne (Get-DsbNormalizedPath -Path $effectiveRuntimeRoot)) {
            throw 'Installation state changed to a different runtime root; refusing to uninstall.'
        }
        $lockedInventory = @(Get-DsbCleanupInventory -RuntimeRoot $effectiveRuntimeRoot -State $lockedState -ExpectedConfigPath $expectedConfigPath)
        $lockedBlockingItems = @(
            if ($coreRequested) {
                Get-DsbCoreBlockingItems -Inventory $lockedInventory
            }
            else {
                $lockedInventory | Where-Object {
                    $_.Category -eq 'state' -and
                    $_.Verification -in @('missing', 'modified', 'outside-runtime', 'invalid', 'record-invalid')
                }
            }
        )
        if ($coreSelected -and $lockedBlockingItems.Count -gt 0) {
            $unsafeItems = @($lockedBlockingItems | Where-Object { $_.Verification -ne 'modified' })
            if ($unsafeItems.Count -gt 0) {
                $targets = @($unsafeItems | ForEach-Object { $_.Target }) -join ', '
                throw "Core uninstall blocked by unverified managed items: $targets"
            }
            if (-not $ForceManaged) {
                $targets = @($lockedBlockingItems | ForEach-Object { $_.Target }) -join ', '
                throw "Core uninstall blocked because managed items were modified: $targets. Use -ForceManaged -ConfirmForceManaged to override."
            }
            if (-not $forceManagedConfirmed) {
                throw 'Managed items changed after uninstall confirmation; rerun the uninstall command to review the new inventory.'
            }
        }
        $lockedCandidateItems = @($lockedInventory | Where-Object {
            $selectedCategories -contains $_.Category -and ($_.Verification -eq 'verified' -or $_.Verification -eq 'manifest-verified' -or ($ForceManaged -and $_.Verification -eq 'modified'))
        })
        $installLockPath = Join-Path $effectiveRuntimeRoot 'state\install-state.lock'
        $installLockSelected = $selectedCategories -contains 'state'
        $installLockPresent = $installLockSelected -and (Test-Path -LiteralPath $installLockPath -PathType Leaf)
        $lockedCleanupItems = @($lockedCandidateItems | Where-Object {
            $_.Target -ne $installLockPath -and
            -not (Test-DsbProjectLockFile -RuntimeRoot $effectiveRuntimeRoot -Target $_.Target)
        })
        $lockedProjectLockItems = @($lockedCandidateItems | Where-Object {
            Test-DsbProjectLockFile -RuntimeRoot $effectiveRuntimeRoot -Target $_.Target
        })
        $lockedOrphanRecordCount = @((Get-DsbObjectProperty -Object $lockedState -Name 'orphan_service_processes' -Default @())).Count
        if ($initialNoOp -and ($lockedCleanupItems.Count -gt 0 -or $lockedProjectLockItems.Count -gt 0 -or $lockedOrphanRecordCount -gt 0)) {
            throw 'Installation state changed after the initial uninstall inventory; rerun the uninstall command to review the new inventory.'
        }
        if ($lockedCleanupItems.Count -eq 0 -and $lockedProjectLockItems.Count -eq 0 -and (-not $coreSelected -or $lockedOrphanRecordCount -eq 0)) {
            if ($installLockPresent) {
                return [pscustomobject]@{ NoOp = $false; RemoveInstallLock = $true; RemoveProjectLocks = $false; RemoveState = $false; RemoveRuntime = $false }
            }
            if (-not $initialNoOp) {
                Write-Verbose 'The uninstall inventory changed after confirmation; no verified managed items remain.'
            }
            return [pscustomobject]@{ NoOp = $true; RemoveInstallLock = $selectedCategories -contains 'state'; RemoveProjectLocks = $false; RemoveState = $false; RemoveRuntime = $false }
        }

        foreach ($credentialItem in @($lockedCandidateItems | Where-Object { $_.Category -eq 'credentials' })) {
            Remove-DsbWindowsCredential -Target $credentialItem.Target
        }

        if ($coreSelected) {
            Stop-DsbRecordedProjectServices -RuntimeRoot $effectiveRuntimeRoot -State $lockedState
            $lockedState = Get-DsbInstallState -RuntimeRoot $effectiveRuntimeRoot -Required
            Reap-DsbAllOrphanServiceProcesses -RuntimeRoot $effectiveRuntimeRoot -State $lockedState | Out-Null
            $activeProcesses = @(Get-DsbRuntimeServiceProcesses -RuntimeRoot $effectiveRuntimeRoot)
            if ($activeProcesses.Count -gt 0) {
                $processIds = @($activeProcesses | ForEach-Object { $_.ProcessId }) -join ', '
                throw "Core uninstall blocked because metadata service process(es) remain active: $processIds"
            }
        }

        foreach ($configItem in @($lockedCandidateItems | Where-Object { $_.Category -eq 'config' })) {
            $configInfo = $configItem.Record
            $updatedContent = $configInfo.Content.Remove($configInfo.Index, $configInfo.Length)
            Write-DsbAtomicUtf8File -Path $configItem.Target -Content $updatedContent
        }
        foreach ($fileItem in @($lockedCandidateItems | Where-Object { $_.Category -eq 'runtime' -and $_.Target -ne (Get-DsbInstallStatePath -RuntimeRoot $effectiveRuntimeRoot) })) {
            if (Test-Path -LiteralPath $fileItem.Target -PathType Leaf) {
                Remove-Item -LiteralPath $fileItem.Target -Force
            }
        }
        foreach ($stateItem in @($lockedCandidateItems | Where-Object {
            $_.Category -eq 'state' -and
            $_.Target -ne $installLockPath -and
            -not (Test-DsbProjectLockFile -RuntimeRoot $effectiveRuntimeRoot -Target $_.Target)
        })) {
            if (Test-Path -LiteralPath $stateItem.Target -PathType Leaf) {
                Remove-Item -LiteralPath $stateItem.Target -Force
            }
        }
        foreach ($profileItem in @($lockedCandidateItems | Where-Object { $_.Category -eq 'profiles' })) {
            if (Test-Path -LiteralPath $profileItem.Target -PathType Leaf) {
                Remove-Item -LiteralPath $profileItem.Target -Force
            }
        }
        foreach ($logItem in @($lockedCandidateItems | Where-Object { $_.Category -eq 'logs' })) {
            if (Test-Path -LiteralPath $logItem.Target -PathType Container) {
                Remove-Item -LiteralPath $logItem.Target -Recurse -Force
            }
        }
        if ($selectedCategories -contains 'runtime') {
            $statePath = Get-DsbInstallStatePath -RuntimeRoot $effectiveRuntimeRoot
            if (Test-Path -LiteralPath $statePath -PathType Leaf) {
                Remove-Item -LiteralPath $statePath -Force
            }
        }
        return [pscustomobject]@{
            NoOp = $false
            RemoveInstallLock = $selectedCategories -contains 'state'
            RemoveProjectLocks = $selectedCategories -contains 'state'
            RemoveState = $selectedCategories -contains 'state'
            RemoveRuntime = $selectedCategories -contains 'runtime'
        }
    }
    if ($cleanupResult.NoOp) {
        Write-Output 'No verified managed items matched the selected categories; nothing was removed.'
        exit 0
    }
    $installLockPath = Join-Path $effectiveRuntimeRoot 'state\install-state.lock'
    if ($cleanupResult.RemoveInstallLock -and (Test-Path -LiteralPath $installLockPath -PathType Leaf)) {
        Remove-Item -LiteralPath $installLockPath -Force
    }
    if ($cleanupResult.RemoveProjectLocks) {
        Remove-DsbProjectLockFiles -RuntimeRoot $effectiveRuntimeRoot
    }
    if ($cleanupResult.RemoveState) {
        Remove-DsbEmptyDirectoryTree -Path (Join-Path $effectiveRuntimeRoot 'state\projects')
        Remove-DsbEmptyDirectoryTree -Path (Join-Path $effectiveRuntimeRoot 'state\locks')
        Remove-DsbEmptyDirectoryTree -Path (Join-Path $effectiveRuntimeRoot 'state')
    }
    if ($cleanupResult.RemoveRuntime) {
        foreach ($part in @('adapter', 'service', 'control')) {
            Remove-DsbEmptyDirectoryTree -Path (Join-Path $effectiveRuntimeRoot $part)
        }
    }
    Remove-DsbEmptyDirectoryTree -Path $effectiveRuntimeRoot
    Write-Output 'Selected verified managed items were removed. Source repository and unrecorded project files were preserved.'
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
