@echo off
setlocal

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

:: 3. Check for Fyne (New Tool)
where fyne >nul 2>nul
if %errorlevel% neq 0 goto :InstallFyne

:Build
echo.
echo [INFO] Tidying dependencies...
go mod tidy

:: 4. Build Native (Debug)
echo.
echo [INFO] Building Native Executable (PyQuickBox_Native.exe)...
go build -o %APP_NAME%_Native.exe .

if %errorlevel% neq 0 goto :Fail

:: 5. Package with Fyne
echo.
echo [INFO] Packaging with Fyne (PyQuickBox.exe)...
fyne package -os windows -icon %ICON% -name %APP_NAME% -appID %APP_ID%

if %errorlevel% equ 0 goto :Success
goto :Fail

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

:InstallFyne
echo.
echo [INFO] Installing NEW Fyne Tool (fyne.io/tools/cmd/fyne)...
:: Using the new CLI path
go install fyne.io/tools/cmd/fyne@latest
set "PATH=%PATH%;%USERPROFILE%\go\bin"
goto :Build

:Success
echo.
echo ----------------------------------------
echo [SUCCESS] Build Complete!
echo You have TWO files:
echo 1. PyQuickBox_Native.exe (Pure Go Build)
echo 2. PyQuickBox.exe (Fyne Packaged with Icon)
echo.
echo Please try running #1 first. If that works, try #2.
echo ----------------------------------------
pause
exit /b 0

:Fail
echo.
echo [FAILURE] Build Failed.
pause
exit /b 1
