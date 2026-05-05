function GS-GetRelativeSkillPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath,

        [Parameter(Mandatory = $true)]
        [string]$CurrentPath
    )

    $fullRootPath = [System.IO.Path]::GetFullPath($RootPath).TrimEnd('\', '/')
    $fullCurrentPath = [System.IO.Path]::GetFullPath($CurrentPath).TrimEnd('\', '/')

    if ($fullCurrentPath -eq $fullRootPath) {
        return "."
    }

    return $fullCurrentPath.Substring($fullRootPath.Length + 1)
}

function GS-GetSkillDirectoryPathsRecursive {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath,

        [Parameter(Mandatory = $true)]
        [string]$CurrentPath
    )

    $results = @()
    $skillFilePath = Join-Path -Path $CurrentPath -ChildPath "SKILL.md"
    if (Test-Path -LiteralPath $skillFilePath -PathType Leaf) {
        $results += @(GS-GetRelativeSkillPath -RootPath $RootPath -CurrentPath $CurrentPath)
    }

    foreach ($childDirectory in Get-ChildItem -LiteralPath $CurrentPath -Directory) {
        if ($childDirectory.Name -eq ".git") {
            continue
        }

        $results += @(GS-GetSkillDirectoryPathsRecursive -RootPath $RootPath -CurrentPath $childDirectory.FullName)
    }

    return $results
}

function GS-GetSkillDirectoryPaths {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath
    )

    if (!(Test-Path -LiteralPath $RootPath -PathType Container)) {
        return @()
    }

    return @(GS-GetSkillDirectoryPathsRecursive -RootPath $RootPath -CurrentPath $RootPath)
}

function GS-GetSkillSetDirectoryPaths {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath
    )

    if (!(Test-Path -LiteralPath $RootPath -PathType Container)) {
        return @()
    }

    $results = @()
    foreach ($childDirectory in Get-ChildItem -LiteralPath $RootPath -Directory) {
        if ($childDirectory.Name -eq ".git") {
            continue
        }

        $childSkillFilePath = Join-Path -Path $childDirectory.FullName -ChildPath "SKILL.md"
        if (Test-Path -LiteralPath $childSkillFilePath -PathType Leaf) {
            continue
        }

        $childSkillPaths = @(GS-GetSkillDirectoryPaths -RootPath $childDirectory.FullName)
        if ($childSkillPaths.Count -gt 1) {
            $results += @(GS-GetRelativeSkillPath -RootPath $RootPath -CurrentPath $childDirectory.FullName)
        }
    }

    return $results
}

function GS-GetSkillSelectionLines {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath
    )

    $results = @()
    foreach ($skillSetPath in (@(GS-GetSkillSetDirectoryPaths -RootPath $RootPath) | Sort-Object)) {
        $results += @("[set]`t$skillSetPath")
    }

    foreach ($skillPath in (@(GS-GetSkillDirectoryPaths -RootPath $RootPath) | Sort-Object)) {
        $results += @("[skill]`t$skillPath")
    }

    return $results
}

function GS-GetSkillSelectionPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SelectionLine
    )

    $selectionParts = $SelectionLine -split "`t", 2
    if ($selectionParts.Count -ne 2) {
        return $null
    }

    return $selectionParts[1]
}

function getskill {
    $skillsDir = "You clone the address of this project"
    $targetSubFolder = ".\.agents\skills"

    if (!(Test-Path -LiteralPath $skillsDir -PathType Container)) {
        Write-Host "[ERROR] Directory $skillsDir not found." -ForegroundColor Red
        return
    }

    $selectionLines = @(GS-GetSkillSelectionLines -RootPath $skillsDir)
    if ($selectionLines.Count -eq 0) {
        Write-Host "[ERROR] No skills found in $skillsDir." -ForegroundColor Red
        return
    }

    $selectedLines = $selectionLines |
        fzf -m --prompt="Select skills or sets to copy: " --delimiter "`t" --nth 2 --tiebreak=begin,length,index

    if ($null -eq $selectedLines) {
        return
    }

    foreach ($selectedLine in @($selectedLines)) {
        if ([string]::IsNullOrWhiteSpace($selectedLine)) {
            continue
        }

        $skillRelPath = GS-GetSkillSelectionPath -SelectionLine $selectedLine
        if ([string]::IsNullOrWhiteSpace($skillRelPath)) {
            continue
        }

        $sourcePath = Join-Path -Path $skillsDir -ChildPath $skillRelPath
        $targetBasePath = Join-Path -Path $ExecutionContext.SessionState.Path.CurrentLocation -ChildPath $targetSubFolder
        $destinationFolder = Join-Path -Path $targetBasePath -ChildPath $skillRelPath
        $destParent = Split-Path -Path $destinationFolder -Parent

        if (!(Test-Path -LiteralPath $destParent)) {
            New-Item -ItemType Directory -Path $destParent -Force | Out-Null
        }

        try {
            Copy-Item -LiteralPath $sourcePath -Destination $destParent -Recurse -Force
            Write-Host "[SUCCESS] Copied folder '$skillRelPath' into '$targetSubFolder'" -ForegroundColor Green
        }
        catch {
            Write-Host "[ERROR] Failed to copy: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
}
