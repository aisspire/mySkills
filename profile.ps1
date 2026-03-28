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

    $skillFilePath = Join-Path -Path $CurrentPath -ChildPath "SKILL.md"
    if (Test-Path -LiteralPath $skillFilePath -PathType Leaf) {
        return GS-GetRelativeSkillPath -RootPath $RootPath -CurrentPath $CurrentPath
    }

    $results = @()
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

function getskill {
    $skillsDir = "You clone the address of this project"
    $targetSubFolder = ".\.agents\skills"

    if (!(Test-Path -LiteralPath $skillsDir -PathType Container)) {
        Write-Host "[ERROR] Directory $skillsDir not found." -ForegroundColor Red
        return
    }

    $skillRelPath = GS-GetSkillDirectoryPaths -RootPath $skillsDir |
        fzf --prompt="Select skill to copy: "

    if ($skillRelPath) {
        $sourcePath = Join-Path -Path $skillsDir -ChildPath $skillRelPath
        $targetBasePath = Join-Path -Path $ExecutionContext.SessionState.Path.CurrentLocation -ChildPath $targetSubFolder
        $destinationFolder = Join-Path -Path $targetBasePath -ChildPath $skillRelPath
        $destParent = Split-Path -Path $destinationFolder -Parent

        if (!(Test-Path -LiteralPath $destParent)) {
            New-Item -ItemType Directory -Path $destParent -Force | Out-Null
        }

        try {
            Copy-Item -Path $sourcePath -Destination $destParent -Recurse -Force
            Write-Host "[SUCCESS] Copied folder '$skillRelPath' into '$targetSubFolder'" -ForegroundColor Green
        }
        catch {
            Write-Host "[ERROR] Failed to copy: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
}
