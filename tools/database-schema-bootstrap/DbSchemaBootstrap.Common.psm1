Set-StrictMode -Version Latest

$script:DsbConfigStartPattern = '(?m)^# >>> database-schema-bootstrap managed id=[0-9a-fA-F-]{36} >>>\s*$'
$script:DsbConfigEndPattern = '(?m)^# <<< database-schema-bootstrap managed id=[0-9a-fA-F-]{36} <<<\s*$'
$script:DsbConfigBlockPattern = '(?ms)^# >>> database-schema-bootstrap managed id=(?<id>[0-9a-fA-F-]{36}) >>>\r?\n.*?^# <<< database-schema-bootstrap managed id=\k<id> <<<\r?$'
$script:DsbLifecycleTimeoutMilliseconds = 25000
$script:DsbHeldFileLocks = @{}

function New-DsbLifecycleDeadline {
    return [System.Diagnostics.Stopwatch]::StartNew()
}

function Get-DsbRemainingLifecycleMilliseconds {
    param(
        [Parameter(Mandatory)]
        [System.Diagnostics.Stopwatch]$Deadline
    )

    $remaining = $script:DsbLifecycleTimeoutMilliseconds - $Deadline.Elapsed.TotalMilliseconds
    if ($remaining -le 0) {
        return 0
    }
    return [int][Math]::Floor($remaining)
}

function Assert-DsbLifecycleTimeRemaining {
    param(
        [Parameter(Mandatory)]
        [System.Diagnostics.Stopwatch]$Deadline
    )

    $remaining = Get-DsbRemainingLifecycleMilliseconds -Deadline $Deadline
    if ($remaining -le 0) {
        throw 'Database metadata service lifecycle timed out.'
    }
    return $remaining
}

function Invoke-DsbExclusiveFileLock {
    param(
        [Parameter(Mandatory)]
        [string]$LockPath,

        [Parameter(Mandatory)]
        [System.Diagnostics.Stopwatch]$Deadline,

        [Parameter(Mandatory)]
        [scriptblock]$Action
    )

    $lockDirectory = [System.IO.Path]::GetDirectoryName($LockPath)
    if ([string]::IsNullOrWhiteSpace($lockDirectory)) {
        throw "A parent directory is required for lock: $LockPath"
    }
    [System.IO.Directory]::CreateDirectory($lockDirectory) | Out-Null
    $lockKey = ([System.IO.Path]::GetFullPath($LockPath)).ToLowerInvariant()
    if ($script:DsbHeldFileLocks.ContainsKey($lockKey)) {
        $heldLock = $script:DsbHeldFileLocks[$lockKey]
        $heldLock.Depth++
        try {
            return (& $Action)
        }
        finally {
            $heldLock.Depth--
        }
    }
    $lockStream = $null
    try {
        while ($null -eq $lockStream) {
            try {
                $lockStream = [System.IO.File]::Open(
                    $LockPath,
                    [System.IO.FileMode]::OpenOrCreate,
                    [System.IO.FileAccess]::ReadWrite,
                    [System.IO.FileShare]::None
                )
            }
            catch [System.IO.IOException] {
                $remaining = Assert-DsbLifecycleTimeRemaining -Deadline $Deadline
                Start-Sleep -Milliseconds ([Math]::Min(100, [Math]::Max(1, $remaining)))
            }
        }
        $script:DsbHeldFileLocks[$lockKey] = [pscustomobject]@{
            Stream = $lockStream
            Depth = 1
        }
        return (& $Action)
    }
    finally {
        $script:DsbHeldFileLocks.Remove($lockKey) | Out-Null
        if ($null -ne $lockStream) {
            $lockStream.Dispose()
        }
    }
}

function Get-DsbInstallStateLockPath {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot
    )

    return Join-Path $RuntimeRoot 'state\install-state.lock'
}

function Invoke-DsbInstallStateLock {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [scriptblock]$Action,

        [System.Diagnostics.Stopwatch]$Deadline
    )

    if ($null -eq $Deadline) {
        $Deadline = New-DsbLifecycleDeadline
    }
    return Invoke-DsbExclusiveFileLock -LockPath (Get-DsbInstallStateLockPath -RuntimeRoot $RuntimeRoot) -Deadline $Deadline -Action $Action
}

function Get-DsbProjectLifecycleLockPath {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot
    )

    return Join-Path $RuntimeRoot ('state\locks\' + (Get-DsbProjectId -ProjectRoot $ProjectRoot) + '.lock')
}

function Invoke-DsbProjectLifecycle {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [Parameter(Mandatory)]
        [scriptblock]$Action
    )

    $deadline = New-DsbLifecycleDeadline
    $lifecycleAction = $Action
    $lifecycleDeadline = $deadline
    return Invoke-DsbExclusiveFileLock -LockPath (Get-DsbProjectLifecycleLockPath -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot) -Deadline $deadline -Action {
        & $lifecycleAction $lifecycleDeadline
    }
}

function Invoke-DsbProjectLocksThenInstallState {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [AllowEmptyCollection()]
        [string[]]$ProjectRoots = @(),

        [Parameter(Mandatory)]
        [scriptblock]$Action
    )

    $deadline = New-DsbLifecycleDeadline
    $lifecycleAction = $Action
    $orderedRoots = @(
        $ProjectRoots |
            Where-Object { $_ -is [string] -and -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object { Get-DsbNormalizedPath -Path $_ } |
            Sort-Object -Unique
    )
    $next = $null
    $next = {
        param([int]$Index)
        if ($Index -ge $orderedRoots.Count) {
            return Invoke-DsbInstallStateLock -RuntimeRoot $RuntimeRoot -Deadline $deadline -Action {
                & $lifecycleAction $deadline
            }
        }
        $projectRoot = $orderedRoots[$Index]
        $nextIndex = $Index + 1
        return Invoke-DsbExclusiveFileLock -LockPath (Get-DsbProjectLifecycleLockPath -RuntimeRoot $RuntimeRoot -ProjectRoot $projectRoot) -Deadline $deadline -Action {
            & $next $nextIndex
        }
    }
    return & $next 0
}

function Get-DsbObjectProperty {
    param(
        [AllowNull()]
        [object]$Object,

        [Parameter(Mandatory)]
        [string]$Name,

        [AllowNull()]
        [object]$Default = $null
    )

    if ($null -eq $Object) {
        return $Default
    }

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $Default
    }
    return $property.Value
}

function Set-DsbObjectProperty {
    param(
        [Parameter(Mandatory)]
        [object]$Object,

        [Parameter(Mandatory)]
        [string]$Name,

        [AllowNull()]
        [object]$Value
    )

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        $Object | Add-Member -MemberType NoteProperty -Name $Name -Value $Value
    }
    else {
        $property.Value = $Value
    }
}

function Write-DsbAtomicUtf8File {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Content
    )

    $directory = [System.IO.Path]::GetDirectoryName($Path)
    if ([string]::IsNullOrWhiteSpace($directory)) {
        throw "A parent directory is required for atomic write: $Path"
    }
    [System.IO.Directory]::CreateDirectory($directory) | Out-Null
    $temporaryPath = Join-Path $directory ('.{0}.{1}.tmp' -f ([System.IO.Path]::GetFileName($Path)), [Guid]::NewGuid().ToString('N'))
    $encoding = [System.Text.UTF8Encoding]::new($false)

    try {
        [System.IO.File]::WriteAllText($temporaryPath, $Content, $encoding)
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            $backupPath = Join-Path $directory ('.{0}.{1}.bak' -f ([System.IO.Path]::GetFileName($Path)), [Guid]::NewGuid().ToString('N'))
            try {
                [System.IO.File]::Replace($temporaryPath, $Path, $backupPath, $true)
            }
            finally {
                if (Test-Path -LiteralPath $backupPath -PathType Leaf) {
                    Remove-Item -LiteralPath $backupPath -Force
                }
            }
        }
        else {
            [System.IO.File]::Move($temporaryPath, $Path)
        }
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

function Read-DsbJsonFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($content)) {
        throw "JSON file is empty: $Path"
    }
    try {
        return $content | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "JSON file is invalid: $Path"
    }
}

function Write-DsbJsonFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [object]$Value
    )

    Write-DsbAtomicUtf8File -Path $Path -Content (($Value | ConvertTo-Json -Depth 12) + [Environment]::NewLine)
}

function Get-DsbSha256File {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $hasher.ComputeHash([System.IO.File]::ReadAllBytes($Path))
        return ([System.BitConverter]::ToString($hashBytes)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $hasher.Dispose()
    }
}

function Get-DsbSha256String {
    param(
        [Parameter(Mandatory)]
        [string]$Value
    )

    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Value))
        return ([System.BitConverter]::ToString($hashBytes)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $hasher.Dispose()
    }
}

function Get-DsbCodexHome {
    param(
        [string]$CodexHome
    )

    if ([string]::IsNullOrWhiteSpace($CodexHome)) {
        if ([string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
            throw 'USERPROFILE is unavailable; pass -CodexHome explicitly.'
        }
        $CodexHome = Join-Path $env:USERPROFILE '.codex'
    }
    return [System.IO.Path]::GetFullPath($CodexHome)
}

function Get-DsbRuntimeRoot {
    param(
        [string]$CodexHome,
        [string]$RuntimeRoot
    )

    if (-not [string]::IsNullOrWhiteSpace($RuntimeRoot)) {
        return [System.IO.Path]::GetFullPath($RuntimeRoot)
    }
    return Join-Path (Get-DsbCodexHome -CodexHome $CodexHome) 'database-schema-bootstrap'
}

function Resolve-DsbPython {
    param(
        [string]$PythonPath
    )

    if ([string]::IsNullOrWhiteSpace($PythonPath)) {
        $PythonPath = $env:CODEX_PYTHON
    }
    if ([string]::IsNullOrWhiteSpace($PythonPath)) {
        throw 'Python is not configured. Pass -PythonPath or set CODEX_PYTHON.'
    }
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw "Configured Python executable was not found: $PythonPath"
    }
    return (Resolve-Path -LiteralPath $PythonPath).ProviderPath
}

function Get-DsbNormalizedPath {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    try {
        $fullPath = [System.IO.Path]::GetFullPath($Path)
    }
    catch {
        throw "Path identity is unavailable: $Path"
    }
    $fullPath = $fullPath.Replace([System.IO.Path]::AltDirectorySeparatorChar, [System.IO.Path]::DirectorySeparatorChar)
    $root = [System.IO.Path]::GetPathRoot($fullPath)
    while ($fullPath.Length -gt $root.Length -and $fullPath.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $fullPath = $fullPath.Substring(0, $fullPath.Length - 1)
    }
    return $fullPath.ToLowerInvariant()
}

function Get-DsbProjectRoot {
    param(
        [string]$ProjectPath = (Get-Location).Path,
        [switch]$RequireGit
    )

    if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
        throw "Project path was not found: $ProjectPath"
    }
    $lexicalPath = Get-DsbNormalizedPath -Path $ProjectPath
    $git = Get-Command -Name git -ErrorAction SilentlyContinue
    if ($null -ne $git) {
        $gitRoot = & git -C $lexicalPath rev-parse --show-toplevel 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace(($gitRoot | Select-Object -First 1))) {
            return Get-DsbNormalizedPath -Path ($gitRoot | Select-Object -First 1)
        }
    }
    if ($RequireGit) {
        throw 'Project identity cannot be confirmed because the current path is not inside a Git worktree.'
    }
    return $lexicalPath
}

function Get-DsbProjectId {
    param(
        [Parameter(Mandatory)]
        [string]$ProjectRoot
    )

    return Get-DsbSha256String -Value (Get-DsbNormalizedPath -Path $ProjectRoot)
}

function Test-DsbPathWithin {
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string]$ParentPath
    )

    $normalizedPath = Get-DsbNormalizedPath -Path $Path
    $normalizedParent = Get-DsbNormalizedPath -Path $ParentPath
    return $normalizedPath -eq $normalizedParent -or $normalizedPath.StartsWith($normalizedParent + '\', [System.StringComparison]::Ordinal)
}

function Assert-DsbProfileName {
    param(
        [Parameter(Mandatory)]
        [string]$Name
    )

    if ($Name -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$') {
        throw 'Profile name must contain only letters, digits, dot, underscore, or hyphen.'
    }
    if ($Name -ieq 'active-profile') {
        throw "Profile name '$Name' is reserved for active-profile.json."
    }
}

function Get-DsbProfileDirectory {
    param(
        [Parameter(Mandatory)]
        [string]$ProjectRoot
    )

    return Join-Path $ProjectRoot '.agents\database-schema-bootstrap\profiles'
}

function Get-DsbProfilePath {
    param(
        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [Parameter(Mandatory)]
        [string]$Name
    )

    Assert-DsbProfileName -Name $Name
    return Join-Path (Get-DsbProfileDirectory -ProjectRoot $ProjectRoot) ($Name + '.json')
}

function Get-DsbActiveProfilePath {
    param(
        [Parameter(Mandatory)]
        [string]$ProjectRoot
    )

    return Join-Path (Get-DsbProfileDirectory -ProjectRoot $ProjectRoot) 'active-profile.json'
}

function Resolve-DsbSelectedProfile {
    param(
        [Parameter(Mandatory)]
        [string]$ProjectRoot
    )

    $activePath = Get-DsbActiveProfilePath -ProjectRoot $ProjectRoot
    if (Test-Path -LiteralPath $activePath -PathType Leaf) {
        $active = Read-DsbJsonFile -Path $activePath
        $name = Get-DsbObjectProperty -Object $active -Name 'name'
        if ($name -isnot [string]) {
            throw "The active profile record is invalid: $activePath"
        }
        Assert-DsbProfileName -Name $name
        $profilePath = Get-DsbProfilePath -ProjectRoot $ProjectRoot -Name $name
        if (-not (Test-Path -LiteralPath $profilePath -PathType Leaf)) {
            throw "The active profile does not exist: $name"
        }
        return [pscustomobject]@{ Name = $name; Path = $profilePath; Source = 'active' }
    }

    $defaultPath = Get-DsbProfilePath -ProjectRoot $ProjectRoot -Name 'default'
    if (Test-Path -LiteralPath $defaultPath -PathType Leaf) {
        return [pscustomobject]@{ Name = 'default'; Path = $defaultPath; Source = 'default' }
    }
    return $null
}

function Get-DsbInstallStatePath {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot
    )

    return Join-Path $RuntimeRoot 'install-state.json'
}

function Get-DsbInstallState {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [switch]$Required
    )

    $statePath = Get-DsbInstallStatePath -RuntimeRoot $RuntimeRoot
    $state = Read-DsbJsonFile -Path $statePath
    if ($Required -and $null -eq $state) {
        throw "Global database-schema-bootstrap installation state was not found: $statePath"
    }
    return $state
}

function Save-DsbInstallState {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [object]$State
    )

    Write-DsbJsonFile -Path (Get-DsbInstallStatePath -RuntimeRoot $RuntimeRoot) -Value $State
}

function Register-DsbInstallRecord {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [ValidateSet('managed_profiles', 'managed_active_profiles', 'credential_targets', 'service_state_files', 'orphan_service_processes')]
        [string]$Collection,

        [Parameter(Mandatory)]
        [object]$Record,

        [Parameter(Mandatory)]
        [string]$Key,

        [Parameter(Mandatory)]
        [string]$KeyValue,

        [System.Diagnostics.Stopwatch]$Deadline
    )

    Invoke-DsbInstallStateLock -RuntimeRoot $RuntimeRoot -Deadline $Deadline -Action {
        $state = Get-DsbInstallState -RuntimeRoot $RuntimeRoot -Required
        $records = @((Get-DsbObjectProperty -Object $state -Name $Collection -Default @()))
        $updatedRecords = @($records | Where-Object { (Get-DsbObjectProperty -Object $_ -Name $Key) -ne $KeyValue })
        $updatedRecords += $Record
        Set-DsbObjectProperty -Object $state -Name $Collection -Value @($updatedRecords)
        Save-DsbInstallState -RuntimeRoot $RuntimeRoot -State $state
    }
}

function Unregister-DsbInstallRecord {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [ValidateSet('managed_profiles', 'managed_active_profiles', 'credential_targets', 'service_state_files', 'orphan_service_processes')]
        [string]$Collection,

        [Parameter(Mandatory)]
        [string]$Key,

        [Parameter(Mandatory)]
        [string]$KeyValue,

        [System.Diagnostics.Stopwatch]$Deadline
    )

    Invoke-DsbInstallStateLock -RuntimeRoot $RuntimeRoot -Deadline $Deadline -Action {
        $state = Get-DsbInstallState -RuntimeRoot $RuntimeRoot -Required
        $records = @((Get-DsbObjectProperty -Object $state -Name $Collection -Default @()))
        $updatedRecords = @($records | Where-Object { (Get-DsbObjectProperty -Object $_ -Name $Key) -ne $KeyValue })
        Set-DsbObjectProperty -Object $state -Name $Collection -Value @($updatedRecords)
        Save-DsbInstallState -RuntimeRoot $RuntimeRoot -State $state
    }
}

function ConvertTo-DsbTomlString {
    param(
        [Parameter(Mandatory)]
        [string]$Value
    )

    $escaped = $Value.Replace('\', '\\').Replace('"', '\"').Replace("`r", '\r').Replace("`n", '\n')
    return '"' + $escaped + '"'
}

function Get-DsbManagedConfigBlockInfo {
    param(
        [Parameter(Mandatory)]
        [string]$ConfigPath
    )

    $content = if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
        Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8
    }
    else {
        ''
    }
    $starts = [regex]::Matches($content, $script:DsbConfigStartPattern)
    $ends = [regex]::Matches($content, $script:DsbConfigEndPattern)
    if ($starts.Count -eq 0 -and $ends.Count -eq 0) {
        return [pscustomobject]@{ Content = $content; Present = $false; InstallationId = $null; Block = $null; Index = -1; Length = 0 }
    }
    if ($starts.Count -ne 1 -or $ends.Count -ne 1) {
        throw 'The managed Codex configuration block is duplicated or has incomplete boundaries.'
    }
    $match = [regex]::Match($content, $script:DsbConfigBlockPattern)
    if (-not $match.Success) {
        throw 'The managed Codex configuration block has invalid boundaries.'
    }
    return [pscustomobject]@{
        Content = $content
        Present = $true
        InstallationId = $match.Groups['id'].Value.ToLowerInvariant()
        Block = $match.Value
        Index = $match.Index
        Length = $match.Length
    }
}

function Set-DsbManagedConfigBlock {
    param(
        [Parameter(Mandatory)]
        [string]$ConfigPath,

        [Parameter(Mandatory)]
        [string]$InstallationId,

        [Parameter(Mandatory)]
        [string]$Block,

        [string]$ExpectedHash
    )

    $info = Get-DsbManagedConfigBlockInfo -ConfigPath $ConfigPath
    if ($info.Present) {
        if ($info.InstallationId -ne $InstallationId.ToLowerInvariant()) {
            throw 'The managed Codex configuration block installation ID does not match installation state.'
        }
        if (-not [string]::IsNullOrWhiteSpace($ExpectedHash) -and (Get-DsbSha256String -Value $info.Block) -ne $ExpectedHash) {
            throw 'The managed Codex configuration block was edited; refusing to overwrite it.'
        }
        $updatedContent = $info.Content.Remove($info.Index, $info.Length).Insert($info.Index, $Block)
    }
    elseif ([string]::IsNullOrWhiteSpace($info.Content)) {
        $updatedContent = $Block + [Environment]::NewLine
    }
    else {
        $updatedContent = $info.Content.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $Block + [Environment]::NewLine
    }
    Write-DsbAtomicUtf8File -Path $ConfigPath -Content $updatedContent
    return Get-DsbManagedConfigBlockInfo -ConfigPath $ConfigPath
}

function New-DsbManagedConfigBlock {
    param(
        [Parameter(Mandatory)]
        [string]$InstallationId,

        [Parameter(Mandatory)]
        [string]$PythonPath,

        [Parameter(Mandatory)]
        [string]$RuntimeRoot
    )

    $adapterPath = Join-Path $RuntimeRoot 'adapter\mcp_server.py'
    $controlPath = Join-Path $RuntimeRoot 'control\db-schema-bootstrap.ps1'
    $hookCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" session-start' -f $controlPath
    $pythonToml = ConvertTo-DsbTomlString -Value $PythonPath
    $adapterToml = ConvertTo-DsbTomlString -Value $adapterPath
    $hookToml = ConvertTo-DsbTomlString -Value $hookCommand
    return @(
        "# >>> database-schema-bootstrap managed id=$InstallationId >>>"
        '[mcp_servers.database-schema-bootstrap]'
        "command = $pythonToml"
        ('args = ["-B", ' + $adapterToml + ', "--timeout", "25"]')
        'enabled_tools = ["list_databases", "list_tables", "describe_table"]'
        'startup_timeout_sec = 15'
        'tool_timeout_sec = 30'
        ''
        '[[hooks.SessionStart]]'
        'matcher = "^(startup|resume|clear|compact)$"'
        ''
        '[[hooks.SessionStart.hooks]]'
        'type = "command"'
        "command = $hookToml"
        'timeout = 30'
        '# <<< database-schema-bootstrap managed id=' + $InstallationId + ' <<<'
    ) -join [Environment]::NewLine
}

function Get-DsbServiceStatePath {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectId
    )

    return Join-Path $RuntimeRoot ('state\projects\' + $ProjectId + '.json')
}

function Get-DsbRuntimeServiceProcesses {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot
    )

    $serviceScript = Get-DsbNormalizedPath -Path (Join-Path $RuntimeRoot 'service\server.py')
    try {
        $processes = @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop)
    }
    catch {
        throw "Unable to inspect metadata service processes before changing the runtime: $($_.Exception.Message)"
    }
    return @($processes | Where-Object {
        $_.CommandLine -is [string] -and
        $_.CommandLine.IndexOf($serviceScript, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    })
}

function Test-DsbLoopbackEndpoint {
    param(
        [Parameter(Mandatory)]
        [string]$Endpoint
    )

    try {
        $uri = [Uri]$Endpoint
    }
    catch {
        return $false
    }
    return $uri.Scheme -eq 'http' -and $uri.Host -eq '127.0.0.1' -and $uri.Port -ge 1 -and $uri.Port -le 65535 -and [string]::IsNullOrEmpty($uri.AbsolutePath.Trim('/'))
}

function Invoke-DsbServiceHealth {
    param(
        [Parameter(Mandatory)]
        [object]$State,

        [Parameter(Mandatory)]
        [string]$ProjectId,

        [int]$TimeoutMilliseconds = 2000
    )

    $endpoint = Get-DsbObjectProperty -Object $State -Name 'endpoint'
    $token = Get-DsbObjectProperty -Object $State -Name 'instance_token'
    if ($TimeoutMilliseconds -le 0 -or $endpoint -isnot [string] -or $token -isnot [string] -or -not $token -or -not (Test-DsbLoopbackEndpoint -Endpoint $endpoint)) {
        return $false
    }
    try {
        $request = [System.Net.HttpWebRequest][System.Net.WebRequest]::Create(($endpoint.TrimEnd('/') + '/v1/health'))
        $request.Method = 'GET'
        $request.Timeout = $TimeoutMilliseconds
        $request.ReadWriteTimeout = $TimeoutMilliseconds
        $request.Headers.Add('X-Database-Schema-Bootstrap-Token', $token)
        $response = $null
        $response = $request.GetResponse()
        try {
            $reader = [System.IO.StreamReader]::new($response.GetResponseStream(), [System.Text.Encoding]::UTF8)
            try {
                $body = $reader.ReadToEnd() | ConvertFrom-Json -ErrorAction Stop
            }
            finally {
                $reader.Dispose()
            }
        }
        finally {
            if ($null -ne $response) {
                $response.Dispose()
            }
        }
        return (Get-DsbObjectProperty -Object $body -Name 'ok') -eq $true -and (Get-DsbObjectProperty -Object $body -Name 'project_id') -eq $ProjectId
    }
    catch {
        return $false
    }
}

function Get-DsbRawServiceState {
    param(
        [Parameter(Mandatory)]
        [string]$StatePath
    )

    try {
        return Read-DsbJsonFile -Path $StatePath
    }
    catch {
        return $null
    }
}

function Test-DsbServiceStateForProject {
    param(
        [AllowNull()]
        [object]$State,

        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [Parameter(Mandatory)]
        [string]$ProjectId
    )

    if ($null -eq $State) {
        return $false
    }
    $stateRoot = Get-DsbObjectProperty -Object $State -Name 'project_root'
    $stateId = Get-DsbObjectProperty -Object $State -Name 'project_id'
    $endpoint = Get-DsbObjectProperty -Object $State -Name 'endpoint'
    $port = Get-DsbObjectProperty -Object $State -Name 'port'
    $pid = Get-DsbObjectProperty -Object $State -Name 'pid'
    $token = Get-DsbObjectProperty -Object $State -Name 'instance_token'
    $stateVersion = Get-DsbObjectProperty -Object $State -Name 'version'
    $portValue = 0
    $pidValue = 0
    if (
        $stateVersion -ne 1 -or
        $stateRoot -isnot [string] -or
        $stateId -ne $ProjectId -or
        $endpoint -isnot [string] -or
        $token -isnot [string] -or
        [string]::IsNullOrWhiteSpace($token) -or
        -not [int]::TryParse([string]$port, [ref]$portValue) -or
        $portValue -lt 1 -or
        $portValue -gt 65535 -or
        -not [int]::TryParse([string]$pid, [ref]$pidValue) -or
        $pidValue -le 0 -or
        -not (Test-DsbLoopbackEndpoint -Endpoint $endpoint)
    ) {
        return $false
    }
    try {
        $endpointUri = [Uri]$endpoint
        if ($endpointUri.Port -ne $portValue) {
            return $false
        }
        return (Get-DsbNormalizedPath -Path $stateRoot) -eq (Get-DsbNormalizedPath -Path $ProjectRoot)
    }
    catch {
        return $false
    }
}

function Get-DsbValidatedServiceState {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot
    )

    $projectId = Get-DsbProjectId -ProjectRoot $ProjectRoot
    $statePath = Get-DsbServiceStatePath -RuntimeRoot $RuntimeRoot -ProjectId $projectId
    $state = Get-DsbRawServiceState -StatePath $statePath
    if (-not (Test-DsbServiceStateForProject -State $state -ProjectRoot $ProjectRoot -ProjectId $projectId)) {
        return $null
    }
    return $state
}

function Get-DsbServiceStatus {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [System.Diagnostics.Stopwatch]$Deadline
    )

    $projectId = Get-DsbProjectId -ProjectRoot $ProjectRoot
    $selected = Resolve-DsbSelectedProfile -ProjectRoot $ProjectRoot
    $state = Get-DsbValidatedServiceState -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot
    $healthy = $false
    if ($null -ne $state) {
        $healthTimeout = 2000
        if ($null -ne $Deadline) {
            $healthTimeout = [Math]::Min(2000, (Assert-DsbLifecycleTimeRemaining -Deadline $Deadline))
        }
        $healthy = Invoke-DsbServiceHealth -State $state -ProjectId $projectId -TimeoutMilliseconds $healthTimeout
    }
    return [pscustomobject]@{
        ProjectRoot = $ProjectRoot
        ProjectId = $projectId
        ActiveProfile = if ($null -eq $selected) { $null } else { $selected.Name }
        ProfileSource = if ($null -eq $selected) { $null } else { $selected.Source }
        ServiceState = if ($healthy) { 'running' } elseif ($null -ne $state) { 'unhealthy' } else { 'stopped' }
        Endpoint = if ($healthy) { Get-DsbObjectProperty -Object $state -Name 'endpoint' } else { $null }
        Pid = if ($healthy) { Get-DsbObjectProperty -Object $state -Name 'pid' } else { $null }
    }
}

function Add-DsbProjectProfile {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$DatabaseHost,

        [Parameter(Mandatory)]
        [string]$Database,

        [Parameter(Mandatory)]
        [string]$ConnectionDatabase,

        [Parameter(Mandatory)]
        [string]$DatabaseUser,

        [ValidateRange(1, 65535)]
        [int]$Port = 5432,

        [string]$Schema = 'public',

        [string]$CredentialTarget,

        [string[]]$TargetTables = @(),

        [switch]$Force
    )

    Assert-DsbProfileName -Name $Name
    foreach ($value in @($DatabaseHost, $Database, $ConnectionDatabase, $DatabaseUser, $Schema)) {
        if ([string]::IsNullOrWhiteSpace($value)) {
            throw 'PostgreSQL profile fields must not be blank.'
        }
    }
    $profileDirectory = Get-DsbProfileDirectory -ProjectRoot $ProjectRoot
    [System.IO.Directory]::CreateDirectory($profileDirectory) | Out-Null
    $profilePath = Get-DsbProfilePath -ProjectRoot $ProjectRoot -Name $Name
    if ((Test-Path -LiteralPath $profilePath -PathType Leaf) -and -not $Force) {
        throw "Profile already exists: $profilePath. Pass -Force to replace it."
    }
    $projectId = Get-DsbProjectId -ProjectRoot $ProjectRoot
    if ([string]::IsNullOrWhiteSpace($CredentialTarget)) {
        $CredentialTarget = "database-schema-bootstrap/$projectId/postgres/$DatabaseHost/$Database/$DatabaseUser"
    }
    $profile = [ordered]@{
        db_type = 'postgres'
        host = $DatabaseHost
        port = $Port
        database = $Database
        connection_database = $ConnectionDatabase
        schema = $Schema
        user = $DatabaseUser
        credential_target = $CredentialTarget
        target_tables = @($TargetTables)
    }
    Write-DsbJsonFile -Path $profilePath -Value $profile
    Register-DsbInstallRecord -RuntimeRoot $RuntimeRoot -Collection 'managed_profiles' -Key 'path' -KeyValue (Get-DsbNormalizedPath -Path $profilePath) -Record ([pscustomobject]@{
        path = (Get-DsbNormalizedPath -Path $profilePath)
        sha256 = (Get-DsbSha256File -Path $profilePath)
        project_root = (Get-DsbNormalizedPath -Path $ProjectRoot)
        project_id = $projectId
        name = $Name
    })
    return [pscustomobject]@{ Name = $Name; Path = $profilePath; CredentialTarget = $CredentialTarget }
}

function Get-DsbProjectProfile {
    param(
        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [Parameter(Mandatory)]
        [string]$Name
    )

    $profilePath = Get-DsbProfilePath -ProjectRoot $ProjectRoot -Name $Name
    if (-not (Test-Path -LiteralPath $profilePath -PathType Leaf)) {
        throw "Profile was not found: $Name"
    }
    return [pscustomobject]@{ Name = $Name; Path = $profilePath; Value = (Read-DsbJsonFile -Path $profilePath) }
}

function Get-DsbProjectProfiles {
    param(
        [Parameter(Mandatory)]
        [string]$ProjectRoot
    )

    $profileDirectory = Get-DsbProfileDirectory -ProjectRoot $ProjectRoot
    if (-not (Test-Path -LiteralPath $profileDirectory -PathType Container)) {
        return @()
    }
    $selected = Resolve-DsbSelectedProfile -ProjectRoot $ProjectRoot
    return @(
        Get-ChildItem -LiteralPath $profileDirectory -Filter '*.json' -File |
            Where-Object { $_.Name -ne 'active-profile.json' } |
            Sort-Object Name |
            ForEach-Object {
                [pscustomobject]@{
                    Name = $_.BaseName
                    Path = $_.FullName
                    Active = ($null -ne $selected -and $_.BaseName -eq $selected.Name)
                }
            }
    )
}

function Set-DsbActiveProfile {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [Parameter(Mandatory)]
        [string]$Name,

        [System.Diagnostics.Stopwatch]$Deadline
    )

    $profile = Get-DsbProjectProfile -ProjectRoot $ProjectRoot -Name $Name
    $activePath = Get-DsbActiveProfilePath -ProjectRoot $ProjectRoot
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($activePath)) | Out-Null
    Write-DsbJsonFile -Path $activePath -Value ([ordered]@{
        version = 1
        name = $profile.Name
        updated_at = [DateTime]::UtcNow.ToString('o')
    })
    Register-DsbInstallRecord -RuntimeRoot $RuntimeRoot -Collection 'managed_active_profiles' -Key 'path' -KeyValue (Get-DsbNormalizedPath -Path $activePath) -Record ([pscustomobject]@{
        path = (Get-DsbNormalizedPath -Path $activePath)
        sha256 = (Get-DsbSha256File -Path $activePath)
        project_root = (Get-DsbNormalizedPath -Path $ProjectRoot)
        project_id = (Get-DsbProjectId -ProjectRoot $ProjectRoot)
    }) -Deadline $Deadline
    return $profile
}

function Initialize-DsbCredentialInterop {
    if ($null -ne ('DsbSchemaBootstrap.CredentialNative' -as [type])) {
        return
    }
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

namespace DsbSchemaBootstrap
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct Credential
    {
        public UInt32 Flags;
        public UInt32 Type;
        public string TargetName;
        public string Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public UInt32 CredentialBlobSize;
        public IntPtr CredentialBlob;
        public UInt32 Persist;
        public UInt32 AttributeCount;
        public IntPtr Attributes;
        public string TargetAlias;
        public string UserName;
    }

    public static class CredentialNative
    {
        [DllImport("Advapi32.dll", EntryPoint = "CredWriteW", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern bool CredWrite(ref Credential credential, UInt32 flags);

        [DllImport("Advapi32.dll", EntryPoint = "CredDeleteW", SetLastError = true, CharSet = CharSet.Unicode)]
        public static extern bool CredDelete(string target, UInt32 type, UInt32 flags);
    }
}
'@
}

function Set-DsbWindowsCredential {
    param(
        [Parameter(Mandatory)]
        [string]$Target,

        [string]$UserName = 'database-schema-bootstrap',

        [System.Security.SecureString]$SecureSecret
    )

    Initialize-DsbCredentialInterop
    if ($null -eq $SecureSecret) {
        $SecureSecret = Read-Host -Prompt "Database password for credential target '$Target'" -AsSecureString
    }
    if ($null -eq $SecureSecret -or $SecureSecret.Length -eq 0) {
        throw 'Password cannot be empty.'
    }
    $bstr = [IntPtr]::Zero
    $blob = [IntPtr]::Zero
    $secretBytes = @()
    try {
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSecret)
        $secretText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        $secretBytes = [System.Text.Encoding]::Unicode.GetBytes($secretText)
        $blob = [Runtime.InteropServices.Marshal]::AllocHGlobal($secretBytes.Length)
        [Runtime.InteropServices.Marshal]::Copy($secretBytes, 0, $blob, $secretBytes.Length)
        $credential = [DsbSchemaBootstrap.Credential]::new()
        $credential.Type = 1
        $credential.TargetName = $Target
        $credential.CredentialBlobSize = [uint32]$secretBytes.Length
        $credential.CredentialBlob = $blob
        $credential.Persist = 2
        $credential.UserName = $UserName
        if (-not [DsbSchemaBootstrap.CredentialNative]::CredWrite([ref]$credential, 0)) {
            $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            throw [ComponentModel.Win32Exception]::new($code)
        }
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
        if ($blob -ne [IntPtr]::Zero) {
            for ($index = 0; $index -lt $secretBytes.Length; $index++) {
                [Runtime.InteropServices.Marshal]::WriteByte($blob, $index, 0)
            }
            [Runtime.InteropServices.Marshal]::FreeHGlobal($blob)
        }
        if ($secureSecret -is [IDisposable]) {
            $secureSecret.Dispose()
        }
    }
}

function Remove-DsbWindowsCredential {
    param(
        [Parameter(Mandatory)]
        [string]$Target
    )

    Initialize-DsbCredentialInterop
    if (-not [DsbSchemaBootstrap.CredentialNative]::CredDelete($Target, 1, 0)) {
        $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        if ($code -ne 1168) {
            throw [ComponentModel.Win32Exception]::new($code)
        }
    }
}

function ConvertTo-DsbProcessArgument {
    param(
        [Parameter(Mandatory)]
        [string]$Value
    )

    if ($Value -notmatch '[\s"]') {
        return $Value
    }
    $escaped = $Value -replace '(\\*)"', '$1$1\\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Test-DsbOwnedServiceProcess {
    param(
        [Parameter(Mandatory)]
        [int]$ServiceProcessId,

        [Parameter(Mandatory)]
        [string]$ServiceScript,

        [Parameter(Mandatory)]
        [string]$StatePath,

        [Parameter(Mandatory)]
        [string]$ProjectId,

        [Parameter(Mandatory)]
        [string]$InstanceToken
    )

    try {
        $process = Get-Process -Id $ServiceProcessId -ErrorAction Stop
        $processInfo = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $ServiceProcessId" -ErrorAction Stop
    }
    catch {
        return $false
    }
    $commandLine = Get-DsbObjectProperty -Object $processInfo -Name 'CommandLine'
    if ($null -eq $process -or $commandLine -isnot [string]) {
        return $false
    }
    return (
        $commandLine.IndexOf($ServiceScript, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $commandLine.IndexOf($StatePath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $commandLine.IndexOf('--project-id', [System.StringComparison]::Ordinal) -ge 0 -and
        $commandLine.IndexOf($ProjectId, [System.StringComparison]::Ordinal) -ge 0 -and
        $commandLine.IndexOf('--instance-token', [System.StringComparison]::Ordinal) -ge 0 -and
        $commandLine.IndexOf($InstanceToken, [System.StringComparison]::Ordinal) -ge 0
    )
}

function ConvertTo-DsbProcessCreationTimeUtc {
    param(
        [AllowNull()]
        [object]$Value
    )

    if ($null -eq $Value) {
        return $null
    }
    try {
        if ($Value -is [DateTime]) {
            return ([DateTime]$Value).ToUniversalTime().ToString('o')
        }
        if ($Value -is [string]) {
            try {
                return ([System.Management.ManagementDateTimeConverter]::ToDateTime($Value)).ToUniversalTime().ToString('o')
            }
            catch {
                return ([DateTime]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)).ToUniversalTime().ToString('o')
            }
        }
    }
    catch {
        return $null
    }
    return $null
}

function Get-DsbProcessSnapshot {
    param(
        [Parameter(Mandatory)]
        [int]$ServiceProcessId
    )

    try {
        $process = Get-Process -Id $ServiceProcessId -ErrorAction Stop
    }
    catch {
        return [pscustomobject]@{
            Exists = $false
            CommandLine = $null
            CommandLineSha256 = $null
            CreationTimeUtc = $null
        }
    }

    $processInfo = $null
    try {
        $processInfo = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $ServiceProcessId" -ErrorAction Stop
    }
    catch {
        return [pscustomobject]@{
            Exists = $true
            CommandLine = $null
            CommandLineSha256 = $null
            CreationTimeUtc = $null
        }
    }
    $commandLine = Get-DsbObjectProperty -Object $processInfo -Name 'CommandLine'
    $creationTimeUtc = ConvertTo-DsbProcessCreationTimeUtc -Value (Get-DsbObjectProperty -Object $processInfo -Name 'CreationDate')
    if ($null -eq $creationTimeUtc) {
        try {
            $creationTimeUtc = ([DateTime]$process.StartTime).ToUniversalTime().ToString('o')
        }
        catch {
            $creationTimeUtc = $null
        }
    }
    return [pscustomobject]@{
        Exists = $true
        CommandLine = if ($commandLine -is [string]) { $commandLine } else { $null }
        CommandLineSha256 = if ($commandLine -is [string]) { Get-DsbSha256String -Value $commandLine } else { $null }
        CreationTimeUtc = $creationTimeUtc
    }
}

function New-DsbOrphanServiceProcessRecord {
    param(
        [Parameter(Mandatory)]
        [object]$State,

        [Parameter(Mandatory)]
        [string]$StatePath,

        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [Parameter(Mandatory)]
        [string]$ProjectId,

        [Parameter(Mandatory)]
        [string]$ServiceScript,

        [Parameter(Mandatory)]
        [string]$Reason
    )

    $pidValue = 0
    if (-not [int]::TryParse([string](Get-DsbObjectProperty -Object $State -Name 'pid'), [ref]$pidValue) -or $pidValue -le 0) {
        return $null
    }
    $snapshot = Get-DsbProcessSnapshot -ServiceProcessId $pidValue
    if (-not $snapshot.Exists) {
        return $null
    }
    $instanceToken = Get-DsbObjectProperty -Object $State -Name 'instance_token'
    if ($instanceToken -isnot [string] -or [string]::IsNullOrWhiteSpace($instanceToken)) {
        $instanceToken = $null
    }
    return [pscustomobject][ordered]@{
        pid = $pidValue
        project_root = Get-DsbNormalizedPath -Path $ProjectRoot
        project_id = $ProjectId
        state_path = Get-DsbNormalizedPath -Path $StatePath
        instance_token = $instanceToken
        service_script = Get-DsbNormalizedPath -Path $ServiceScript
        command_line_sha256 = $snapshot.CommandLineSha256
        process_creation_time_utc = $snapshot.CreationTimeUtc
        observed_at = [DateTime]::UtcNow.ToString('o')
        reason = $Reason
    }
}

function Add-DsbOrphanServiceProcessRecord {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [object]$State,

        [Parameter(Mandatory)]
        [string]$StatePath,

        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [Parameter(Mandatory)]
        [string]$ProjectId,

        [Parameter(Mandatory)]
        [string]$ServiceScript,

        [Parameter(Mandatory)]
        [string]$Reason,

        [System.Diagnostics.Stopwatch]$Deadline
    )

    $record = New-DsbOrphanServiceProcessRecord -State $State -StatePath $StatePath -ProjectRoot $ProjectRoot -ProjectId $ProjectId -ServiceScript $ServiceScript -Reason $Reason
    if ($null -eq $record) {
        return $null
    }
    Invoke-DsbInstallStateLock -RuntimeRoot $RuntimeRoot -Deadline $Deadline -Action {
        $installState = Get-DsbInstallState -RuntimeRoot $RuntimeRoot -Required
        $records = @((Get-DsbObjectProperty -Object $installState -Name 'orphan_service_processes' -Default @()))
        $sameRecord = @($records | Where-Object {
            (Get-DsbObjectProperty -Object $_ -Name 'pid') -eq $record.pid -and
            (Get-DsbObjectProperty -Object $_ -Name 'state_path') -eq $record.state_path -and
            (Get-DsbObjectProperty -Object $_ -Name 'process_creation_time_utc') -eq $record.process_creation_time_utc
        })
        if ($sameRecord.Count -eq 0) {
            $records += $record
        }
        else {
            $records = @($records | ForEach-Object {
                if ($_ -eq $sameRecord[0]) { $record } else { $_ }
            })
        }
        Set-DsbObjectProperty -Object $installState -Name 'orphan_service_processes' -Value @($records)
        Save-DsbInstallState -RuntimeRoot $RuntimeRoot -State $installState
    }
    return $record
}

function Test-DsbOrphanServiceProcessIdentity {
    param(
        [Parameter(Mandatory)]
        [object]$Record,

        [Parameter(Mandatory)]
        [object]$Snapshot
    )

    if (-not $Snapshot.Exists -or $Snapshot.CommandLine -isnot [string] -or [string]::IsNullOrWhiteSpace($Snapshot.CommandLine)) {
        return $false
    }
    $expectedHash = Get-DsbObjectProperty -Object $Record -Name 'command_line_sha256'
    $expectedCreation = Get-DsbObjectProperty -Object $Record -Name 'process_creation_time_utc'
    $statePath = Get-DsbObjectProperty -Object $Record -Name 'state_path'
    $serviceScript = Get-DsbObjectProperty -Object $Record -Name 'service_script'
    $projectId = Get-DsbObjectProperty -Object $Record -Name 'project_id'
    if ($expectedHash -isnot [string] -or [string]::IsNullOrWhiteSpace($expectedHash) -or $expectedCreation -isnot [string] -or [string]::IsNullOrWhiteSpace($expectedCreation) -or $statePath -isnot [string] -or $serviceScript -isnot [string] -or $projectId -isnot [string]) {
        return $false
    }
    return (
        $expectedHash -ceq $Snapshot.CommandLineSha256 -and
        $expectedCreation -ceq $Snapshot.CreationTimeUtc -and
        $Snapshot.CommandLine.IndexOf($serviceScript, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $Snapshot.CommandLine.IndexOf($statePath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $Snapshot.CommandLine.IndexOf('--project-id', [System.StringComparison]::Ordinal) -ge 0 -and
        $Snapshot.CommandLine.IndexOf($projectId, [System.StringComparison]::Ordinal) -ge 0
    )
}

function Reap-DsbOrphanServiceProcesses {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectId,

        [System.Diagnostics.Stopwatch]$Deadline
    )

    if ($null -eq $Deadline) {
        $Deadline = New-DsbLifecycleDeadline
    }
    $resultList = [System.Collections.Generic.List[object]]::new()
    Invoke-DsbInstallStateLock -RuntimeRoot $RuntimeRoot -Deadline $Deadline -Action {
        $installState = Get-DsbInstallState -RuntimeRoot $RuntimeRoot -Required
        $allRecords = @((Get-DsbObjectProperty -Object $installState -Name 'orphan_service_processes' -Default @()))
        $remainingRecords = @()
        $serviceStateRecordsToRemove = [System.Collections.Generic.List[object]]::new()
        foreach ($record in $allRecords) {
            if ((Get-DsbObjectProperty -Object $record -Name 'project_id') -ne $ProjectId) {
                $remainingRecords += $record
                continue
            }
            $pidValue = 0
            if (-not [int]::TryParse([string](Get-DsbObjectProperty -Object $record -Name 'pid'), [ref]$pidValue) -or $pidValue -le 0) {
                $remainingRecords += $record
                [void]$resultList.Add([pscustomobject]@{ Status = 'Unverified'; Pid = (Get-DsbObjectProperty -Object $record -Name 'pid'); Record = $record })
                continue
            }
            $snapshot = Get-DsbProcessSnapshot -ServiceProcessId $pidValue
            if (-not $snapshot.Exists) {
                [void]$resultList.Add([pscustomobject]@{ Status = 'Stale'; Pid = $pidValue; Record = $record })
                $statePath = Get-DsbObjectProperty -Object $record -Name 'state_path'
                if ($statePath -is [string]) {
                    try {
                        $statePathKey = (Get-DsbNormalizedPath -Path $statePath).ToLowerInvariant()
                        $instanceToken = Get-DsbObjectProperty -Object $record -Name 'instance_token'
                        if ($instanceToken -is [string] -and -not [string]::IsNullOrWhiteSpace($instanceToken)) {
                            [void]$serviceStateRecordsToRemove.Add([pscustomobject]@{
                                path_key = $statePathKey
                                instance_token = $instanceToken
                                legacy = $false
                            })
                        }
                        elseif (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
                            [void]$serviceStateRecordsToRemove.Add([pscustomobject]@{
                                path_key = $statePathKey
                                instance_token = $null
                                legacy = $true
                            })
                        }
                    }
                    catch {
                        # An invalid path cannot identify a managed record; the
                        # orphan result remains available for fail-closed handling.
                    }
                }
                continue
            }
            if (-not (Test-DsbOrphanServiceProcessIdentity -Record $record -Snapshot $snapshot)) {
                $remainingRecords += $record
                [void]$resultList.Add([pscustomobject]@{ Status = 'Unverified'; Pid = $pidValue; Record = $record })
                continue
            }
            $latestSnapshot = Get-DsbProcessSnapshot -ServiceProcessId $pidValue
            if (-not (Test-DsbOrphanServiceProcessIdentity -Record $record -Snapshot $latestSnapshot)) {
                $remainingRecords += $record
                [void]$resultList.Add([pscustomobject]@{ Status = 'Unverified'; Pid = $pidValue; Record = $record })
                continue
            }
            try {
                Stop-Process -Id $pidValue -Force -ErrorAction Stop
                while ($true) {
                    if (-not (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
                        break
                    }
                    $remaining = Get-DsbRemainingLifecycleMilliseconds -Deadline $Deadline
                    if ($remaining -le 0) {
                        break
                    }
                    Start-Sleep -Milliseconds ([Math]::Min(100, [Math]::Max(1, $remaining)))
                }
            }
            catch {
                $remainingRecords += $record
                [void]$resultList.Add([pscustomobject]@{ Status = 'Unverified'; Pid = $pidValue; Record = $record })
                continue
            }
            if (Get-Process -Id $pidValue -ErrorAction SilentlyContinue) {
                $remainingRecords += $record
                [void]$resultList.Add([pscustomobject]@{ Status = 'Unverified'; Pid = $pidValue; Record = $record })
            }
            else {
                [void]$resultList.Add([pscustomobject]@{ Status = 'Reaped'; Pid = $pidValue; Record = $record })
                $statePath = Get-DsbObjectProperty -Object $record -Name 'state_path'
                if ($statePath -is [string]) {
                    try {
                        $statePathKey = (Get-DsbNormalizedPath -Path $statePath).ToLowerInvariant()
                        $instanceToken = Get-DsbObjectProperty -Object $record -Name 'instance_token'
                        if ($instanceToken -is [string] -and -not [string]::IsNullOrWhiteSpace($instanceToken)) {
                            [void]$serviceStateRecordsToRemove.Add([pscustomobject]@{
                                path_key = $statePathKey
                                instance_token = $instanceToken
                                legacy = $false
                            })
                        }
                        elseif (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
                            [void]$serviceStateRecordsToRemove.Add([pscustomobject]@{
                                path_key = $statePathKey
                                instance_token = $null
                                legacy = $true
                            })
                        }
                    }
                    catch {
                        # An invalid path cannot identify a managed record; the
                        # orphan result remains available for fail-closed handling.
                    }
                }
            }
        }
        if ($serviceStateRecordsToRemove.Count -gt 0) {
            $serviceStateRecords = @((Get-DsbObjectProperty -Object $installState -Name 'service_state_files' -Default @()))
            $serviceStateRecords = @($serviceStateRecords | Where-Object {
                $recordPath = Get-DsbObjectProperty -Object $_ -Name 'path'
                if ($recordPath -isnot [string]) {
                    return $true
                }
                try {
                    $recordPathKey = (Get-DsbNormalizedPath -Path $recordPath).ToLowerInvariant()
                    $recordInstanceToken = Get-DsbObjectProperty -Object $_ -Name 'instance_token'
                    foreach ($removal in $serviceStateRecordsToRemove) {
                        if ($removal.path_key -ne $recordPathKey) {
                            continue
                        }
                        if ($removal.legacy) {
                            return $false
                        }
                        if ($recordInstanceToken -is [string] -and $recordInstanceToken -ceq $removal.instance_token) {
                            return $false
                        }
                    }
                    return $true
                }
                catch {
                    return $true
                }
            })
            Set-DsbObjectProperty -Object $installState -Name 'service_state_files' -Value @($serviceStateRecords)
        }
        Set-DsbObjectProperty -Object $installState -Name 'orphan_service_processes' -Value @($remainingRecords)
        Save-DsbInstallState -RuntimeRoot $RuntimeRoot -State $installState
    }
    return @($resultList.ToArray())
}

function Remove-DsbServiceState {
    param(
        [Parameter(Mandatory)]
        [string]$StatePath,

        [AllowNull()]
        [string]$ExpectedInstanceToken
    )

    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
        return $false
    }
    if ($null -ne $ExpectedInstanceToken) {
        $state = Get-DsbRawServiceState -StatePath $StatePath
        if ($null -eq $state -or (Get-DsbObjectProperty -Object $state -Name 'instance_token') -cne $ExpectedInstanceToken) {
            return $false
        }
    }
    Remove-Item -LiteralPath $StatePath -Force
    return $true
}

function Stop-DsbProjectServiceInternal {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [Parameter(Mandatory)]
        [System.Diagnostics.Stopwatch]$Deadline
    )

    $projectId = Get-DsbProjectId -ProjectRoot $ProjectRoot
    $statePath = Get-DsbServiceStatePath -RuntimeRoot $RuntimeRoot -ProjectId $projectId
    $state = Get-DsbRawServiceState -StatePath $statePath
    $serviceScript = Join-Path $RuntimeRoot 'service\server.py'
    if (-not (Test-DsbServiceStateForProject -State $state -ProjectRoot $ProjectRoot -ProjectId $projectId)) {
        $stateProcessExists = $false
        if ($null -ne $state) {
            $snapshotPid = 0
            if ([int]::TryParse([string](Get-DsbObjectProperty -Object $state -Name 'pid'), [ref]$snapshotPid) -and $snapshotPid -gt 0) {
                $snapshot = Get-DsbProcessSnapshot -ServiceProcessId $snapshotPid
                if ($snapshot.Exists) {
                    $stateProcessExists = $true
                    Add-DsbOrphanServiceProcessRecord -RuntimeRoot $RuntimeRoot -State $state -StatePath $statePath -ProjectRoot $ProjectRoot -ProjectId $projectId -ServiceScript $serviceScript -Reason 'state-invalid' -Deadline $Deadline | Out-Null
                }
            }
        }
        Remove-DsbServiceState -StatePath $statePath -ExpectedInstanceToken $null | Out-Null
        if (-not $stateProcessExists) {
            Unregister-DsbInstallRecord -RuntimeRoot $RuntimeRoot -Collection 'service_state_files' -Key 'path' -KeyValue (Get-DsbNormalizedPath -Path $statePath) -Deadline $Deadline
        }
        return $false
    }
    $pidValue = Get-DsbObjectProperty -Object $state -Name 'pid'
    $serviceProcessId = [int]$pidValue
    $instanceToken = [string](Get-DsbObjectProperty -Object $state -Name 'instance_token')
    $process = Get-Process -Id $serviceProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        Remove-DsbServiceState -StatePath $statePath -ExpectedInstanceToken $instanceToken | Out-Null
        Unregister-DsbInstallRecord -RuntimeRoot $RuntimeRoot -Collection 'service_state_files' -Key 'path' -KeyValue (Get-DsbNormalizedPath -Path $statePath) -Deadline $Deadline
        return $false
    }
    if (-not (Test-DsbOwnedServiceProcess -ServiceProcessId $serviceProcessId -ServiceScript $serviceScript -StatePath $statePath -ProjectId $projectId -InstanceToken $instanceToken)) {
        Add-DsbOrphanServiceProcessRecord -RuntimeRoot $RuntimeRoot -State $state -StatePath $statePath -ProjectRoot $ProjectRoot -ProjectId $projectId -ServiceScript $serviceScript -Reason 'ownership-mismatch' -Deadline $Deadline | Out-Null
        Remove-DsbServiceState -StatePath $statePath -ExpectedInstanceToken $instanceToken | Out-Null
        return $false
    }
    Stop-Process -Id $serviceProcessId -Force -ErrorAction Stop
    while ($true) {
        if ($null -eq (Get-Process -Id $serviceProcessId -ErrorAction SilentlyContinue)) {
            break
        }
        $remaining = Assert-DsbLifecycleTimeRemaining -Deadline $Deadline
        Start-Sleep -Milliseconds ([Math]::Min(100, [Math]::Max(1, $remaining)))
    }
    Remove-DsbServiceState -StatePath $statePath -ExpectedInstanceToken $instanceToken | Out-Null
    Unregister-DsbInstallRecord -RuntimeRoot $RuntimeRoot -Collection 'service_state_files' -Key 'path' -KeyValue (Get-DsbNormalizedPath -Path $statePath) -Deadline $Deadline
    return $true
}

function Start-DsbProjectServiceInternal {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [Parameter(Mandatory)]
        [System.Diagnostics.Stopwatch]$Deadline
    )

    $projectId = Get-DsbProjectId -ProjectRoot $ProjectRoot
    Get-DsbInstallState -RuntimeRoot $RuntimeRoot -Required | Out-Null
    try {
        Reap-DsbOrphanServiceProcesses -RuntimeRoot $RuntimeRoot -ProjectId $projectId -Deadline $Deadline | Out-Null
    }
    catch {
        # A live or unverifiable orphan remains recorded, but must not block a
        # fresh verified instance for this session.
    }
    $selected = Resolve-DsbSelectedProfile -ProjectRoot $ProjectRoot
    if ($null -eq $selected) {
        return [pscustomobject]@{ Status = 'not-configured'; ProjectRoot = $ProjectRoot; ActiveProfile = $null }
    }
    return Invoke-DsbInstallStateLock -RuntimeRoot $RuntimeRoot -Deadline $Deadline -Action {
        $installState = Get-DsbInstallState -RuntimeRoot $RuntimeRoot -Required
        $pythonPath = Get-DsbObjectProperty -Object $installState -Name 'python_path'
        if ($pythonPath -isnot [string] -or -not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
            throw 'The installed Python path is unavailable. Re-run install.ps1 with -PythonPath.'
        }
        $statePath = Get-DsbServiceStatePath -RuntimeRoot $RuntimeRoot -ProjectId $projectId
        $existingState = Get-DsbValidatedServiceState -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot
        if ($null -ne $existingState -and (Invoke-DsbServiceHealth -State $existingState -ProjectId $projectId -TimeoutMilliseconds ([Math]::Min(2000, (Assert-DsbLifecycleTimeRemaining -Deadline $Deadline))))) {
            return Get-DsbServiceStatus -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Deadline $Deadline
        }
        if (Test-Path -LiteralPath $statePath -PathType Leaf) {
            Stop-DsbProjectServiceInternal -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Deadline $Deadline | Out-Null
        }

        $serviceScript = Join-Path $RuntimeRoot 'service\server.py'
        if (-not (Test-Path -LiteralPath $serviceScript -PathType Leaf)) {
            throw "Installed metadata service is missing: $serviceScript"
        }
        $stateDirectory = [System.IO.Path]::GetDirectoryName($statePath)
        $logDirectory = Join-Path $RuntimeRoot 'logs'
        [System.IO.Directory]::CreateDirectory($stateDirectory) | Out-Null
        [System.IO.Directory]::CreateDirectory($logDirectory) | Out-Null
        $instanceToken = [Guid]::NewGuid().ToString('N')
        $stdoutLog = Join-Path $logDirectory ($projectId + '.stdout.log')
        $stderrLog = Join-Path $logDirectory ($projectId + '.stderr.log')
        Assert-DsbLifecycleTimeRemaining -Deadline $Deadline | Out-Null
        $arguments = @(
            '-B',
            $serviceScript,
            '--config', $selected.Path,
            '--port', '0',
            '--instance-token', $instanceToken,
            '--ready-state', $statePath,
            '--project-id', $projectId,
            '--project-root', (Get-DsbNormalizedPath -Path $ProjectRoot)
        )
        $argumentLine = (@($arguments | ForEach-Object { ConvertTo-DsbProcessArgument -Value $_ })) -join ' '
        $process = $null
        try {
            $process = Start-Process -FilePath $pythonPath -ArgumentList $argumentLine -WorkingDirectory $RuntimeRoot -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -WindowStyle Hidden -PassThru
            while ($true) {
                $remaining = Assert-DsbLifecycleTimeRemaining -Deadline $Deadline
                Start-Sleep -Milliseconds ([Math]::Min(100, [Math]::Max(1, $remaining)))
                $candidate = Get-DsbValidatedServiceState -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot
                if ($null -ne $candidate -and (Invoke-DsbServiceHealth -State $candidate -ProjectId $projectId -TimeoutMilliseconds ([Math]::Min(2000, (Assert-DsbLifecycleTimeRemaining -Deadline $Deadline))))) {
                    Register-DsbInstallRecord -RuntimeRoot $RuntimeRoot -Collection 'service_state_files' -Key 'path' -KeyValue (Get-DsbNormalizedPath -Path $statePath) -Record ([pscustomobject]@{
                        path = (Get-DsbNormalizedPath -Path $statePath)
                        sha256 = Get-DsbSha256File -Path $statePath
                        project_root = (Get-DsbNormalizedPath -Path $ProjectRoot)
                        project_id = $projectId
                        instance_token = Get-DsbObjectProperty -Object $candidate -Name 'instance_token'
                    }) -Deadline $Deadline
                    return Get-DsbServiceStatus -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Deadline $Deadline
                }
                if ($null -eq (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
                    throw "Metadata service exited during startup. Inspect logs at: $logDirectory"
                }
            }
        }
        catch {
            $startupError = $_
            $failureState = Get-DsbRawServiceState -StatePath $statePath
            $ownedFailureState = $null -ne $failureState -and (Get-DsbObjectProperty -Object $failureState -Name 'instance_token') -ceq $instanceToken
            try {
                if ($null -ne $process -and $null -ne (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
                    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                    while ($null -ne (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
                        $remaining = Get-DsbRemainingLifecycleMilliseconds -Deadline $Deadline
                        if ($remaining -le 0) {
                            break
                        }
                        Start-Sleep -Milliseconds ([Math]::Min(100, [Math]::Max(1, $remaining)))
                    }
                }
            }
            catch {
                # Preserve the startup failure while still attempting state cleanup.
            }
            $latestFailureState = Get-DsbRawServiceState -StatePath $statePath
            if ($null -ne $latestFailureState -and (Get-DsbObjectProperty -Object $latestFailureState -Name 'instance_token') -ceq $instanceToken) {
                $failureState = $latestFailureState
                $ownedFailureState = $true
            }
            if ($ownedFailureState) {
                Remove-DsbServiceState -StatePath $statePath -ExpectedInstanceToken $instanceToken | Out-Null
            }
            $remainingProcess = if ($null -eq $process) { $null } else { Get-Process -Id $process.Id -ErrorAction SilentlyContinue }
            if ($null -ne $remainingProcess) {
                $orphanState = if ($ownedFailureState) {
                    $failureState
                }
                else {
                    [pscustomobject]@{ pid = $process.Id }
                }
                try {
                    Add-DsbOrphanServiceProcessRecord -RuntimeRoot $RuntimeRoot -State $orphanState -StatePath $statePath -ProjectRoot $ProjectRoot -ProjectId $projectId -ServiceScript $serviceScript -Reason 'startup-failure' -Deadline (New-DsbLifecycleDeadline) | Out-Null
                }
                catch {
                    # The original startup error is more actionable; the process
                    # remains discoverable by its command line if registration is
                    # temporarily unavailable.
                }
            }
            throw $startupError
        }
    }
}

function Restart-DsbProjectServiceInternal {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [Parameter(Mandatory)]
        [System.Diagnostics.Stopwatch]$Deadline
    )

    Stop-DsbProjectServiceInternal -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Deadline $Deadline | Out-Null
    return Start-DsbProjectServiceInternal -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Deadline $Deadline
}

function Stop-DsbProjectService {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot
    )

    return Invoke-DsbProjectLifecycle -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Action {
        param($deadline)
        Stop-DsbProjectServiceInternal -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Deadline $deadline
    }
}

function Start-DsbProjectService {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot
    )

    return Invoke-DsbProjectLifecycle -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Action {
        param($deadline)
        Start-DsbProjectServiceInternal -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Deadline $deadline
    }
}

function Restart-DsbProjectService {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot
    )

    return Invoke-DsbProjectLifecycle -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Action {
        param($deadline)
        Restart-DsbProjectServiceInternal -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Deadline $deadline
    }
}

function Use-DsbProjectProfile {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [Parameter(Mandatory)]
        [string]$Name
    )

    return Invoke-DsbProjectLifecycle -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Action {
        param($deadline)
        Set-DsbActiveProfile -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Name $Name -Deadline $deadline | Out-Null
        Restart-DsbProjectServiceInternal -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot -Deadline $deadline
    }
}

function Remove-DsbProjectProfileRecord {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectRoot,

        [Parameter(Mandatory)]
        [object]$Profile
    )

    $projectId = Get-DsbProjectId -ProjectRoot $ProjectRoot
    $statePath = Get-DsbServiceStatePath -RuntimeRoot $RuntimeRoot -ProjectId $projectId

    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        Stop-DsbProjectService -RuntimeRoot $RuntimeRoot -ProjectRoot $ProjectRoot | Out-Null
    }

    $profilePath = Get-DsbProfilePath -ProjectRoot $ProjectRoot -Name $Profile.Name
    $profileValue = Read-DsbJsonFile -Path $profilePath
    if ($null -ne $profileValue) {
        $target = Get-DsbObjectProperty -Object $profileValue -Name 'credential_target'
        if ($target -is [string] -and -not [string]::IsNullOrWhiteSpace($target)) {
            Remove-DsbWindowsCredential -Target $target
            Unregister-DsbInstallRecord -RuntimeRoot $RuntimeRoot -Collection 'credential_targets' -Key 'target' -KeyValue $target | Out-Null
        }
    }

    $activePath = Get-DsbActiveProfilePath -ProjectRoot $ProjectRoot
    $active = Read-DsbJsonFile -Path $activePath
    if ($null -ne $active -and (Get-DsbObjectProperty -Object $active -Name 'name') -eq $Profile.Name) {
        Remove-Item -LiteralPath $activePath -Force -ErrorAction SilentlyContinue
        Unregister-DsbInstallRecord -RuntimeRoot $RuntimeRoot -Collection 'managed_active_profiles' -Key 'path' -KeyValue (Get-DsbNormalizedPath -Path $activePath) | Out-Null
    }

    if (Test-Path -LiteralPath $profilePath -PathType Leaf) {
        Remove-Item -LiteralPath $profilePath -Force
    }
    Unregister-DsbInstallRecord -RuntimeRoot $RuntimeRoot -Collection 'managed_profiles' -Key 'path' -KeyValue (Get-DsbNormalizedPath -Path $profilePath) | Out-Null
}

Export-ModuleMember -Function @(
    'Get-DsbObjectProperty',
    'Set-DsbObjectProperty',
    'Write-DsbAtomicUtf8File',
    'Read-DsbJsonFile',
    'Write-DsbJsonFile',
    'Get-DsbSha256File',
    'Get-DsbSha256String',
    'Get-DsbCodexHome',
    'Get-DsbRuntimeRoot',
    'Invoke-DsbProjectLocksThenInstallState',
    'Resolve-DsbPython',
    'Get-DsbNormalizedPath',
    'Get-DsbProjectRoot',
    'Get-DsbProjectId',
    'Test-DsbPathWithin',
    'Assert-DsbProfileName',
    'Get-DsbProfileDirectory',
    'Get-DsbProfilePath',
    'Get-DsbActiveProfilePath',
    'Resolve-DsbSelectedProfile',
    'Get-DsbInstallStatePath',
    'Get-DsbInstallState',
    'Save-DsbInstallState',
    'Register-DsbInstallRecord',
    'Unregister-DsbInstallRecord',
    'ConvertTo-DsbTomlString',
    'Get-DsbManagedConfigBlockInfo',
    'Set-DsbManagedConfigBlock',
    'New-DsbManagedConfigBlock',
    'Get-DsbServiceStatePath',
    'Get-DsbRuntimeServiceProcesses',
    'Test-DsbLoopbackEndpoint',
    'Invoke-DsbServiceHealth',
    'Get-DsbRawServiceState',
    'Test-DsbServiceStateForProject',
    'Get-DsbValidatedServiceState',
    'Get-DsbServiceStatus',
    'Add-DsbProjectProfile',
    'Get-DsbProjectProfile',
    'Get-DsbProjectProfiles',
    'Set-DsbActiveProfile',
    'Set-DsbWindowsCredential',
    'Remove-DsbWindowsCredential',
    'Reap-DsbOrphanServiceProcesses',
    'Use-DsbProjectProfile',
    'Remove-DsbProjectProfileRecord',
    'Stop-DsbProjectService',
    'Start-DsbProjectService',
    'Restart-DsbProjectService'
)
