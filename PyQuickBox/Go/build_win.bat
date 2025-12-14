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

:: 3. Check for Fyne
where fyne >nul 2>nul
if %errorlevel% neq 0 goto :InstallFyne

:Build
echo.
echo [INFO] Tidying dependencies...
go mod tidy

:: 4. Build Test (Native Arch)
:: Clearing GOARCH to let Go detect the system's native architecture.
set GOOS=windows
set GOARCH=

echo.
echo [INFO] Running compilation check (go build)...
go build -v -o %APP_NAME%.exe .

if %errorlevel% neq 0 goto :Fail

echo.
echo [INFO] Packaging with Fyne (Adding Icon)...
:: Overwrite the test executable with the packaged one
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
echo Fyne requires a C compiler on Windows (MinGW or TDM-GCC).
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
echo Common Fixes:
echo 1. Ensure Go and GCC are both 64-bit (or both 32-bit).
echo 2. Re-install TDM-GCC (64-bit recommended).
pause
exit /b 1
