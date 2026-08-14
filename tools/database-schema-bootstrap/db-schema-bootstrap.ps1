[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('profile', 'status', 'session-start', 'session-stop', 'session-reap')]
    [string]$Command,

    [Parameter(Position = 1)]
    [string]$Action,

    [string]$ProjectPath,

    [string]$Name,

    [Alias('Host')]
    [string]$DatabaseHost,

    [string]$Database,

    [string]$ConnectionDatabase = 'postgres',

    [string]$DatabaseUser,

    [ValidateRange(1, 65535)]
    [int]$Port = 5432,

    [string]$Schema = 'public',

    [string]$CredentialTarget,

    [string[]]$TargetTables = @(),

    [string]$CodexHome,

    [string]$RuntimeRoot,

    [switch]$Force,

    [Parameter(ValueFromPipeline = $true)]
    [AllowEmptyString()]
    [string]$HookInput
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Import-Module (Join-Path $PSScriptRoot 'DbSchemaBootstrap.Common.psm1') -Force

function Get-DsbControlRuntimeRoot {
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

function Require-DsbValue {
    param(
        [string]$Value,
        [string]$ParameterName
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "-$ParameterName is required for this command."
    }
}

function Test-DsbSecureStringEqual {
    param(
        [Parameter(Mandatory)]
        [System.Security.SecureString]$A,

        [Parameter(Mandatory)]
        [System.Security.SecureString]$B
    )

    $aPtr = [IntPtr]::Zero
    $bPtr = [IntPtr]::Zero
    try {
        $aPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($A)
        $bPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($B)
        return (
            [Runtime.InteropServices.Marshal]::PtrToStringBSTR($aPtr) -ceq
            [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bPtr)
        )
    }
    finally {
        if ($aPtr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($aPtr)
        }
        if ($bPtr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bPtr)
        }
    }
}

function Invoke-DsbProfileAddWizard {
    param(
        [Parameter(Mandatory)]
        [string]$RuntimeRoot,

        [Parameter(Mandatory)]
        [string]$ProjectPath,

        [AllowEmptyString()]
        [string]$Name = ''
    )

    $projectRoot = Get-DsbProjectRoot -ProjectPath $ProjectPath

    Write-Host ''
    Write-Host '===== database-schema-bootstrap profile 添加向导 =====' -ForegroundColor Cyan
    Write-Host "项目根目录: $projectRoot"

    $defaultName = if ([string]::IsNullOrWhiteSpace($Name)) { 'default' } else { $Name }
    $name = Read-Host "profile 名称(直接回车使用默认: $defaultName)"
    if ([string]::IsNullOrWhiteSpace($name)) {
        $name = $defaultName
    }
    Assert-DsbProfileName -Name $name

    $hostValue = Read-Host '数据库主机(如 127.0.0.1)'
    while ([string]::IsNullOrWhiteSpace($hostValue)) {
        $hostValue = Read-Host '数据库主机不能为空,请重新输入'
    }

    $port = 5432
    $portText = Read-Host '端口(直接回车使用默认: 5432)'
    if (-not [string]::IsNullOrWhiteSpace($portText)) {
        if (-not [int]::TryParse($portText, [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
            throw "无效的端口: $portText"
        }
    }

    $database = Read-Host '目标数据库名(要探查 schema 的业务库)'
    while ([string]::IsNullOrWhiteSpace($database)) {
        $database = Read-Host '目标数据库名不能为空,请重新输入'
    }

    $connectionDatabase = Read-Host '入口连接库(直接回车使用默认: postgres)'
    if ([string]::IsNullOrWhiteSpace($connectionDatabase)) {
        $connectionDatabase = 'postgres'
    }

    $schema = Read-Host 'schema(直接回车使用默认: public)'
    if ([string]::IsNullOrWhiteSpace($schema)) {
        $schema = 'public'
    }

    $user = Read-Host '数据库用户'
    while ([string]::IsNullOrWhiteSpace($user)) {
        $user = Read-Host '数据库用户不能为空,请重新输入'
    }

    $password = Read-Host '数据库密码(隐藏输入,不会显示)' -AsSecureString
    if ($null -eq $password -or $password.Length -eq 0) {
        throw '密码不能为空。'
    }
    $confirmPassword = Read-Host '再次输入密码确认' -AsSecureString
    if ($null -eq $confirmPassword -or -not (Test-DsbSecureStringEqual -A $password -B $confirmPassword)) {
        throw '两次输入的密码不一致,请重新运行。'
    }

    $profile = Add-DsbProjectProfile -RuntimeRoot $RuntimeRoot -ProjectRoot $projectRoot -Name $name -DatabaseHost $hostValue -Database $database -ConnectionDatabase $connectionDatabase -DatabaseUser $user -Port $port -Schema $schema
    Set-DsbWindowsCredential -Target $profile.CredentialTarget -SecureSecret $password
    Register-DsbInstallRecord -RuntimeRoot $RuntimeRoot -Collection 'credential_targets' -Key 'target' -KeyValue $profile.CredentialTarget -Record ([pscustomobject]@{
        target = $profile.CredentialTarget
        project_root = (Get-DsbNormalizedPath -Path $projectRoot)
        project_id = (Get-DsbProjectId -ProjectRoot $projectRoot)
        profile = $name
        created_at = [DateTime]::UtcNow.ToString('o')
    })

    Write-Host ''
    Write-Host "profile '$name' 已保存并登录:" -ForegroundColor Green
    Write-Host "  配置文件 : $($profile.Path)"
    Write-Host "  连接     : $hostValue`:$port / 数据库 $database (入口库 $connectionDatabase, schema $schema)"
    Write-Host "  用户     : $user"
    Write-Host "  凭据目标 : $($profile.CredentialTarget)"

    $useNow = Read-Host '是否立即设为活动 profile 并启动服务?(y/N, 默认 N)'
    if ($useNow -match '^[yY]') {
        try {
            Use-DsbProjectProfile -RuntimeRoot $RuntimeRoot -ProjectRoot $projectRoot -Name $name | Out-Null
            Write-Host '已设为活动 profile 并启动服务。可用 & $dbs status -ProjectPath . 查看状态。' -ForegroundColor Green
        }
        catch {
            Write-Warning "设为活动 profile 失败(项目需是 Git 仓库): $($_.Exception.Message)"
        }
    }
    return $profile
}

function Resolve-DsbSessionStartProjectPath {
    param(
        [Parameter(Mandatory)]
        [bool]$HasExplicitProjectPath,

        [AllowEmptyCollection()]
        [object[]]$PipelineInput
    )

    if ($HasExplicitProjectPath) {
        return $ProjectPath
    }

    $fallbackPath = (Get-Location).Path
    $rawParts = @(
        $PipelineInput |
            ForEach-Object {
                if ($_ -is [string]) {
                    $_
                }
                else {
                    $_ | ConvertTo-Json -Compress -Depth 12
                }
            }
    )
    $rawInput = $rawParts -join [Environment]::NewLine
    if ([string]::IsNullOrWhiteSpace($rawInput) -and [Console]::IsInputRedirected) {
        $rawInput = [Console]::In.ReadToEnd()
    }
    if ([string]::IsNullOrWhiteSpace($rawInput)) {
        return $fallbackPath
    }

    try {
        $hookEvent = $rawInput | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw 'SessionStart hook input is invalid.'
    }
    $cwd = Get-DsbObjectProperty -Object $hookEvent -Name 'cwd'
    if ($null -eq $cwd) {
        return $fallbackPath
    }
    if ($cwd -isnot [string]) {
        throw 'SessionStart hook cwd is invalid.'
    }
    if ([string]::IsNullOrWhiteSpace($cwd)) {
        return $fallbackPath
    }
    return $cwd
}

$hasExplicitProjectPath = $PSBoundParameters.ContainsKey('ProjectPath')
$hookPipelineInput = @($input)
if ($hookPipelineInput.Count -eq 0 -and $PSBoundParameters.ContainsKey('HookInput')) {
    $hookPipelineInput = @($HookInput)
}
$sessionStartPipelineInput = if ($Command -eq 'session-start' -and -not $hasExplicitProjectPath) {
    $hookPipelineInput
}
else {
    @()
}

try {
    $effectiveRuntimeRoot = Get-DsbControlRuntimeRoot
    if (-not (Test-Path -LiteralPath (Get-DsbInstallStatePath -RuntimeRoot $effectiveRuntimeRoot) -PathType Leaf)) {
        throw "Global runtime is not installed: $effectiveRuntimeRoot"
    }
    $effectiveProjectPath = if ($Command -eq 'session-start') {
        Resolve-DsbSessionStartProjectPath -HasExplicitProjectPath $hasExplicitProjectPath -PipelineInput $sessionStartPipelineInput
    }
    elseif ($hasExplicitProjectPath) {
        $ProjectPath
    }
    else {
        (Get-Location).Path
    }

    switch ($Command) {
        'profile' {
            switch ($Action) {
                'add' {
                    if ([string]::IsNullOrWhiteSpace($Name) -or [string]::IsNullOrWhiteSpace($DatabaseHost) -or [string]::IsNullOrWhiteSpace($Database) -or [string]::IsNullOrWhiteSpace($DatabaseUser)) {
                        Invoke-DsbProfileAddWizard -RuntimeRoot $effectiveRuntimeRoot -ProjectPath $effectiveProjectPath -Name $Name | Out-Null
                    }
                    else {
                        Require-DsbValue -Value $Name -ParameterName 'Name'
                        Require-DsbValue -Value $DatabaseHost -ParameterName 'DatabaseHost'
                        Require-DsbValue -Value $Database -ParameterName 'Database'
                        Require-DsbValue -Value $ConnectionDatabase -ParameterName 'ConnectionDatabase'
                        Require-DsbValue -Value $DatabaseUser -ParameterName 'DatabaseUser'
                        $projectRoot = Get-DsbProjectRoot -ProjectPath $effectiveProjectPath
                        Add-DsbProjectProfile -RuntimeRoot $effectiveRuntimeRoot -ProjectRoot $projectRoot -Name $Name -DatabaseHost $DatabaseHost -Database $Database -ConnectionDatabase $ConnectionDatabase -DatabaseUser $DatabaseUser -Port $Port -Schema $Schema -CredentialTarget $CredentialTarget -TargetTables $TargetTables -Force:$Force
                    }
                }
                'login' {
                    Require-DsbValue -Value $Name -ParameterName 'Name'
                    $projectRoot = Get-DsbProjectRoot -ProjectPath $effectiveProjectPath
                    $profile = Get-DsbProjectProfile -ProjectRoot $projectRoot -Name $Name
                    $target = Get-DsbObjectProperty -Object $profile.Value -Name 'credential_target'
                    if ($target -isnot [string] -or [string]::IsNullOrWhiteSpace($target)) {
                        throw "Profile has no credential_target: $Name"
                    }
                    Set-DsbWindowsCredential -Target $target
                    Register-DsbInstallRecord -RuntimeRoot $effectiveRuntimeRoot -Collection 'credential_targets' -Key 'target' -KeyValue $target -Record ([pscustomobject]@{
                        target = $target
                        project_root = (Get-DsbNormalizedPath -Path $projectRoot)
                        project_id = (Get-DsbProjectId -ProjectRoot $projectRoot)
                        profile = $Name
                        created_at = [DateTime]::UtcNow.ToString('o')
                    })
                    Write-Output "Stored credential target for profile '$Name'."
                }
                'use' {
                    Require-DsbValue -Value $Name -ParameterName 'Name'
                    $projectRoot = Get-DsbProjectRoot -ProjectPath $effectiveProjectPath -RequireGit
                    Use-DsbProjectProfile -RuntimeRoot $effectiveRuntimeRoot -ProjectRoot $projectRoot -Name $Name
                }
                'remove' {
                    $projectRoot = Get-DsbProjectRoot -ProjectPath $effectiveProjectPath
                    $profiles = @(Get-DsbProjectProfiles -ProjectRoot $projectRoot)
                    if ($profiles.Count -eq 0) {
                        throw '该项目没有可删除的 profile。'
                    }
                    $selected = $null
                    if (-not [string]::IsNullOrWhiteSpace($Name)) {
                        $selected = @($profiles | Where-Object { $_.Name -eq $Name })[0]
                        if ($null -eq $selected) {
                            throw "profile 不存在: $Name"
                        }
                    }
                    else {
                        Write-Host '该项目下的 profile:'
                        for ($index = 0; $index -lt $profiles.Count; $index++) {
                            $activeMark = if ($profiles[$index].Active) { ' (当前活动)' } else { '' }
                            Write-Host ("  [{0}] {1}{2}" -f ($index + 1), $profiles[$index].Name, $activeMark)
                        }
                        $choiceText = Read-Host '输入序号选择要删除的 profile'
                        $choice = 0
                        if (-not [int]::TryParse($choiceText, [ref]$choice) -or $choice -lt 1 -or $choice -gt $profiles.Count) {
                            throw '无效的选择。'
                        }
                        $selected = $profiles[$choice - 1]
                    }
                    $confirm = Read-Host "确认删除 profile '$($selected.Name)'?将同时删除其凭据与服务状态。(y/N)"
                    if ($confirm -notmatch '^[yY]') {
                        Write-Output '已取消,未做任何修改。'
                    }
                    else {
                        Remove-DsbProjectProfileRecord -RuntimeRoot $effectiveRuntimeRoot -ProjectRoot $projectRoot -Profile $selected
                        Write-Output "profile '$($selected.Name)' 已删除,相关凭据与服务状态已清理。"
                    }
                }
                'list' {
                    $projectRoot = Get-DsbProjectRoot -ProjectPath $effectiveProjectPath
                    Get-DsbProjectProfiles -ProjectRoot $projectRoot
                }
                'status' {
                    $projectRoot = Get-DsbProjectRoot -ProjectPath $effectiveProjectPath
                    Get-DsbServiceStatus -RuntimeRoot $effectiveRuntimeRoot -ProjectRoot $projectRoot
                }
                default {
                    throw 'Use one of: profile add, profile login, profile use, profile list, profile status.'
                }
            }
        }
        'status' {
            $projectRoot = Get-DsbProjectRoot -ProjectPath $effectiveProjectPath
            Get-DsbServiceStatus -RuntimeRoot $effectiveRuntimeRoot -ProjectRoot $projectRoot
        }
        'session-start' {
            $projectRoot = Get-DsbProjectRoot -ProjectPath $effectiveProjectPath -RequireGit
            Start-DsbProjectService -RuntimeRoot $effectiveRuntimeRoot -ProjectRoot $projectRoot | Out-Null
        }
        'session-stop' {
            $projectRoot = Get-DsbProjectRoot -ProjectPath $effectiveProjectPath -RequireGit
            Stop-DsbProjectService -RuntimeRoot $effectiveRuntimeRoot -ProjectRoot $projectRoot | Out-Null
        }
        'session-reap' {
            $projectRoot = Get-DsbProjectRoot -ProjectPath $effectiveProjectPath -RequireGit
            $projectId = Get-DsbProjectId -ProjectRoot $projectRoot
            $reapResults = @(Reap-DsbOrphanServiceProcesses -RuntimeRoot $effectiveRuntimeRoot -ProjectId $projectId)
            if ($reapResults.Count -eq 0) {
                Write-Output 'No orphan service process records matched the current Git project.'
            }
            else {
                $reapResults | Select-Object Status, Pid | Format-Table -AutoSize | Out-Host
            }
            if (@($reapResults | Where-Object { $_.Status -eq 'Unverified' }).Count -gt 0) {
                $pids = @($reapResults | Where-Object { $_.Status -eq 'Unverified' } | ForEach-Object { $_.Pid }) -join ', '
                throw "Unable to verify orphan service process ownership; records were retained for PID(s): $pids"
            }
        }
    }
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
