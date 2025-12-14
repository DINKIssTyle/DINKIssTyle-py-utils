@echo off
setlocal enabledelayedexpansion

set "APP_NAME=PyQuickBox"
set "ICON_ICO=Icon.ico"

echo ----------------------------------------------------
echo  PyQuickBox Robust Windows Builder
echo ----------------------------------------------------

:: Clean up previous build artifacts
if exist rsrc.syso del rsrc.syso
if exist %APP_NAME%.exe del %APP_NAME%.exe

:: 1. Check Build Environment
echo [CHECK] Checking Go...
where go >nul 2>nul
if %errorlevel% neq 0 goto :NoGo

echo [CHECK] Checking GCC...
where gcc >nul 2>nul
if %errorlevel% neq 0 goto :NoGCC

:: 2. Install resource embedding tool (rsrc)
where rsrc >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Installing rsrc tool...
    go install github.com/akavel/rsrc@latest
)

:: 3. Icon Handling
if exist %ICON_ICO% (
    echo [INFO] Found %ICON_ICO%. Embedding...
    rsrc -ico %ICON_ICO% -o rsrc.syso
    if !errorlevel! neq 0 (
        echo [WARNING] rsrc failed to embed the icon.
        echo [WARNING] Deleting corrupted resource file to allow build to proceed.
        if exist rsrc.syso del rsrc.syso
    )
) else (
    echo [INFO] No %ICON_ICO% found. 
    echo [INFO] If you have Icon.png, please convert it to .ico manually for best results.
    echo [INFO] Building without icon for now...
)

:: 4. Build
echo.
echo [INFO] Building Application...
go mod tidy
:: Build with specific flags to avoid console window (-H=windowsgui) and strip debug info (-s -w)
go build -ldflags="-H=windowsgui -s -w" -v -o %APP_NAME%.exe .

if %errorlevel% equ 0 goto :Success
goto :Fail

:Success
echo.
echo ----------------------------------------------------
echo [SUCCESS] Build Complete: %APP_NAME%.exe
echo ----------------------------------------------------
if not exist rsrc.syso (
    echo [NOTE] The app was built WITHOUT an icon resource.
    echo To add an icon:
    echo 1. Place a valid 'Icon.ico' file in this folder.
    echo 2. Run this script again.
) else (
    echo [NOTE] Icon resource embedded successfully.
)
:: Cleanup resource file (optional, keeps folder clean)
if exist rsrc.syso del rsrc.syso
pause
exit /b 0

:NoGo
echo [ERROR] Go not installed.
pause
exit /b 1

:NoGCC
echo [ERROR] GCC not installed.
pause
exit /b 1

:Fail
echo.
echo [FAILURE] Build Failed.
pause
exit /b 1
