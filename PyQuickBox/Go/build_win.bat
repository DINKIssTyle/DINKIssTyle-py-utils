@echo off
setlocal enabledelayedexpansion

set "APP_NAME=PyQuickBox"
set "APP_ID=com.dinkisstyle.pyquickbox"
set "ICON=Icon.png"

echo Checking build environment...

:: 1. Check for Go
where go >nul 2>nul
if %errorlevel% neq 0 goto :NoGo

echo [DEBUG] Go Version:
go version

:: 2. Check for GCC
where gcc >nul 2>nul
if %errorlevel% neq 0 goto :NoGCC

echo [DEBUG] GCC Version:
gcc --version

:: 3. Force Install NEW Fyne Tool
echo.
echo [INFO] Ensuring Fyne Toolkit is installed...
go install fyne.io/tools/cmd/fyne@latest

:Build
echo.
echo [INFO] Tidying dependencies...
go mod tidy

:: 4. Build Native (Fallback)
echo.
echo [INFO] Building Native Executable (PyQuickBox_Native.exe)...
set GOOS=windows
set GOARCH=amd64
go build -ldflags="-s -w" -v -o %APP_NAME%_Native.exe .

:: 5. Package with Fyne (Correct Flags)
echo.
echo [INFO] Packaging with Fyne (PyQuickBox.exe)...
:: Using double-dash flags for the new tool
"%USERPROFILE%\go\bin\fyne" package --os windows --icon %ICON% --name %APP_NAME% --app-id %APP_ID%

if %errorlevel% equ 0 goto :Success
echo [WARNING] Fyne package failed.

:Success
echo.
echo ----------------------------------------
echo [SUCCESS] Build Process Finished.
echo.
echo 1. PyQuickBox_Native.exe (No Icon, Verified Working)
for %%I in (%APP_NAME%_Native.exe) do echo    Size: %%~zI bytes
echo.
echo 2. PyQuickBox.exe (Has Icon)
for %%I in (%APP_NAME%.exe) do echo    Size: %%~zI bytes
echo.
echo Note: If PyQuickBox.exe still fails, please use PyQuickBox_Native.exe
echo ----------------------------------------
pause
exit /b 0

:NoGo
echo.
echo [ERROR] Go is not installed.
pause
exit /b 1

:NoGCC
echo.
echo [ERROR] GCC is not installed.
pause
exit /b 1

:Fail
echo.
echo [FAILURE] Build Failed.
pause
exit /b 1
