推荐配合[`fzf`](https://github.com/junegunn/fzf)进行使用

我提供了bat脚本执行下面的步骤除克隆项目之外的步骤

使用步骤（win11powershell）

1. 安装`fzf`

   ```powershell
   winget install fzf
   ```

2.  克隆当前项目

   ```powershell
   git clone git@github.com:aisspire/mySkills.git
   # git clone https://github.com/aisspire/mySkills.git
   ```

3. 在powershell的配置文件中（`C:\Users\用户名\Documents\WindowsPowerShell\profile.ps1`）添加下面的函数（并根据需要修改`skillsDir`和`targetSubFolder`的值）


   ```powershell
   function getskill {
       # 1. 设置技能库的来源路径
       $skillsDir = "You clone the address of this project"
       
       # 2. 设置你想要存放在当前目录下的哪个子目录（例如 "modules" 或 "skills"）
       # 如果你想直接复制到当前目录下，请保持 $targetSubFolder = "."
       $targetSubFolder = ".\.agents\skills"
   
       # 检查来源目录是否存在
       if (!(Test-Path -Path $skillsDir)) {
           Write-Host "[ERROR] Directory $skillsDir not found." -ForegroundColor Red
           return
       }
   
       # 3. 使用 fzf 选择技能文件夹
       $skill = Get-ChildItem -Path $skillsDir -Directory | 
                Where-Object { $_.Name -ne ".git" } | 
                Select-Object -ExpandProperty Name | 
                fzf --prompt="Select skill to copy: "
   
       # 4. 如果选中了
       if ($skill) {
           # 确定来源的文件夹完整路径（不加 \* 就会复制整个文件夹）
           $sourcePath = Join-Path -Path $skillsDir -ChildPath $skill
           
           # 确定当前目录下的目标路径
           $destinationPath = Join-Path -Path $ExecutionContext.SessionState.Path.CurrentLocation -ChildPath $targetSubFolder
   
           # 如果目标子文件夹不存在，则创建它
           if (!(Test-Path -Path $destinationPath)) {
               New-Item -ItemType Directory -Path $destinationPath | Out-Null
           }
   
           # 执行复制：将整个文件夹复制到目标位置
           try {
               Copy-Item -Path $sourcePath -Destination $destinationPath -Recurse -Force
               Write-Host "[SUCCESS] Copied folder '$skill' into '$targetSubFolder/'" -ForegroundColor Green
           }
           catch {
               Write-Host "[ERROR] Failed to copy: $($_.Exception.Message)" -ForegroundColor Red
           }
       }
   }
   ```

4. 在你想要添加技能的项目根目录使用`powershell`执行`getskill`命令即可调用`fzf`搜索技能并复制到当前项目目录的技能存放处
## Installer Structure

- `installer.bat` remains the entry point.
- `src/install.ps1` contains the installation logic.
- `profile.ps1` remains the editable `getskill` function template.
