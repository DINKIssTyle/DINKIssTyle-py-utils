@echo off
setlocal

set "APP_NAME=PyQuickBox"
set "APP_ID=com.dinkisstyle.pyquickbox"
set "ICON=Icon.png"

echo Checking build environment...

:: 1. Check for Go
where go >nul 2>nul
if %errorlevel% neq 0 goto :NoGo

:: 2. Check for GCC
where gcc >nul 2>nul
if %errorlevel% neq 0 goto :NoGCC

:: 3. Check for Fyne
where fyne >nul 2>nul
if %errorlevel% neq 0 goto :InstallFyne

:Build
echo.
echo [INFO] Targeting Windows x64...
set "GOOS=windows"
set "GOARCH=amd64"

echo [INFO] Tidying dependencies...
go mod tidy

echo.
echo [INFO] Building %APP_NAME%...
fyne package -os windows -icon %ICON% -name %APP_NAME% -appID %APP_ID%

if %errorlevel% equ 0 goto :Success
goto :Fail

:NoGo
echo.
echo [ERROR] Go is not installed or not in PATH.
pause
exit /b 1

:NoGCC
echo.
echo [ERROR] GCC Compiler is NOT found.
echo Fyne requires a C compiler on Windows (MixGW or TDM-GCC).
echo Please install TDM-GCC from: https://jmeubank.github.io/tdm-gcc/
pause
exit /b 1

:InstallFyne
echo.
echo [INFO] Fyne CLI not found. Installing...
go install fyne.io/fyne/v2/cmd/fyne@latest
set "PATH=%PATH%;%USERPROFILE%\go\bin"
goto :Build

:Success
echo.
echo ----------------------------------------
echo [SUCCESS] Build Complete: %APP_NAME%.exe
echo ----------------------------------------
pause
exit /b 0

:Fail
echo.
echo [FAILURE] Build Failed. See errors above.
pause
exit /b 1
