@echo off
chcp 65001 >nul
setlocal

echo ===================================================
echo     getskill Auto-Setup Script
echo ===================================================
echo.

set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "INSTALL_SCRIPT=%REPO_ROOT%\src\install.ps1"

if not exist "%INSTALL_SCRIPT%" (
    echo [ERROR] Install script not found: "%INSTALL_SCRIPT%"
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%INSTALL_SCRIPT%" -RepoRoot "%REPO_ROOT%" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo ===================================================
    echo Setup finished.
    echo Restart PowerShell and then try: getskill
    echo ===================================================
) else (
    echo ===================================================
    echo Setup failed with exit code %EXIT_CODE%.
    echo ===================================================
)

pause
exit /b %EXIT_CODE%
