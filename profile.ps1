function getskill {
    # 1. 设置技能库的来源路径
    $skillsDir = "You clone the address of this project"
    
    # 2. 设置你想要存放在当前目录下的哪个子目录
    $targetSubFolder = ".\.agents\skills"

    # 检查来源目录是否存在
    if (!(Test-Path -Path $skillsDir)) {
        Write-Host "[ERROR] Directory $skillsDir not found." -ForegroundColor Red
        return
    }

    # 3. 使用 Get-ChildItem -Recurse 获取所有子目录的相对路径
    # 使用 -Name 直接得到相对路径 (例如 Utils\AI\Skill1)
    # 使用正则表达式 (^|\\)\.git(\|$) 安全过滤掉 .git 及其子目录
    $skillRelPath = Get-ChildItem -Path $skillsDir -Directory -Recurse -Name | 
             Where-Object { $_ -notmatch '(^|\\)\.git(\|$)' } | 
             fzf --prompt="Select skill to copy: "

    # 4. 如果选中了
    if ($skillRelPath) {
        # 完整源文件夹路径
        $sourcePath = Join-Path -Path $skillsDir -ChildPath $skillRelPath
        
        # 完整目标文件夹的基准路径
        $targetBasePath = Join-Path -Path $ExecutionContext.SessionState.Path.CurrentLocation -ChildPath $targetSubFolder
        
        # 最终该文件夹应当在的完整路径
        $destinationFolder = Join-Path -Path $targetBasePath -ChildPath $skillRelPath
        
        # 获取该文件夹的“父目录”路径
        # 例如你复制 A\B\C，我们要把它放在目标目录的 A\B 下，Copy-Item 会自动把 C 复制进 A\B
        $destParent = Split-Path -Path $destinationFolder -Parent

        # 如果目标的父层级目录还不存在，强制级联创建
        if (!(Test-Path -Path $destParent)) {
            New-Item -ItemType Directory -Path $destParent -Force | Out-Null
        }

        try {
            # 将源文件夹及其内部全部文件复制到目标的父目录下
            Copy-Item -Path $sourcePath -Destination $destParent -Recurse -Force
            Write-Host "[SUCCESS] Copied folder '$skillRelPath' into '$targetSubFolder'" -ForegroundColor Green
        }
        catch {
            Write-Host "[ERROR] Failed to copy: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
}
