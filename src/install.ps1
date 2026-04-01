[CmdletBinding()]
param(
    [Parameter()]
    [string]$RepoRoot = (Split-Path -Path $PSScriptRoot -Parent),

    [Parameter()]
    [string]$TemplatePath,

    [Parameter()]
    [string]$ProfilePath,

    [Parameter()]
    [switch]$Force,

    [Parameter()]
    [switch]$SkipFzfInstall
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$managedBlockStart = '# >>> getskill installer >>>'
$managedBlockEnd = '# <<< getskill installer <<<'

function Write-Step {
    param(
        [Parameter(Mandatory)]
        [string]$Message
    )

    Write-Host $Message -ForegroundColor Cyan
}

function Test-CommandExists {
    param(
        [Parameter(Mandatory)]
        [string]$Name
    )

    return $null -ne (Get-Command -Name $Name -ErrorAction SilentlyContinue)
}

function Get-DefaultProfilePath {
    if ($script:PSBoundParameters.ContainsKey('ProfilePath') -and $script:ProfilePath) {
        return $ProfilePath
    }

    if ($null -ne $PROFILE) {
        $currentUserCurrentHost = $PROFILE.PSObject.Properties['CurrentUserCurrentHost']
        if ($null -ne $currentUserCurrentHost -and $currentUserCurrentHost.Value) {
            return $currentUserCurrentHost.Value
        }

        if ([string]$PROFILE) {
            return [string]$PROFILE
        }
    }

    return Join-Path -Path ([Environment]::GetFolderPath('MyDocuments')) -ChildPath 'WindowsPowerShell\profile.ps1'
}

function Ensure-Fzf {
    Write-Step '[1/3] Checking fzf...'

    if (Test-CommandExists -Name 'fzf') {
        Write-Host '[OK] fzf is already installed.' -ForegroundColor Green
        return
    }

    if ($SkipFzfInstall) {
        throw "fzf was not found in PATH. Install it manually and rerun the installer."
    }

    if (-not (Test-CommandExists -Name 'winget')) {
        throw "fzf was not found and winget is unavailable. Install fzf manually, then rerun the installer."
    }

    Write-Host '[INFO] fzf not found. Installing via winget...' -ForegroundColor Yellow
    & winget install --id junegunn.fzf -e --accept-package-agreements --accept-source-agreements

    if ($LASTEXITCODE -ne 0) {
        throw "winget failed to install fzf (exit code $LASTEXITCODE)."
    }

    Write-Host '[OK] fzf installation finished. You may need to restart PowerShell before using it.' -ForegroundColor Green
}

function Get-TemplateContent {
    param(
        [Parameter(Mandatory)]
        [string]$ResolvedTemplatePath,

        [Parameter(Mandatory)]
        [string]$ResolvedRepoRoot
    )

    $template = Get-Content -LiteralPath $ResolvedTemplatePath -Raw -Encoding UTF8
    $skillsDirPattern = '(?m)^(\s*\$skillsDir\s*=\s*).*$'

    if ($template -notmatch $skillsDirPattern) {
        throw "The profile template does not contain a `$skillsDir assignment: $ResolvedTemplatePath"
    }

    $resolvedSkillsRoot = (Join-Path -Path $ResolvedRepoRoot -ChildPath '.agents\skills')
    $escapedSkillsRoot = $resolvedSkillsRoot.Replace("'", "''")
    return [regex]::Replace(
        $template,
        $skillsDirPattern,
        {
            param($match)
            '{0}''{1}''' -f $match.Groups[1].Value, $escapedSkillsRoot
        }
    )
}

function Get-FunctionNamesFromContent {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Content
    )

    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($Content, [ref]$tokens, [ref]$parseErrors)

    return @(
        $ast.FindAll(
            {
                param($node)
                $node -is [System.Management.Automation.Language.FunctionDefinitionAst]
            },
            $true
        ) | ForEach-Object { $_.Name }
    )
}

function Remove-FunctionsByName {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Content,

        [Parameter(Mandatory)]
        [string[]]$FunctionNames
    )

    $distinctFunctionNames = @($FunctionNames | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
    if ($distinctFunctionNames.Count -eq 0) {
        return @{
            Content = $Content
            Removed = $false
            RemovedNames = @()
        }
    }

    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($Content, [ref]$tokens, [ref]$parseErrors)
    $functionAsts = $ast.FindAll(
        {
            param($node)
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            ($distinctFunctionNames -icontains $node.Name)
        },
        $true
    )

    if (-not $functionAsts -or $functionAsts.Count -eq 0) {
        return @{
            Content = $Content
            Removed = $false
            RemovedNames = @()
        }
    }

    $updatedContent = $Content
    $removedNames = New-Object System.Collections.Generic.List[string]
    foreach ($functionAst in ($functionAsts | Sort-Object { $_.Extent.StartOffset } -Descending)) {
        $startOffset = $functionAst.Extent.StartOffset
        $endOffset = $functionAst.Extent.EndOffset
        $updatedContent = $updatedContent.Remove($startOffset, $endOffset - $startOffset)
        $removedNames.Add($functionAst.Name)
    }

    return @{
        Content = $updatedContent.Trim()
        Removed = $true
        RemovedNames = @($removedNames | Select-Object -Unique)
    }
}

function Set-ManagedProfileBlock {
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$ExistingContent,

        [Parameter(Mandatory)]
        [string]$ManagedContent,

        [Parameter(Mandatory)]
        [string[]]$ManagedFunctionNames
    )

    $managedBlock = @(
        $managedBlockStart
        $ManagedContent.Trim()
        $managedBlockEnd
    ) -join [Environment]::NewLine

    $blockPattern = '(?s)' + [regex]::Escape($managedBlockStart) + '.*?' + [regex]::Escape($managedBlockEnd)

    if ($ExistingContent -match $blockPattern) {
        $managedBlockRegex = [regex]::new($blockPattern)
        return $managedBlockRegex.Replace(
            $ExistingContent,
            { param($match) $managedBlock },
            1
        ).Trim() + [Environment]::NewLine
    }

    $withoutLegacy = Remove-FunctionsByName -Content $ExistingContent -FunctionNames $ManagedFunctionNames
    $contentAfterRemoval = $withoutLegacy.Content.Trim()

    if ($withoutLegacy.Removed -and -not $Force) {
        $removedFunctionList = ($withoutLegacy.RemovedNames | Sort-Object) -join ', '
        $choice = Read-Host "Detected existing unmanaged template functions in your profile ($removedFunctionList). Replace them? (Y/N)"
        if ($choice -notmatch '^[Yy]') {
            throw 'Installation cancelled by user.'
        }
    }

    if ([string]::IsNullOrWhiteSpace($contentAfterRemoval)) {
        return $managedBlock + [Environment]::NewLine
    }

    return ($contentAfterRemoval, '', $managedBlock) -join [Environment]::NewLine + [Environment]::NewLine
}

function Ensure-ProfileFile {
    param(
        [Parameter(Mandatory)]
        [string]$ResolvedProfilePath
    )

    $profileDirectory = Split-Path -Path $ResolvedProfilePath -Parent
    if ([string]::IsNullOrWhiteSpace($profileDirectory)) {
        $profileDirectory = (Get-Location).Path
    }
    if (-not (Test-Path -LiteralPath $profileDirectory)) {
        New-Item -ItemType Directory -Path $profileDirectory -Force | Out-Null
    }

    if (-not (Test-Path -LiteralPath $ResolvedProfilePath)) {
        New-Item -ItemType File -Path $ResolvedProfilePath -Force | Out-Null
    }
}

try {
    $resolvedRepoRoot = (Resolve-Path -LiteralPath $RepoRoot).ProviderPath
    $resolvedTemplatePath = if ($TemplatePath) {
        (Resolve-Path -LiteralPath $TemplatePath).ProviderPath
    } else {
        Join-Path -Path $resolvedRepoRoot -ChildPath 'profile.ps1'
    }
    $resolvedProfilePath = Get-DefaultProfilePath

    if (-not (Test-Path -LiteralPath $resolvedTemplatePath)) {
        throw "Profile template not found: $resolvedTemplatePath"
    }

    Ensure-Fzf

    Write-Step '[2/3] Configuring PowerShell profile...'
    Ensure-ProfileFile -ResolvedProfilePath $resolvedProfilePath

    $templateContent = Get-TemplateContent -ResolvedTemplatePath $resolvedTemplatePath -ResolvedRepoRoot $resolvedRepoRoot
    $templateFunctionNames = Get-FunctionNamesFromContent -Content $templateContent
    $existingProfileContent = Get-Content -LiteralPath $resolvedProfilePath -Raw -Encoding UTF8
    if ($null -eq $existingProfileContent) {
        $existingProfileContent = ''
    }

    $updatedProfileContent = Set-ManagedProfileBlock -ExistingContent $existingProfileContent -ManagedContent $templateContent -ManagedFunctionNames $templateFunctionNames
    Set-Content -LiteralPath $resolvedProfilePath -Value $updatedProfileContent -Encoding UTF8

    Write-Step '[3/3] Finalizing setup...'
    Write-Host "[SUCCESS] getskill was installed to: $resolvedProfilePath" -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
